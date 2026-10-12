"""Safe, database-free verification of frozen evidence bundles."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any, NoReturn
from uuid import UUID

from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AnchorReceipt,
    AssertionResult,
    EvidenceManifest,
    EvidenceRecord,
    Observation,
    Outcome,
    Reason,
    RecordVerificationInput,
    ReportCore,
    RunPlan,
)
from reputation_core.record_verifier import preserve_rpc_unknown, verify_record
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
VERIFICATION_LIMITATIONS = (
    "Offline PASS proves committed material and rule consistency, not original authenticity.",
    "Task live_chain checks execution-chain facts; it does not authenticate historical Registry "
    "ownership, endpoints, or HTTP originals.",
    "Anchor CONFIRMED proves publication of the report digest, not authenticity of its originals.",
)
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
            {
                "indexed": False,
                "internalType": "bytes32",
                "name": "previousReportHash",
                "type": "bytes32",
            },
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


def _record_by_id(manifest: EvidenceManifest) -> dict[UUID, EvidenceRecord]:
    return {item.evidence_id: item for item in manifest.evidence}


def _expected_rule_version(template: Any) -> str:
    value = str(template)
    if value.endswith("@1"):
        return "1"
    if value.endswith("@2"):
        return "2"
    if value.endswith("@3"):
        return "3"
    if value.endswith("@4"):
        return "4"
    if value.endswith("@6"):
        return "6"
    if value.endswith("@5"):
        return "5"
    _fail("RULE_VERSION_MISMATCH", "Run plan uses an unsupported assertion template.")


def _bundle_tasks(
    verification: Any,
    plan: RunPlan,
    core_data: dict[str, Any],
    records: dict[UUID, EvidenceRecord],
    files: dict[str, bytes],
) -> list[tuple[Any, UUID, UUID, UUID | None, UUID | None]]:
    """Resolve each planned task to its input, freeze, and optional HTTP evidence."""
    if not isinstance(verification, dict):
        _fail("REPLAY_MISMATCH", "Verification index must be an object.")
    if verification.get("schema_version") == "task-replay-v1":
        rows = verification.get("tasks")
        if not isinstance(rows, list) or not rows:
            _fail("REPLAY_MISMATCH", "Task replay index is empty or malformed.")
    elif verification.get("schema_version") is not None:
        _fail("RULE_VERSION_MISMATCH", "Verification index uses an unsupported schema version.")
    elif "input_evidence_id" in verification and "freeze_evidence_id" in verification:
        if set(verification) != {"input_evidence_id", "freeze_evidence_id"}:
            _fail("REPLAY_MISMATCH", "Legacy verification index contains unexpected fields.")
        if len(plan.slots) != 1:
            _fail("REPLAY_MISMATCH", "Legacy verification index can identify only one task.")
        rows = [
            {
                "slot_id": str(plan.slots[0].slot_id),
                "input_evidence_id": verification["input_evidence_id"],
                "freeze_evidence_id": verification["freeze_evidence_id"],
            }
        ]
    else:
        _fail("REPLAY_MISMATCH", "Verification index version is missing or unsupported.")

    planned = {str(slot.slot_id): slot for slot in plan.slots}
    resolved = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            _fail("REPLAY_MISMATCH", "Task replay entry must be an object.")
        if set(row) - {
            "slot_id",
            "input_evidence_id",
            "freeze_evidence_id",
            "agent_http_evidence_id",
            "initial_http_evidence_id",
        }:
            _fail("REPLAY_MISMATCH", "Task replay entry contains unexpected fields.")
        slot_key = row.get("slot_id")
        if not isinstance(slot_key, str) or slot_key not in planned or slot_key in seen:
            _fail("REPLAY_MISMATCH", "Task replay entries do not uniquely match the run plan.")
        seen.add(slot_key)
        try:
            input_id = UUID(row["input_evidence_id"])
            freeze_id = UUID(row["freeze_evidence_id"])
            http_id = (
                UUID(row["agent_http_evidence_id"]) if row.get("agent_http_evidence_id") else None
            )
            initial_id = (
                UUID(row["initial_http_evidence_id"])
                if row.get("initial_http_evidence_id") else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise VerificationError(
                "MISSING_EVIDENCE", "Task replay references are invalid."
            ) from exc
        if (
            input_id not in records
            or freeze_id not in records
            or (http_id is not None and http_id not in records)
            or (initial_id is not None and initial_id not in records)
        ):
            _fail("MISSING_EVIDENCE", "Task replay references evidence absent from the manifest.")
        resolved.append((planned[slot_key], input_id, freeze_id, http_id, initial_id))
    if seen != set(planned):
        _fail("REPLAY_MISMATCH", "Task replay index does not cover every planned task.")
    schema_version = core_data.get("schema_version", "1.0.0")
    new_index = verification.get("schema_version") == "task-replay-v1"
    rule_version = _expected_rule_version(plan.template_version)
    valid_format = (
        (rule_version == "1" and schema_version == "1.0.0" and not new_index)
        or (rule_version == "2" and schema_version == "1.0.0" and not new_index)
        or (rule_version == "2" and schema_version == "1.1.0" and new_index)
        or (
            (rule_version, schema_version) in {("3", "1.2.0"), ("4", "1.3.0"), ("5", "1.4.0"), ("6", "1.5.0")} and new_index
            and plan.suite_id == "formal-evaluation-v1"
        )
    )
    if schema_version not in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"} and (
        plan.suite_id == "formal-evaluation-v1" or any(row[4] for row in resolved)
    ):
        valid_format = False
    if not valid_format:
        _fail(
            "RULE_VERSION_MISMATCH", "Report, assertion rules, and replay index versions disagree."
        )
    by_slot = {item[0].slot_id: item for item in resolved}
    return [by_slot[slot.slot_id] for slot in plan.slots]


def _verify_task_documents(
    aliases: dict[str, bytes],
    records: dict[UUID, EvidenceRecord],
    files: dict[str, bytes],
    tasks: list[tuple[Any, UUID, UUID, UUID | None, UUID | None]],
    expected_version: str,
    *,
    evaluated_at: str,
    require_http_refs: bool,
) -> tuple[list[RecordVerificationInput], list[Observation], dict[str, Any]]:
    try:
        snapshot_core = _json(aliases, "snapshot_core.json")
        review = _json(aliases, "claims_review.json")
        bindings = _json(aliases, "bindings.json")
        grants = _json(aliases, "access_grants.json")
        observations_raw = _json(aliases, "observations.json")
        policy = _json(aliases, "policy.json")
    except KeyError as exc:
        raise VerificationError("MISSING_FILE", "Bundle is missing a replay document.") from exc
    if not isinstance(observations_raw, list):
        _fail("REPLAY_MISMATCH", "Observation document must be a list.")
    try:
        observations = [Observation.model_validate(item) for item in observations_raw]
    except (TypeError, ValueError) as exc:
        raise VerificationError("REPLAY_MISMATCH", "Observation evidence is invalid.") from exc
    inputs: list[RecordVerificationInput] = []
    for slot, input_id, freeze_id, http_id, initial_id in tasks:
        input_record, freeze_record = records[input_id], records[freeze_id]
        if input_record.source != "record-verification-input" or (
            input_id != freeze_id and freeze_record.source != "report-freeze-verification-input"
        ):
            _fail(
                "EVIDENCE_INCONSISTENT", "Task input and freeze references have unexpected sources."
            )
        try:
            task_input = RecordVerificationInput.model_validate_json(files[input_record.path])
            frozen_input = RecordVerificationInput.model_validate_json(files[freeze_record.path])
        except (TypeError, ValueError) as exc:
            raise VerificationError(
                "REPLAY_MISMATCH", "Task verification input is invalid."
            ) from exc
        if not task_input.evm.observed_at <= frozen_input.evm.observed_at <= evaluated_at:
            _fail(
                "EVIDENCE_INCONSISTENT", "Freeze time falls outside the task and report interval."
            )
        if task_input.slot != slot or frozen_input.slot != slot:
            _fail("EVIDENCE_INCONSISTENT", "Task input does not match its planned slot.")
        if task_input.model_dump(exclude={"evm"}) != frozen_input.model_dump(exclude={"evm"}):
            _fail(
                "EVIDENCE_INCONSISTENT", "Freeze input changes task facts outside chain evidence."
            )
        if (
            task_input.rule_version != expected_version
            or frozen_input.rule_version != expected_version
        ):
            _fail("RULE_VERSION_MISMATCH", "Task evidence does not use the plan's assertion rules.")
        if frozen_input.evm.error_reason:
            _fail("EVIDENCE_INCONSISTENT", "Freeze input contains an unresolved chain error.")
        original_result = verify_record(task_input, (input_id,))
        frozen_result = verify_record(frozen_input, (input_id,))
        historical_rpc_unknown = preserve_rpc_unknown(task_input, original_result)
        if frozen_input.evm.candidate_tx_hash != task_input.evm.candidate_tx_hash and not (
            historical_rpc_unknown
            and task_input.slot.capability_id == "get_tx_status"
            and task_input.evm.candidate_tx_hash is None
            and frozen_input.evm.candidate_tx_hash == task_input.slot.task.query_tx_hash
        ):
            _fail("EVIDENCE_INCONSISTENT", "Freeze input changed the task's candidate transaction.")
        if not historical_rpc_unknown and (
            [(item.rule_id, item.outcome, item.reason_code) for item in original_result.assertions]
            != [(item.rule_id, item.outcome, item.reason_code) for item in frozen_result.assertions]
            or original_result.task_link != frozen_result.task_link
        ):
            _fail("EVIDENCE_INCONSISTENT", "Freeze evidence changes the task's original judgement.")
        if task_input.snapshot.core.model_dump(mode="json") != snapshot_core:
            _fail("EVIDENCE_INCONSISTENT", "Snapshot document differs from task input.")
        if task_input.review.model_dump(mode="json") != review:
            _fail("EVIDENCE_INCONSISTENT", "Claim review differs from task input.")
        task_observations = [item for item in observations if item.slot_id == slot.slot_id]
        if not task_observations:
            _fail("EVIDENCE_INCONSISTENT", "Task has no observations in the frozen bundle.")
        if any(item.slot_id != slot.slot_id for item in observations) and len(tasks) == 1:
            _fail("EVIDENCE_INCONSISTENT", "Observation references an unplanned task.")
        if http_id is None:
            if task_input.agent_http is not None:
                if require_http_refs:
                    _fail(
                        "MISSING_EVIDENCE", "Frozen Agent HTTP response has no referenced evidence."
                    )
                matching = False
                for record in records.values():
                    if record.source != "agent-task-response":
                        continue
                    try:
                        raw_http = strict_json(files[record.path])
                    except (UnicodeError, ValueError, json.JSONDecodeError):
                        continue
                    if raw_http == task_input.agent_http:
                        matching = True
                        break
                if not matching:
                    _fail(
                        "MISSING_EVIDENCE",
                        "No committed HTTP evidence matches the frozen response.",
                    )
        else:
            http_record = records[http_id]
            if http_record.source != "agent-task-response" or task_input.agent_http is None:
                _fail("EVIDENCE_INCONSISTENT", "Agent HTTP reference has an unexpected source.")
            try:
                raw_http = strict_json(files[http_record.path])
            except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
                raise VerificationError(
                    "INVALID_JSON", "Agent HTTP evidence is not valid JSON."
                ) from exc
            if raw_http != task_input.agent_http:
                _fail("EVIDENCE_INCONSISTENT", "Agent HTTP evidence differs from replay input.")
        if initial_id is None:
            if task_input.initial_agent_http is not None:
                _fail("MISSING_EVIDENCE", "Initial HTTP response has no committed reference.")
        else:
            initial_record = records[initial_id]
            initial_observations = [
                item for item in task_observations
                if item.attempt_no == 1 and not item.diagnostic_only
                and item.dispatch_state != "SETTLED"
            ]
            if (
                initial_record.source != "agent-task-response"
                or task_input.initial_agent_http is None
                or _json(files, initial_record.path) != task_input.initial_agent_http
                or len(initial_observations) != 1
                or initial_id not in initial_observations[0].evidence_refs
                or task_input.initial_agent_http.get("method") != "POST"
                or task_input.initial_agent_http.get("request_id") != slot.task.request_id
                or any(
                    getattr(initial_observations[0], field)
                    != task_input.initial_agent_http.get(field)
                    for field in ("started_at", "ended_at", "http_status", "latency_ms")
                )
            ):
                _fail("EVIDENCE_INCONSISTENT", "Initial HTTP evidence differs from the task.")
        inputs.append(task_input)
    def unique_documents(field: str, identifier: str) -> list[dict[str, Any]]:
        expected: dict[str, dict[str, Any]] = {}
        for item in inputs:
            value = getattr(item, field)
            if value is None:
                continue
            key, body = str(getattr(value, identifier)), value.model_dump(mode="json")
            if key in expected and expected[key] != body:
                _fail("EVIDENCE_INCONSISTENT", "Shared context ID contains different documents.")
            expected[key] = body
        return list(expected.values())

    expected_bindings = unique_documents("binding", "binding_id")
    expected_grants = unique_documents("grant", "grant_id")
    if bindings != expected_bindings or grants != expected_grants:
        _fail("EVIDENCE_INCONSISTENT", "Binding or access grant document differs from task input.")
    if {item.slot_id for item in observations} != {task[0].slot_id for task in tasks}:
        _fail("EVIDENCE_INCONSISTENT", "Observation document contains missing or unplanned tasks.")
    return inputs, observations, policy


def _verify_publication_context(
    manifest: EvidenceManifest,
    receipt: AnchorReceipt,
    core: ReportCore,
    platform_instance_ids: Iterable[str],
) -> None:
    publication = manifest.publication
    # The receipt is outside the report commitment, so it cannot replace committed identities.
    if (
        receipt.trusted_chain_key != publication.trusted_chain_key
        or receipt.chain_instance_id != publication.chain.instance_hash
        or receipt.contract != publication.contract
        or receipt.publisher != publication.publisher
        or core.previous_report_hash != publication.previous_report_hash
        or any(identifier != publication.platform_instance_id for identifier in platform_instance_ids)
    ):
        _fail("EVIDENCE_INCONSISTENT", "Task, report, receipt and publication context disagree.")


def _verify_anchor(
    rpc_url: str, manifest: EvidenceManifest, receipt: AnchorReceipt, report_hash: str, core
) -> dict[str, Any]:
    if receipt.status != "CONFIRMED":
        return {"status": "NOT_CHECKED", "reason": "bundle has no confirmed anchor"}
    if not rpc_url:
        return {"status": "NOT_CHECKED", "reason": "trusted RPC was not configured"}
    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        tx_hash, block_hash, block_number = (
            receipt.tx_hash,
            receipt.block_hash,
            receipt.block_number,
        )
        if tx_hash is None or block_hash is None or block_number is None:
            _fail("ANCHOR_RECEIPT_MISMATCH", "Confirmed anchor receipt is incomplete.")
        chain = manifest.publication.chain
        if (
            str(web3.eth.chain_id) != chain.chain_id
            or web3.eth.get_block(0)["hash"].to_0x_hex().lower() != chain.genesis_hash
        ):
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
            _fail(
                "ANCHOR_TX_MISMATCH",
                "Anchor transaction is not a successful call to the committed contract.",
            )
        if (
            mined["blockHash"].to_0x_hex().lower() != block_hash
            or str(mined["blockNumber"]) != block_number
        ):
            _fail(
                "ANCHOR_RECEIPT_MISMATCH",
                "Committed anchor receipt does not match the trusted chain.",
            )
        head = web3.eth.block_number - int(mined["blockNumber"]) + 1
        if head < manifest.publication.confirmation_depth:
            _fail("ANCHOR_NOT_FINAL", "Anchor confirmation depth is not satisfied.")
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(manifest.publication.contract), abi=ANCHOR_ABI
        )
        exists, policy, previous, sequence = contract.functions.lookup(
            Web3.to_checksum_address(manifest.publication.publisher),
            _bytes32(core.agent_key_hash),
            _bytes32(report_hash),
        ).call()
        if (
            not exists
            or "0x" + bytes(policy).hex() != core.policy_hash
            or "0x" + bytes(previous).hex() != core.previous_report_hash
            or str(sequence) != str(receipt.sequence)
        ):
            _fail(
                "ANCHOR_RECORD_MISMATCH", "The trusted contract record does not match the report."
            )
        return {"status": "CONFIRMED", "confirmations": head}
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(
            "RPC_UNAVAILABLE", "Trusted RPC could not verify the anchor."
        ) from exc


def _live_rpc_results(web3: Web3, data: RecordVerificationInput) -> dict[str, Any]:
    """Collect only chain reads required to replay a task; never calls the Agent."""
    from web3.types import RPCEndpoint

    results: dict[str, Any] = {}

    def read(label: str, method: str, params: list[Any]) -> Any:
        reply = web3.provider.make_request(RPCEndpoint(method), params)
        if not isinstance(reply, dict) or "error" in reply or "result" not in reply:
            raise OSError("RPC response unavailable")
        results[label] = reply["result"]
        return reply["result"]

    task, facts = data.slot.task, data.slot.expected
    read("chain_id", "eth_chainId", [])
    read("genesis", "eth_getBlockByNumber", ["0x0", False])
    read("head", "eth_getBlockByNumber", ["latest", False])
    registry = facts.agent_ref.registry_address
    read("registry_code", "eth_getCode", [registry, results["head"]["number"]])
    if task.target_contract is not None:
        read("record_code", "eth_getCode", [task.target_contract, results["head"]["number"]])
    read(
        "deployment_instance",
        "eth_call",
        [
            {"to": registry, "data": hash_bytes(b"deploymentInstanceId()")[:10]},
            results["head"]["number"],
        ],
    )
    read("pre_dispatch_block", "eth_getBlockByNumber", [hex(int(facts.pre_dispatch_block)), False])
    witness = data.registry_witness
    if witness is not None:
        read(
            "dispatch_block",
            "eth_getBlockByNumber",
            [hex(int(witness.snapshot_core.read_block_number)), False],
        )
    if task.capability_id != "anchor_record":
        assert task.read_block_number is not None
        read("read_block", "eth_getBlockByHash", [task.read_block_hash, False])
        read("read_canonical", "eth_getBlockByNumber", [hex(int(task.read_block_number)), False])
    if task.capability_id == "verify_record":
        assert task.target_contract is not None
        assert task.record_executor is not None and task.record_request_id is not None
        read(
            "record_call",
            "eth_call",
            [
                {
                    "to": task.target_contract,
                    "data": hash_bytes(b"getRecord(address,bytes32)")[:10]
                    + task.record_executor[2:].rjust(64, "0")
                    + task.record_request_id[2:],
                },
                hex(int(task.read_block_number or "0")),
            ],
        )
        read(
            "read_canonical",
            "eth_getBlockByNumber",
            [hex(int(task.read_block_number or "0")), False],
        )
    candidate = (
        task.query_tx_hash if task.capability_id == "get_tx_status" else data.evm.candidate_tx_hash
    )
    if candidate is not None:
        read("transaction", "eth_getTransactionByHash", [candidate])
        receipt = read("receipt", "eth_getTransactionReceipt", [candidate])
        if receipt is not None:
            read("receipt_block", "eth_getBlockByHash", [receipt["blockHash"], False])
            read("receipt_canonical", "eth_getBlockByNumber", [receipt["blockNumber"], False])
    read("head", "eth_getBlockByNumber", ["latest", False])
    return results


def _live_task_check(
    rpc_url: str | None,
    data: RecordVerificationInput,
    historical_outcome: Outcome,
    historical_reason: Reason | None,
    evidence_id: UUID,
) -> dict[str, Any]:
    if historical_outcome == Outcome.NOT_APPLICABLE:
        return {"status": "NOT_REQUIRED", "reason_code": historical_reason}
    if data.rule_version in {"3", "4", "5", "6"} and data.slot.case_kind == "negative":
        return {
            "status": "NOT_REQUIRED", "reason_code": historical_reason,
            "reason": "frozen HTTP rejection is replayed without sending the invalid request",
        }
    original = verify_record(data, (evidence_id,))
    if any(
        item.rule_id == "agent.service" and item.outcome == Outcome.FAIL
        for item in original.assertions
    ) and not any(item.rule_id.startswith("chain.") for item in original.assertions):
        return {"status": "NOT_REQUIRED", "reason_code": historical_reason}
    if not rpc_url:
        return {
            "status": "NOT_CHECKED",
            "reason_code": None,
            "reason": "trusted task RPC was not configured",
        }
    if data.slot.capability_id == "anchor_record" and data.evm.candidate_tx_hash is None:
        return {
            "status": "NOT_CHECKED",
            "reason_code": None,
            "reason": "no candidate transaction hash was frozen",
        }
    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        results = _live_rpc_results(web3, data)
        live_evidence = data.evm.model_copy(update={"results": results, "error_reason": None})
        live_input = data.model_copy(update={"evm": live_evidence})
        result = verify_record(live_input, (evidence_id,))
    except Exception:
        return {"status": "UNKNOWN", "reason_code": Reason.PLATFORM_RPC_ERROR}
    chain_identity = next(
        (item for item in result.assertions if item.rule_id == "chain.identity"), None
    )
    if (
        result.outcome == Outcome.UNKNOWN
        or chain_identity is None
        or chain_identity.outcome != Outcome.PASS
    ):
        return {
            "status": "UNKNOWN",
            "outcome": result.outcome,
            "reason_code": chain_identity.reason_code
            if chain_identity is not None and chain_identity.outcome != Outcome.PASS
            else result.reason_code or Reason.MISSING_EVIDENCE,
            "historical_outcome": historical_outcome,
            "historical_reason_code": historical_reason,
        }
    if historical_outcome == Outcome.UNKNOWN:
        status = "RESOLVED"
    elif result.outcome == historical_outcome and result.reason_code == historical_reason:
        status = "CONFIRMED"
    else:
        status = "CONFLICT"
    return {
        "status": status,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "historical_outcome": historical_outcome,
        "historical_reason_code": historical_reason,
    }


def verify_bundle(
    path: str,
    *,
    rpc_url: str | None = None,
    task_rpc_url: str | None = None,
) -> dict[str, Any]:
    files = _read_zip(path)
    core_data = _json(files, "report_core.json")
    manifest_data = _json(files, "evidence_manifest.json")
    receipt_data = _json(files, "anchor_receipt.json")
    if not isinstance(core_data, dict):
        _fail("SCHEMA_ERROR", "Report core must be an object.")
    try:
        manifest = EvidenceManifest.model_validate(manifest_data)
        receipt = AnchorReceipt.model_validate(receipt_data)
    except ValueError as exc:
        raise VerificationError(
            "SCHEMA_ERROR", "Bundle documents do not match the published schemas."
        ) from exc
    report_hash = hash_json(core_data)
    manifest_hash = hash_json(manifest.model_dump(mode="json"))
    if (
        core_data.get("evidence_manifest_hash") != manifest_hash
        or receipt.report_hash != report_hash
    ):
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
        if document.path not in files or str(document.evidence_id) not in {
            str(item.evidence_id) for item in manifest.evidence
        }:
            _fail("MISSING_EVIDENCE", f"Bundle is missing committed document {document.path}.")
        record = next(
            item for item in manifest.evidence if item.evidence_id == document.evidence_id
        )
        if files[document.path] != files[record.path]:
            _fail("CONTENT_HASH_MISMATCH", f"Document alias {document.path} differs from its blob.")
        aliases[document.path] = files[document.path]
    allowed = {
        "report_core.json",
        "evidence_manifest.json",
        "anchor_receipt.json",
        "FORMAT.md",
        *expected,
        *aliases,
    }
    if set(files) - allowed:
        _fail("UNCOMMITTED_FILE", "Bundle contains a file absent from the manifest.")

    plan_selector = _json(aliases, "run_plan.json")
    if core_data.get("schema_version") == "1.6.0" or (
        isinstance(plan_selector, dict) and plan_selector.get("suite_id") == "public-readonly-v1"
    ):
        from .public_bundle import verify_public_bundle

        return verify_public_bundle(
            core_data, manifest, receipt, aliases, files, report_hash=report_hash,
            manifest_hash=manifest_hash, rpc_url=rpc_url,
        )

    try:
        from reputation_core.models import ReportTaskResult

        plan_data = _json(aliases, "run_plan.json")
        if not isinstance(plan_data, dict):
            _fail("REPLAY_MISMATCH", "Run plan must be an object.")
        expected_version = _expected_rule_version(plan_data.get("template_version"))
        core_schema = core_data.get("schema_version", "1.0.0")
        if core_schema not in {"1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            _fail("RULE_VERSION_MISMATCH", "Report uses an unsupported schema version.")
        if core_schema == "1.0.0" and ("task_results" in core_data or "task_counts" in core_data):
            _fail(
                "RULE_VERSION_MISMATCH", "Legacy report schema cannot carry task replay summaries."
            )
        reported_tasks = core_data.get("task_results", [])
        if core_schema in {"1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"} and (
            not isinstance(reported_tasks, list)
            or not reported_tasks
            or not isinstance(core_data.get("task_counts"), dict)
        ):
            _fail("RULE_VERSION_MISMATCH", "Task replay reports require results and counts.")
        if (
            core_schema in {"1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"}
            and isinstance(reported_tasks, list)
            and any(
                not isinstance(item, dict) or item.get("rule_version") != expected_version
                for item in reported_tasks
            )
        ):
            _fail("RULE_VERSION_MISMATCH", "Report task results use a different assertion version.")
        plan = RunPlan.model_validate(plan_data)
        if len(plan.slots) != 1 and core_schema not in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            _fail("REPLAY_MISMATCH", "Historical reports support one task per run.")
        verification = _json(aliases, "verification.json")
        records = _record_by_id(manifest)
        tasks = _bundle_tasks(verification, plan, core_data, records, files)
        try:
            core = ReportCore.model_validate(core_data)
        except ValueError as exc:
            raise VerificationError(
                "REPLAY_MISMATCH", "Report task results or counts are invalid."
            ) from exc
        if hash_json(core.model_dump(mode="json")) != report_hash:
            _fail("CONTENT_HASH_MISMATCH", "Report core is not in its canonical wire form.")
        inputs, observations, policy = _verify_task_documents(
            aliases,
            records,
            files,
            tasks,
            expected_version,
            evaluated_at=core.evaluated_at,
            require_http_refs=verification.get("schema_version") == "task-replay-v1",
        )
        _verify_publication_context(
            manifest, receipt, core, (data.platform_instance_id for data in inputs)
        )
        referenced_ids = set(plan.planning_evidence_refs)
        for task_input in inputs:
            referenced_ids.update(task_input.snapshot.evidence_refs)
            referenced_ids.update(task_input.review.mapping_evidence_ids)
            if task_input.binding is not None:
                referenced_ids.update(task_input.binding.verification_evidence)
        for observation in observations:
            referenced_ids.update(observation.evidence_refs)
        referenced_ids.update(
            evidence_id
            for _, input_id, freeze_id, http_id, initial_id in tasks
            for evidence_id in (input_id, freeze_id, http_id, initial_id)
            if evidence_id is not None
        )
        if not referenced_ids.issubset(records):
            _fail("MISSING_EVIDENCE", "A frozen task references evidence absent from the manifest.")
        input_ids = [entry[1] for entry in tasks]
        results = [
            verify_record(task_input, (input_id,))
            for task_input, input_id in zip(inputs, input_ids, strict=True)
        ]
        computed_assertions = tuple(
            sorted(
                (assertion for result in results for assertion in result.assertions),
                key=lambda item: str(item.assertion_id),
            )
        )
        assertion_document = _json(aliases, "assertions.json")
        if not isinstance(assertion_document, list):
            _fail("REPLAY_MISMATCH", "Assertions document must be a list.")
        try:
            frozen_assertions = tuple(
                AssertionResult.model_validate(item) for item in assertion_document
            )
        except (TypeError, ValueError) as exc:
            raise VerificationError("REPLAY_MISMATCH", "Frozen assertions are invalid.") from exc
        if computed_assertions != frozen_assertions or computed_assertions != core.assertions:
            _fail("REPLAY_MISMATCH", "Recomputed task assertions differ from the report.")

        computed_counts = {outcome: 0 for outcome in Outcome}
        expected_tasks = []
        for (slot, input_id, _, _, _), task_input, result in zip(tasks, inputs, results, strict=True):
            computed_counts[result.outcome] += 1
            expected_tasks.append(
                ReportTaskResult(
                    slot_id=slot.slot_id,
                    capability_id=slot.capability_id,
                    outcome=result.outcome,
                    reason_code=result.reason_code,
                    rule_version=task_input.rule_version,
                    input_evidence_id=input_id,
                )
            )
        if core.schema_version in {"1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            if (
                tuple(expected_tasks) != core.task_results
                or core.task_counts is None
                or core.task_counts.model_dump(mode="json")
                != {outcome.value: count for outcome, count in computed_counts.items()}
            ):
                _fail(
                    "REPLAY_MISMATCH", "Recomputed task results or counts differ from the report."
                )
        elif core.task_results or core.task_counts is not None:
            _fail(
                "RULE_VERSION_MISMATCH",
                "Legacy report unexpectedly contains task replay summaries.",
            )

        rebuilt = build_report(
            plan,
            tuple(inputs) if core.schema_version in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"} else inputs[0],
            tuple(input_ids) if core.schema_version in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"} else input_ids[0],
            tuple(observations),
            policy,
            evaluated_at=core.evaluated_at,
            code_version=core.code_version,
            manifest_hash=manifest_hash,
            previous_report_hash=core.previous_report_hash,
            report_schema_version="1.5.0" if core.schema_version == "1.5.0"
            else "1.4.0" if core.schema_version == "1.4.0"
            else "1.3.0" if core.schema_version == "1.3.0"
            else "1.2.0" if core.schema_version == "1.2.0" else None,
        )
        if core.schema_version == "1.0.0" and rebuilt.schema_version == "1.1.0":
            rebuilt = rebuilt.model_copy(
                update={"schema_version": "1.0.0", "task_results": (), "task_counts": None}
            )
        if rebuilt != core:
            _fail("REPLAY_MISMATCH", "Recomputed report statistics or context differ.")
    except VerificationError:
        raise
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError(
            "REPLAY_MISMATCH", "Bundle could not be replayed from its committed inputs."
        ) from exc
    live_rpc = task_rpc_url or rpc_url
    replayed_tasks = []
    for task_ref, task_input, result in zip(tasks, inputs, results, strict=True):
        slot, input_id = task_ref[0], task_ref[1]
        live = _live_task_check(
            live_rpc,
            task_input,
            result.outcome,
            result.reason_code,
            input_id,
        )
        replayed_tasks.append(
            {
                "slot_id": str(slot.slot_id),
                "capability_id": slot.capability_id,
                "outcome": result.outcome,
                "reason_code": result.reason_code,
                "rule_version": task_input.rule_version,
                "live_chain": live,
            }
        )
    anchor = _verify_anchor(rpc_url or "", manifest, receipt, report_hash, core)
    return {
        "status": "PASS",
        "offline": "PASS",
        "limitations": list(VERIFICATION_LIMITATIONS),
        "report_hash": report_hash,
        "task_results": replayed_tasks,
        "task_counts": {outcome.value: computed_counts[outcome] for outcome in Outcome},
        "task_count_comparison": "MATCH"
        if core.schema_version in {"1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"}
        else "NOT_AVAILABLE_LEGACY_REPORT",
        "assessment_comparison": "MATCH"
        if core.schema_version in {"1.3.0", "1.4.0", "1.5.0"} else "NOT_AVAILABLE_LEGACY_REPORT",
        **({
            "evidence_sufficiency": core.evidence_sufficiency.model_dump(mode="json"),
            "risk_assessment": core.risk_assessment.model_dump(mode="json"),
        } if core.evidence_sufficiency is not None and core.risk_assessment is not None else {}),
        "anchor": anchor,
    }
