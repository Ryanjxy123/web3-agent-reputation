"""Safe, database-free verification of frozen evidence bundles."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any, NoReturn
from uuid import UUID

from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AnchorReceipt,
    EvidenceManifest,
    EvidenceRecord,
    Observation,
    RecordVerificationInput,
    RunPlan,
)
from reputation_core.record_verifier import verify_record
from reputation_core.reporting import build_report
from web3 import Web3
from web3.types import HexStr


class VerificationError(ValueError):
    """A bundle failed a deterministic verification check."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


MAX_BUNDLE = 64 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_RATIO = 200
HEX32 = re.compile(r"^0x[0-9a-f]{64}$")
ANCHOR_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "agentKey", "type": "bytes32"},
            {"internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
        ],
        "name": "head",
        "outputs": [
            {"internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
            {"internalType": "uint64", "name": "sequence", "type": "uint64"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "evaluator", "type": "address"},
            {"internalType": "bytes32", "name": "agentKey", "type": "bytes32"},
            {"internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
        ],
        "name": "lookup",
        "outputs": [
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "bytes32", "name": "policyHash", "type": "bytes32"},
            {"internalType": "bytes32", "name": "previousReportHash", "type": "bytes32"},
            {"internalType": "uint64", "name": "sequence", "type": "uint64"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "evaluator", "type": "address"},
            {"indexed": True, "internalType": "bytes32", "name": "agentKey", "type": "bytes32"},
            {"indexed": True, "internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
            {"indexed": False, "internalType": "bytes32", "name": "policyHash", "type": "bytes32"},
            {"indexed": False, "internalType": "bytes32", "name": "previousReportHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint64", "name": "sequence", "type": "uint64"},
        ],
        "name": "ReportAnchored",
        "type": "event",
    },
]


def _fail(code: str, message: str) -> NoReturn:
    raise VerificationError(code, message)


