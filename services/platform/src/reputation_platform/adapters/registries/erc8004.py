"""One fixed-block public identity; RPC and metadata targets are operator-owned constants."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AgentRef,
    ChainIdentity,
    EvidenceRecord,
    Outcome,
    PublicIdentityRead,
    Reason,
    SnapshotCore,
)
from reputation_core.models.public_identity import IdentityOutcome
from reputation_core.public_identity import (
    normalized_public_metadata,
    parse_registration_metadata,
    readonly_endpoints,
)

from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.audited_readonly import (
    audited_readonly_request,
    evidence_json,
)
from reputation_platform.infrastructure.network.safe_http import (
    PUBLIC_ORIGIN,
    NetworkPolicyError,
    SafeHttpClient,
    decode_public_json,
)

RPC_ORIGIN = "https://mainnet.base.org"
REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
AKASHI_REF = AgentRef(chain_id="8453", registry_address=REGISTRY, agent_id="98097")
REGISTRATION_PATH = "/.well-known/agent-registration.json"
REGISTRATION_URI = PUBLIC_ORIGIN + REGISTRATION_PATH
ABI_SHA256 = "cdb8e30f41a56ed53421126dab87551ff2a178b8463646f69f75bc5dc9620564"


@dataclass(frozen=True)
class PublicRegistryReadResult:
    core: SnapshotCore | None
    identity: PublicIdentityRead
    evidence: tuple[EvidenceRecord, ...]
    openapi_raw: bytes | None = None
    metadata_raw: bytes | None = None


class Erc8004RegistryReader:
    def __init__(self, root: Path, client: SafeHttpClient, evidence: EvidenceStore):
        if not client.is_public_readonly:
            raise NetworkPolicyError("PUBLIC_READONLY_DISABLED")
        abi = (root / "third_party/erc8004/IdentityRegistry.json").read_bytes()
        lock = strict_json((root / "configs/upstream-lock.json").read_bytes())
        if (hashlib.sha256(abi).hexdigest() != ABI_SHA256
                or lock["erc8004"]["commit"] != "b9e466c250744a7e06b13dff9d3c2844ed64f825"):
            raise NetworkPolicyError("UPSTREAM_NOT_PINNED")
        functions = {item.get("name"): item for item in strict_json(abi)
                     if item.get("type") == "function"}
        for name, output in (("ownerOf", "address"), ("tokenURI", "string")):
            entry = functions[name]
            if (entry["stateMutability"] != "view"
                    or entry["inputs"] != [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}]
                    or [item["type"] for item in entry["outputs"]] != [output]):
                raise NetworkPolicyError("UPSTREAM_NOT_PINNED")
        self.client, self.evidence = client, evidence
        self._identifier = 0

    async def _request(self, method, origin, path, payload, records):
        redactor = None
        if origin == RPC_ORIGIN and payload:
            def redact_abi(value):
                omitted = {"jsonrpc": "2.0", "id": payload["id"],
                           "result": "[UNSUPPORTED RPC RESULT OMITTED]"}
                if (set(value) != {"jsonrpc", "id", "result"} or value["jsonrpc"] != "2.0"
                        or type(value["id"]) is not int or value["id"] != payload["id"]):
                    return omitted
                if payload["method"] != "eth_call":
                    return value
                type_name = "string" if payload["params"][0]["data"].startswith("0xc87b56dd") else "address"
                try:
                    decoded = self._abi_result(value.get("result"), type_name)
                    safe = decoded == REGISTRATION_URI if type_name == "string" else int(decoded[2:], 16) != 0
                except (ValueError, TypeError, DecodingError):
                    safe = False
                return value if safe else omitted
            redactor = redact_abi
        response = await audited_readonly_request(
            self.client, self.evidence, protocol="erc8004-public-readonly-v1",
            capability_id="identity-read", method=method, origin=origin, path=path,
            payload=payload, records=records, response_redactor=redactor,
        )
        if response.audit.get("payment_required") or response.status == 402:
            raise NetworkPolicyError("PAYMENT_REQUIRED")
        if response.status != 200:
            raise NetworkPolicyError("PUBLIC_IDENTITY_RESPONSE_UNAVAILABLE")
        value = decode_public_json(response)
        if evidence_json(value) != value:
            self.client.stop_public_readonly("SENSITIVE_METADATA")
            raise NetworkPolicyError("SENSITIVE_METADATA")
        return value, response.body

    async def _rpc(self, method, params, records):
        self._identifier += 1
        value, _ = await self._request("POST", RPC_ORIGIN, "/", {
            "jsonrpc": "2.0", "id": self._identifier, "method": method, "params": params,
        }, records)
        if (set(value) != {"jsonrpc", "id", "result"} or value["jsonrpc"] != "2.0"
                or type(value["id"]) is not int or value["id"] != self._identifier):
            raise NetworkPolicyError("INVALID_RPC_ENVELOPE")
        return value["result"]

    @staticmethod
    def _quantity(value):
        if not isinstance(value, str) or re.fullmatch(r"0x(?:0|[1-9a-f][0-9a-f]{0,15})", value) is None:
            raise ValueError("invalid RPC quantity")
        return int(value, 16)

    @classmethod
    def _block(cls, value, expected_number=None):
        if not isinstance(value, dict):
            raise ValueError("missing RPC block")
        number, digest = cls._quantity(value.get("number")), value.get("hash")
        if (not isinstance(digest, str) or re.fullmatch(r"0x[0-9a-f]{64}", digest) is None
                or int(digest[2:], 16) == 0
                or expected_number is not None and number != expected_number):
            raise ValueError("invalid RPC block")
        return number, digest

    @staticmethod
    def _abi_result(value, type_name):
        if not isinstance(value, str) or re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", value) is None:
            raise ValueError("missing ABI result")
        raw = bytes.fromhex(value[2:])
        result = decode([type_name], raw)[0]
        if encode([type_name], [result]) != raw:
            raise ValueError("noncanonical ABI result")
        return result

    async def read(self, ref: AgentRef) -> PublicRegistryReadResult:
        if ref != AKASHI_REF:
            raise NetworkPolicyError("UNSUPPORTED_PUBLIC_REGISTRY")
        records: list[EvidenceRecord] = []
        code_hash = None
        registration: IdentityOutcome = Outcome.UNKNOWN
        registration_reason: Reason | None = Reason.PLATFORM_RPC_ERROR
        metadata = None
        metadata_hash = openapi_hash = None
        metadata_raw = None
        openapi_raw = None
        core = None
        metadata_reason: Reason | None = Reason.MISSING_EVIDENCE
        try:
            if self._quantity(await self._rpc("eth_chainId", [], records)) != int(ref.chain_id):
                raise ValueError("wrong registration chain")
            _, genesis = self._block(await self._rpc("eth_getBlockByNumber", ["0x0", False], records), 0)
            number, block_hash = self._block(
                await self._rpc("eth_getBlockByNumber", ["latest", False], records)
            )
            tag = hex(number)
            code = await self._rpc("eth_getCode", [REGISTRY, tag], records)
            if not isinstance(code, str) or re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", code) is None:
                raise ValueError("registry bytecode unavailable")
            code_hash = hash_bytes(bytes.fromhex(code[2:]))
            owner = self._abi_result(await self._rpc("eth_call", [{
                "to": REGISTRY, "data": "0x6352211e" + f"{int(ref.agent_id):064x}",
            }, tag], records), "address").lower()
            if int(owner[2:], 16) == 0:
                raise ValueError("zero owner")
            uri = self._abi_result(await self._rpc("eth_call", [{
                "to": REGISTRY, "data": "0xc87b56dd" + f"{int(ref.agent_id):064x}",
            }, tag], records), "string")
            if self._block(await self._rpc("eth_getBlockByNumber", [tag, False], records), number)[1] != block_hash:
                registration_reason = Reason.IDENTITY_CHANGED
                raise ValueError("registration block changed")
            registration, registration_reason = Outcome.PASS, None
            metadata_reason = Reason.SCHEMA_ERROR
            # A changed URI is evidence, never permission to contact its host or path.
            if uri != REGISTRATION_URI:
                metadata_reason = Reason.UNSUPPORTED_PROTOCOL
                raise NetworkPolicyError("UNSUPPORTED_METADATA_URI")
            _, raw = await self._request("GET", PUBLIC_ORIGIN, REGISTRATION_PATH, None, records)
            metadata_raw = raw
            metadata_hash = hash_bytes(raw)
            metadata = parse_registration_metadata(raw, ref)
            endpoints = readonly_endpoints(metadata)
            if not endpoints:
                raise ValueError("no supported static endpoint")
            if any(endpoint.protocol == "akashi-http-readonly-v1" for endpoint in endpoints):
                _, openapi_raw = await self._request("GET", PUBLIC_ORIGIN, "/openapi.json", None, records)
                openapi_hash = hash_bytes(openapi_raw)
            if self._block(await self._rpc("eth_getBlockByNumber", [tag, False], records), number)[1] != block_hash:
                registration, registration_reason = Outcome.UNKNOWN, Reason.IDENTITY_CHANGED
                raise ValueError("registration block changed")
            domain = hash_json({"kind": "erc8004-public-v1", "chain_id": ref.chain_id,
                                "genesis_hash": genesis, "registry_address": REGISTRY})
            chain_body = {"chain_id": ref.chain_id, "genesis_hash": genesis,
                          "deployment_instance_id": domain, "registry_code_hash": code_hash}
            normalized = normalized_public_metadata(metadata)
            core = SnapshotCore(
                agent_ref=ref, source_type="public_registry", owner=owner, declared_executor=None,
                agent_uri=uri, registry_revision=0, metadata_hash=hash_json(normalized),
                normalized_metadata=normalized, endpoints=endpoints, read_block_number=str(number),
                read_block_hash=block_hash, captured_at=timestamp(),
                registry_chain=ChainIdentity(**chain_body, instance_hash=hash_json(chain_body)),
            )
            metadata_reason = None
        except (httpx.HTTPError, TimeoutError):
            if registration == Outcome.PASS:
                metadata_reason = Reason.PLATFORM_NETWORK_ERROR
            core, metadata = None, None
        except NetworkPolicyError as exc:
            if registration == Outcome.PASS and metadata_reason == Reason.SCHEMA_ERROR:
                metadata_reason = (Reason.NOT_DECLARED_READ_ONLY if "PAYMENT" in str(exc)
                                   else Reason.SCHEMA_ERROR if str(exc) in {
                                       "INVALID_JSON", "JSON_TOO_DEEP", "SENSITIVE_METADATA",
                                       "EXPECTED_JSON", "EXPECTED_JSON_OBJECT", "UNSUPPORTED_OPENAPI_PROOF",
                                   } else Reason.PLATFORM_NETWORK_ERROR)
            core, metadata = None, None
        except (ValueError, TypeError, KeyError, DecodingError):
            # Saved responses retain the cause; no guessed owner, URI, or snapshot is emitted.
            core, metadata = None, None
        identity = PublicIdentityRead(
            abi_sha256=ABI_SHA256, registry_code_hash=code_hash, rpc_source="operator-base-mainnet-v1",
            source_hashes=tuple(dict.fromkeys(record.blob_hash for record in records)),
            metadata_bytes_hash=metadata_hash, openapi_bytes_hash=openapi_hash, metadata=metadata,
            registration_outcome=registration, registration_reason=registration_reason,
            metadata_outcome=Outcome.PASS if core else Outcome.UNKNOWN,
            metadata_reason=metadata_reason,
        )
        return PublicRegistryReadResult(core, identity, tuple(records), openapi_raw, metadata_raw)
