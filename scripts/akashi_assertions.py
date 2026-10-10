"""Pure assertions for the documented Akashi CID proof on Base; no calls or scoring."""

import re
from typing import Any

from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError, EncodingError
from reputation_core.evidence import canonical_bytes, hash_bytes, strict_json
from reputation_core.record_verifier import hex_data, quantity, transaction_evidence_reason

CONTRACTS = {
    "0xe0c6bb0914be3e49e13ffbc389cf659871a1bcd3": "USDC",
    "0xeed9d0f7265892e84e43d05da464c75add199260": "ETH",
}
EVENT_TOPIC = hash_bytes(b"Anchored(string,string,string,address,uint256,uint256)")
EVENT_TYPES = ("string", "string", "address", "uint256", "uint256")
MIN_CONFIRMATIONS = 12


def _hash(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("INVALID_SHA256")
    result = value.removeprefix("0x").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", result):
        raise ValueError("INVALID_SHA256")
    return result


def _uint(value: Any, *, text=False) -> int:
    if text:
        if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
            raise ValueError("INVALID_UNSIGNED_INTEGER")
        value = int(value)
    if type(value) is not int or not 0 <= value < 2**256:
        raise ValueError("INVALID_UNSIGNED_INTEGER")
    return value


def normalize_proof(value: Any, mcp: bool = False) -> dict[str, Any]:
    """Keep documented business fields; reject conflicting MCP representations."""
    if not isinstance(value, dict):
        raise ValueError("PROOF_OBJECT_REQUIRED")
    if mcp:
        if value.get("isError", False) is not False:
            raise ValueError("MCP_TOOL_ERROR")
        representations = []
        if value.get("structuredContent") is not None:
            representations.append(normalize_proof(value["structuredContent"]))
        contents = value.get("content", [])
        if not isinstance(contents, list):
            raise ValueError("INVALID_MCP_CONTENT")
        for content in contents:
            if not isinstance(content, dict):
                raise ValueError("INVALID_MCP_CONTENT")
            if content.get("type") == "text":
                if not isinstance(content.get("text"), str):
                    raise ValueError("INVALID_MCP_TEXT")
                try:
                    representations.append(normalize_proof(strict_json(content["text"].encode())))
                except RecursionError as exc:
                    raise ValueError("MCP_JSON_TOO_DEEP") from exc
        if not representations or any(item != representations[0] for item in representations[1:]):
            raise ValueError("MCP_PROOF_MISSING_OR_CONFLICTING")
        return representations[0]
    if type(value.get("anchored")) is not bool or not isinstance(value.get("proofs"), list):
        raise ValueError("INVALID_PROOF_ENVELOPE")
    proofs = []
    for proof in value["proofs"]:
        if not isinstance(proof, dict) or not isinstance(proof.get("filename"), str):
            raise ValueError("INVALID_PROOF")
        if not isinstance(proof.get("chain"), str) or not isinstance(proof.get("currency"), str):
            raise ValueError("INVALID_PROOF_CHAIN_OR_CURRENCY")
        proofs.append(
            {
                "hash": _hash(proof.get("hash")),
                "filename": proof["filename"],
                "submitter": hex_data(proof.get("submitter"), 20),
                "timestamp": _uint(proof.get("timestamp")),
                "paid": str(_uint(proof.get("paid"), text=True)),
                "currency": proof["currency"],
                "chain": proof["chain"],
                "chainId": _uint(proof.get("chainId")),
                "contract": hex_data(proof.get("contract"), 20),
                "txHash": hex_data(proof.get("txHash"), 32),
                "blockNumber": _uint(proof.get("blockNumber")),
            }
        )
    result: dict[str, Any] = {
        "anchored": value["anchored"],
        "proofs": sorted(proofs, key=canonical_bytes),
    }
    for name in ("tx", "hash"):
        if name in value:
            result[name] = hex_data(value[name], 32) if name == "tx" else _hash(value[name])
    for name in ("searched", "unsearched"):
        if name in value:
            if not isinstance(value[name], list):
                raise ValueError("INVALID_SEARCH_SCOPE")
            result[name] = sorted({hex_data(item, 20) for item in value[name]})
    return result


def verify_proof(
    normalized: dict[str, Any], query: dict[str, Any], chain_evidence: dict[str, Any]
) -> dict[str, Any]:
    """Confirm service claims against a complete independent canonical Base receipt."""
    assertions: list[dict[str, Any]] = []

    def result(status, reason, *, proofs=(), confirmations=None):
        return {
            "status": status,
            "reason": reason,
            "assertions": assertions,
            "confirmed_proofs": list(proofs),
            "confirmations": confirmations,
        }

    def check(rule, passed, expected, observed):
        assertions.append(
            {
                "rule": rule,
                "status": "PASS" if passed else "FAIL",
                "expected": expected,
                "observed": observed,
            }
        )
        return passed

    try:
        normalized = normalize_proof(normalized)
        if set(query) not in ({"tx"}, {"hash"}):
            raise ValueError("INVALID_QUERY")
        requested = hex_data(query["tx"], 32) if "tx" in query else _hash(query["hash"])
    except (ValueError, TypeError, KeyError):
        return result("UNKNOWN", "PROOF_OR_QUERY_SCHEMA_INVALID")
    if "hash" in query and not normalized["proofs"]:
        # A search response does not independently establish absence across either contract.
        return result(
            "UNKNOWN",
            "SEARCH_INCOMPLETE"
            if normalized.get("unsearched")
            else "GLOBAL_ABSENCE_NOT_ESTABLISHED",
        )
    try:
        rpc = {
            **chain_evidence,
            "transaction": chain_evidence["tx"],
            "receipt_canonical": chain_evidence["canonical_block"],
        }
        if quantity(rpc["chain_id"]) != 8453:
            return result("UNKNOWN", "RPC_WRONG_CHAIN")
        candidate = requested if "tx" in query else normalized["proofs"][0]["txHash"]
        error = transaction_evidence_reason(rpc, candidate, writing=True)
        if error is not None:
            return result("UNKNOWN", error.value)
        tx, receipt = rpc["transaction"], rpc["receipt"]
        if tx is None or receipt is None:
            return result("UNKNOWN", "RECEIPT_NOT_CONFIRMED")
        block, canonical, head = rpc["receipt_block"], rpc["receipt_canonical"], rpc["head"]
        timestamp = quantity(block["timestamp"])
        if quantity(canonical["timestamp"]) != timestamp:
            return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
        if hex_data(canonical["hash"], 32) != hex_data(receipt["blockHash"], 32):
            return result("UNKNOWN", "PENDING_FINALITY")
        confirmations = quantity(head["number"]) - quantity(receipt["blockNumber"]) + 1
        if confirmations < MIN_CONFIRMATIONS:
            return result("UNKNOWN", "PENDING_FINALITY", confirmations=confirmations)
        for field in ("from", "to"):
            receipt_address = hex_data(receipt[field], 20) if receipt[field] is not None else None
            tx_address = hex_data(tx[field], 20) if tx[field] is not None else None
            if receipt_address != tx_address:
                return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
        expected_proofs = []
        previous_index = -1
        for log in receipt["logs"]:
            if not isinstance(log, dict) or type(log.get("removed")) is not bool:
                raise ValueError("INVALID_LOG")
            if log["removed"]:
                return result("UNKNOWN", "PENDING_FINALITY")
            if any(
                (hex_data(log[field], 32) != hex_data(receipt[field], 32))
                if field in ("transactionHash", "blockHash")
                else quantity(log[field]) != quantity(receipt[field])
                for field in ("transactionHash", "blockHash", "blockNumber", "transactionIndex")
            ):
                return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
            index = quantity(log["logIndex"])
            if index <= previous_index:
                return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
            previous_index = index
            address = hex_data(log["address"], 20)
            if not isinstance(log["topics"], list) or len(log["topics"]) > 4:
                raise ValueError("INVALID_TOPICS")
            topics = [hex_data(topic, 32) for topic in log["topics"]]
            data = bytes.fromhex(hex_data(log["data"])[2:])
            if address not in CONTRACTS or not topics or topics[0] != EVENT_TOPIC:
                continue
            if len(topics) != 2:
                raise ValueError("INVALID_ANCHORED_TOPICS")
            cid, filename, submitter, event_time, paid = decode(EVENT_TYPES, data, strict=True)
            if encode(EVENT_TYPES, (cid, filename, submitter, event_time, paid)) != data:
                raise ValueError("NONCANONICAL_EVENT_ENCODING")
            if topics[1] != hash_bytes(cid.encode()) or event_time != timestamp:
                return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
            try:
                digest = _hash(cid)
            except ValueError:
                return result("UNKNOWN", "UNSUPPORTED_CID_RECORD_FORMAT")
            expected_proofs.append(
                {
                    "hash": digest,
                    "filename": filename,
                    "submitter": hex_data(submitter, 20),
                    "timestamp": event_time,
                    "paid": str(paid),
                    "currency": CONTRACTS[address],
                    "chain": "base",
                    "chainId": 8453,
                    "contract": address,
                    "txHash": candidate,
                    "blockNumber": quantity(receipt["blockNumber"]),
                }
            )
        if quantity(receipt["status"]) == 0 and receipt["logs"]:
            return result("UNKNOWN", "EVIDENCE_INCONSISTENT")
    except (ValueError, TypeError, KeyError, AttributeError, DecodingError, EncodingError):
        return result("UNKNOWN", "PLATFORM_RPC_ERROR")
    assertions.append({"rule": "rpc.canonical", "status": "PASS", "confirmations": confirmations})
    if not check(
        "query.echo",
        normalized.get(next(iter(query))) == requested,
        requested,
        normalized.get(next(iter(query))),
    ):
        return result("FAIL", "RESPONSE_QUERY_MISMATCH", confirmations=confirmations)
    if "hash" in query:
        if any(proof["txHash"] != candidate for proof in normalized["proofs"]):
            return result("UNKNOWN", "ADDITIONAL_TRANSACTIONS_NOT_VERIFIED")
        expected_proofs = [proof for proof in expected_proofs if proof["hash"] == requested]
    if not check(
        "proof.anchored",
        normalized["anchored"] == bool(expected_proofs),
        bool(expected_proofs),
        normalized["anchored"],
    ):
        return result("FAIL", "ANCHOR_CLAIM_MISMATCH", confirmations=confirmations)
    if not check(
        "proof.events",
        normalized["proofs"] == sorted(expected_proofs, key=canonical_bytes),
        sorted(expected_proofs, key=canonical_bytes),
        normalized["proofs"],
    ):
        return result("FAIL", "PROOF_EVENT_MISMATCH", confirmations=confirmations)
    if expected_proofs:
        target = hex_data(tx["to"], 20) if tx["to"] is not None else None
        direct = target in CONTRACTS
        assertions.append(
            {
                "rule": "tx.target",
                "status": "PASS" if direct else "UNKNOWN",
                "expected": sorted(CONTRACTS),
                "observed": target,
            }
        )
        # shortcut: indirect targets stay UNKNOWN; expand when an adapter covers routed calls.
        if not direct:
            return result("UNKNOWN", "INDIRECT_TARGET_NOT_VERIFIED", confirmations=confirmations)
    return result(
        "PASS",
        "BUSINESS_EVENT_CONFIRMED" if expected_proofs else "TRANSACTION_ABSENCE_CONFIRMED",
        proofs=expected_proofs,
        confirmations=confirmations,
    )