def _read_zip(path: str) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            total = sum(info.file_size for info in infos)
            if total > MAX_BUNDLE:
                _fail("BUNDLE_TOO_LARGE", "Bundle exceeds the verification limit.")
            files: dict[str, bytes] = {}
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                if (
                    not name
                    or name in files
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or "\\" in name
                    or info.is_dir()
                    or info.file_size > MAX_MEMBER
                    or (info.compress_size and info.file_size / info.compress_size > MAX_RATIO)
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    _fail("UNSAFE_ARCHIVE", "Bundle contains an unsafe or duplicate member.")
                files[name] = archive.read(info)
            return files
    except (OSError, zipfile.BadZipFile) as exc:
        raise VerificationError("INVALID_ZIP", "Bundle is not a readable ZIP archive.") from exc


def _json(files: dict[str, bytes], path: str) -> Any:
    if path not in files:
        _fail("MISSING_FILE", f"Bundle is missing {path}.")
    try:
        return strict_json(files[path])
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError("INVALID_JSON", f"Invalid JSON in {path}.") from exc


def _bytes32(value: str) -> bytes:
    if not HEX32.fullmatch(value):
        _fail("INVALID_HASH", "Expected a lowercase 32-byte hex value.")
    return bytes.fromhex(value[2:])


def _verify_anchor(rpc_url: str, manifest: EvidenceManifest, receipt: AnchorReceipt, report_hash: str, core) -> dict[str, Any]:
    if receipt.status != "CONFIRMED":
        return {"status": "NOT_CHECKED", "reason": "bundle has no confirmed anchor"}
    if not rpc_url:
        return {"status": "NOT_CHECKED", "reason": "trusted RPC was not configured"}
    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        tx_hash, block_hash, block_number = receipt.tx_hash, receipt.block_hash, receipt.block_number
        if tx_hash is None or block_hash is None or block_number is None:
            _fail("ANCHOR_RECEIPT_MISMATCH", "Confirmed anchor receipt is incomplete.")
        chain = manifest.publication.chain
        if str(web3.eth.chain_id) != chain.chain_id or web3.eth.get_block(0)["hash"].to_0x_hex().lower() != chain.genesis_hash:
            _fail("CHAIN_INSTANCE_MISMATCH", "Trusted RPC is a different chain instance.")
        transaction_id = HexStr(tx_hash)
        tx = web3.eth.get_transaction(transaction_id)
        mined = web3.eth.get_transaction_receipt(transaction_id)
        if (
            int(mined["status"]) != 1
            or tx["to"] is None
            or tx["to"].lower() != manifest.publication.contract.lower()
            or tx["from"].lower() != manifest.publication.publisher.lower()
        ):
            _fail("ANCHOR_TX_MISMATCH", "Anchor transaction is not a successful call to the committed contract.")
        if mined["blockHash"].to_0x_hex().lower() != block_hash or str(mined["blockNumber"]) != block_number:
            _fail("ANCHOR_RECEIPT_MISMATCH", "Committed anchor receipt does not match the trusted chain.")
        head = web3.eth.block_number - int(mined["blockNumber"]) + 1
        if head < manifest.publication.confirmation_depth:
            _fail("ANCHOR_NOT_FINAL", "Anchor confirmation depth is not satisfied.")
        contract = web3.eth.contract(address=Web3.to_checksum_address(manifest.publication.contract), abi=ANCHOR_ABI)
        exists, policy, previous, sequence = contract.functions.lookup(
            Web3.to_checksum_address(manifest.publication.publisher),
            _bytes32(core.agent_key_hash),
            _bytes32(report_hash),
        ).call()
        if not exists or "0x" + bytes(policy).hex() != core.policy_hash or "0x" + bytes(previous).hex() != core.previous_report_hash or str(sequence) != str(receipt.sequence):
            _fail("ANCHOR_RECORD_MISMATCH", "The trusted contract record does not match the report.")
        return {"status": "CONFIRMED", "confirmations": head}
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError("RPC_UNAVAILABLE", "Trusted RPC could not verify the anchor.") from exc


def verify_bundle(path: str, *, rpc_url: str | None = None) -> dict[str, Any]:
    files = _read_zip(path)
    core_data = _json(files, "report_core.json")
    manifest_data = _json(files, "evidence_manifest.json")
    receipt_data = _json(files, "anchor_receipt.json")
    try:
        from reputation_core.models import ReportCore

        core = ReportCore.model_validate(core_data)
        manifest = EvidenceManifest.model_validate(manifest_data)
        receipt = AnchorReceipt.model_validate(receipt_data)
    except ValueError as exc:
        raise VerificationError("SCHEMA_ERROR", "Bundle documents do not match the published schemas.") from exc
    report_hash = hash_json(core.model_dump(mode="json"))
    manifest_hash = hash_json(manifest.model_dump(mode="json"))
    if report_hash != hash_json(core_data) or core.evidence_manifest_hash != manifest_hash or receipt.report_hash != report_hash:
        _fail("CONTENT_HASH_MISMATCH", "Report, manifest, or receipt hash does not match.")

    expected: dict[str, EvidenceRecord] = {item.path: item for item in manifest.evidence}
    aliases: dict[str, bytes] = {}
    for record in manifest.evidence:
        if record.path not in files:
            _fail("MISSING_EVIDENCE", f"Bundle is missing {record.path}.")
        data = files[record.path]
        if len(data) != record.byte_count or hash_bytes(data) != record.blob_hash:
            _fail("CONTENT_HASH_MISMATCH", f"Evidence commitment failed for {record.path}.")
    for document in manifest.documents:
        if document.path not in files or str(document.evidence_id) not in {str(item.evidence_id) for item in manifest.evidence}:
            _fail("MISSING_EVIDENCE", f"Bundle is missing committed document {document.path}.")
        record = next(item for item in manifest.evidence if item.evidence_id == document.evidence_id)
        if files[document.path] != files[record.path]:
            _fail("CONTENT_HASH_MISMATCH", f"Document alias {document.path} differs from its blob.")
        aliases[document.path] = files[document.path]
    allowed = {"report_core.json", "evidence_manifest.json", "anchor_receipt.json", "FORMAT.md", *expected, *aliases}
    if set(files) - allowed:
        _fail("UNCOMMITTED_FILE", "Bundle contains a file absent from the manifest.")

    try:
        verification = strict_json(aliases["verification.json"])
        input_id = UUID(verification["input_evidence_id"])
        input_record = next(item for item in manifest.evidence if item.evidence_id == input_id)
        inputs = RecordVerificationInput.model_validate_json(files[input_record.path])
        plan = RunPlan.model_validate_json(aliases["run_plan.json"])
        observations = tuple(Observation.model_validate(item) for item in strict_json(aliases["observations.json"]))
        policy = strict_json(aliases["policy.json"])
        rebuilt = build_report(
            plan,
            inputs,
            input_id,
            observations,
            policy,
            evaluated_at=core.evaluated_at,
            code_version=core.code_version,
            manifest_hash=manifest_hash,
            previous_report_hash=core.previous_report_hash,
        )
        replay = verify_record(inputs, (input_id,))
        if rebuilt != core or tuple(sorted(replay.assertions, key=lambda item: str(item.assertion_id))) != tuple(core.assertions):
            _fail("REPLAY_MISMATCH", "Recomputed assertions or report statistics differ.")
    except VerificationError:
        raise
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError("REPLAY_MISMATCH", "Bundle could not be replayed from its committed inputs.") from exc
    anchor = _verify_anchor(rpc_url or "", manifest, receipt, report_hash, core)
    return {"status": "PASS", "offline": "PASS", "report_hash": report_hash, "anchor": anchor}
