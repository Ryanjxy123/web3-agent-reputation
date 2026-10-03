"""Deterministic anchor_record rules. No database, RPC client, environment or live clock."""

import re
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from .binding import agent_key_hash, endpoint_hash, signatures_match
from .evidence import hash_bytes, hash_json
from .models import (
    AssertionResult,
    Outcome,
    Reason,
    RecordVerificationInput,
    RecordVerificationResult,
    TaskLink,
)

EVENT_TOPIC = hash_bytes(b"RecordAnchored(address,bytes32,bytes32)")
CALL_SELECTOR = hash_bytes(b"anchorRecord(bytes32,bytes32)")[:10]
BUSINESS_RULES = (
    "tx.exists",
    "tx.chain",
    "tx.executor",
    "tx.target",
    "tx.calldata",
    "receipt.success",
    "receipt.canonical",
    "receipt.finality",
    "record.event",
    "record.emitter",
    "record.executor",
    "record.request",
    "record.hash",
    "record.window",
    "record.location",
)


def quantity(value) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise ValueError("invalid RPC quantity")
    return int(value, 16)


def hex_data(value, size: int | None = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("invalid RPC bytes")
    if size is not None and len(value) != 2 + size * 2:
        raise ValueError("invalid RPC byte length")
    return value.lower()


def seconds(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


def verify_record(
    data: RecordVerificationInput, evidence_refs: tuple[UUID, ...]
) -> RecordVerificationResult:
    slot, snapshot, proof = data.slot, data.snapshot, data.binding
    # Raw JSON-RPC is deliberately decoded at each rule boundary below.
    rpc = cast(dict[str, Any], data.evm.results)
    facts, task = slot.expected, slot.task
    assertions = []
    event: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None

    def emit(rule, passed, reason, expected, observed, *, unknown=False, critical=False):
        outcome = Outcome.PASS if passed else Outcome.UNKNOWN if unknown else Outcome.FAIL
        # Stable result identifiers only; unpredictable execution challenges are generated outside core.
        identifier = UUID(
            bytes=bytes.fromhex(hash_json([str(slot.slot_id), rule, "1"])[2:34]), version=4
        )
        assertion = AssertionResult(
            assertion_id=identifier,
            slot_id=slot.slot_id,
            rule_id=rule,
            rule_version="1",
            outcome=outcome,
            reason_code=None if passed else reason,
            expected=expected,
            observed=observed,
            evidence_refs=evidence_refs,
            critical=critical,
        )
        assertions.append(assertion)
        return passed

    def finish():
        failures = [item for item in assertions if item.outcome == Outcome.FAIL]
        unknowns = [item for item in assertions if item.outcome == Outcome.UNKNOWN]
        outcome = Outcome.FAIL if failures else Outcome.UNKNOWN if unknowns else Outcome.PASS
        reason = (
            Reason.SEMANTIC_MISMATCH if failures else unknowns[0].reason_code if unknowns else None
        )
        matched = outcome == Outcome.PASS
        block_number, block_hash, log_index = None, None, None
        if matched:
            assert receipt is not None and event is not None
            block_number, block_hash = (
                str(quantity(receipt["blockNumber"])),
                hex_data(receipt["blockHash"], 32),
            )
            log_index = event["index"]
        link = TaskLink(
            request_id=task.request_id,
            candidate_tx_hash=data.evm.candidate_tx_hash,
            verified_tx_hash=data.evm.candidate_tx_hash if matched else None,
            executor=facts.executor,
            block_number=block_number,
            block_hash=block_hash,
            log_index=log_index,
            match_status=outcome,
        )
        return RecordVerificationResult(
            assertions=tuple(assertions),
            task_link=link,
            outcome=outcome,
            reason_code=reason,
            critical_conflict=any(item.critical for item in failures),
        )

    def unavailable(reason):
        existing = {item.rule_id for item in assertions}
        for rule in BUSINESS_RULES:
            if rule not in existing:
                emit(rule, False, reason, None, None, unknown=True)
        return finish()

    if not evidence_refs:
        emit(
            "evidence.available",
            False,
            Reason.MISSING_EVIDENCE,
            "saved verification input",
            None,
            unknown=True,
        )
        return unavailable(Reason.MISSING_EVIDENCE)
    context_ok = emit(
        "context.snapshot",
        snapshot.snapshot_hash == hash_json(snapshot.core.model_dump(mode="json"))
        and snapshot.snapshot_hash == facts.snapshot_hash == data.review.snapshot_hash
        and facts.agent_ref == snapshot.core.agent_ref,
        Reason.IDENTITY_CHANGED,
        facts.snapshot_hash,
        snapshot.snapshot_hash,
        unknown=True,
    )
    context_ok &= emit(
        "context.mapping",
        slot.capability_id in data.review.confirmed_claims
        and data.review.review_version == data.review_version,
        Reason.MAPPING_UNCONFIRMED,
        slot.capability_id,
        list(data.review.confirmed_claims),
        unknown=True,
    )
    dispatched = data.dispatch_started_at
    intent_ok = (
        dispatched is not None
        and snapshot.core.captured_at
        <= facts.window_start
        <= data.intent_persisted_at
        <= dispatched
        <= task.deadline
        and data.dispatch_payload_hash == hash_json(task.model_dump(mode="json"))
        and slot.synthetic_input is not None
    )
    context_ok &= emit(
        "task.intent",
        intent_ok,
        data.execution_reason or Reason.DISPATCH_UNCERTAIN,
        hash_json(task.model_dump(mode="json")),
        data.dispatch_payload_hash,
        unknown=True,
    )
    witness = data.registry_witness
    ignored = {"captured_at", "read_block_number", "read_block_hash"}
    identity_ok = (
        witness is not None
        and dispatched is not None
        and witness.snapshot_core.captured_at <= dispatched
        and witness.snapshot_core.model_dump(exclude=ignored)
        == snapshot.core.model_dump(exclude=ignored)
        and witness.owner_code == "0x"
        and witness.executor_code == "0x"
    )
    context_ok &= emit(
        "binding.identity",
        identity_ok,
        Reason.IDENTITY_CHANGED,
        snapshot.core.owner,
        witness.snapshot_core.owner if witness else None,
        unknown=True,
    )
    binding_ok = (
        proof is not None
        and proof.status == "VERIFIED"
        and proof.binding_id == facts.binding_id
        and proof.owner == snapshot.core.owner
        and proof.message.executor == facts.executor
        and proof.message.agent_key_hash == agent_key_hash(facts.agent_ref)
        and proof.message.snapshot_hash == snapshot.snapshot_hash
        and proof.message.execution_chain_id == facts.execution_chain.chain_id
        and proof.message.execution_chain_instance_hash == facts.execution_chain.instance_hash
        and proof.domain_registry == facts.agent_ref.registry_address
        and proof.domain_chain_id == facts.agent_ref.chain_id
        and proof.domain_salt == data.platform_instance_id
        and any(
            endpoint_hash(endpoint) == proof.message.endpoint_hash
            for endpoint in snapshot.core.endpoints
        )
        and dispatched is not None
        and proof.message.issued_at <= seconds(dispatched) <= proof.message.deadline
        and datetime.fromisoformat(task.deadline).timestamp() <= proof.message.deadline
        and signatures_match(proof)
    )
    context_ok &= emit(
        "binding.signatures",
        binding_ok,
        Reason.BINDING_UNVERIFIED,
        facts.executor,
        proof.message.executor if proof else None,
        unknown=True,
    )
    grant = data.grant
    grant_ok = (
        grant is not None
        and grant.grant_id == slot.grant_id
        and grant.snapshot_hash == snapshot.snapshot_hash
        and slot.capability_id in grant.capabilities
        and task.target_contract in grant.contract_allowlist
        and task.chain_instance_id in grant.chain_instances
        and "POST" in grant.methods
        and "/tasks" in grant.paths
        and proof is not None
        and any(
            endpoint.endpoint_id in grant.endpoint_ids
            and endpoint_hash(endpoint) == proof.message.endpoint_hash
            for endpoint in snapshot.core.endpoints
        )
        and dispatched is not None
        and dispatched <= task.deadline <= grant.expires_at
    )
    context_ok &= emit(
        "task.authorization",
        grant_ok,
        Reason.ACCESS_NOT_GRANTED,
        str(slot.grant_id),
        str(grant.grant_id) if grant else None,
        unknown=True,
    )
    try:
        identity = {
            "chain_id": str(quantity(rpc["chain_id"])),
            "genesis_hash": hex_data(rpc["genesis"]["hash"], 32),
            "deployment_instance_id": hex_data(rpc["deployment_instance"]),
            "registry_code_hash": hash_bytes(bytes.fromhex(hex_data(rpc["registry_code"])[2:])),
        }
        observed_instance = hash_json(identity)
        context_ok &= emit(
            "chain.identity",
            observed_instance == facts.execution_chain.instance_hash,
            Reason.CHAIN_INSTANCE_CHANGED,
            facts.execution_chain.instance_hash,
            observed_instance,
            unknown=True,
        )
        code_hash = hash_bytes(bytes.fromhex(hex_data(rpc["record_code"])[2:]))
        context_ok &= emit(
            "chain.record_code",
            facts.target_code_hash is not None and code_hash == facts.target_code_hash,
            Reason.CHAIN_INSTANCE_CHANGED if facts.target_code_hash else Reason.MISSING_EVIDENCE,
            facts.target_code_hash,
            code_hash,
            unknown=True,
        )
        pre_hash = hex_data(rpc["pre_dispatch_block"]["hash"], 32)
        context_ok &= emit(
            "chain.pre_dispatch",
            pre_hash == facts.pre_dispatch_block_hash,
            Reason.STALE_EVIDENCE,
            facts.pre_dispatch_block_hash,
            pre_hash,
            unknown=True,
        )
        dispatch_hash = hex_data(rpc["dispatch_block"]["hash"], 32)
        context_ok &= emit(
            "chain.dispatch_head",
            witness is not None and dispatch_hash == witness.snapshot_core.read_block_hash,
            Reason.STALE_EVIDENCE,
            witness.snapshot_core.read_block_hash if witness else None,
            dispatch_hash,
            unknown=True,
        )
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        emit(
            "chain.available",
            False,
            data.evm.error_reason or Reason.PLATFORM_RPC_ERROR,
            "complete chain identity reads",
            None,
            unknown=True,
        )
        context_ok = False
    if not context_ok:
        reason = next(item.reason_code for item in assertions if item.outcome == Outcome.UNKNOWN)
        return unavailable(reason)
    tx = rpc.get("transaction")
    if not isinstance(tx, dict):
        return unavailable(
            data.evm.error_reason or data.execution_reason or Reason.RPC_RECEIPT_NOT_FOUND
        )
    try:
        emit(
            "tx.exists",
            hex_data(tx["hash"], 32) == data.evm.candidate_tx_hash,
            Reason.SEMANTIC_MISMATCH,
            data.evm.candidate_tx_hash,
            tx["hash"],
            critical=True,
        )
        emit(
            "tx.chain",
            str(quantity(tx["chainId"])) == facts.execution_chain.chain_id,
            Reason.TX_WRONG_CHAIN,
            facts.execution_chain.chain_id,
            str(quantity(tx["chainId"])),
            critical=True,
        )
        emit(
            "tx.executor",
            hex_data(tx["from"], 20) == facts.executor,
            Reason.TX_WRONG_EXECUTOR,
            facts.executor,
            tx["from"],
            critical=True,
        )
        emit(
            "tx.target",
            hex_data(tx["to"], 20) == facts.target_contract,
            Reason.TX_WRONG_TARGET,
            facts.target_contract,
            tx["to"],
            critical=True,
        )
        expected_call = CALL_SELECTOR + task.request_id[2:] + task.record_hash[2:]
        emit(
            "tx.calldata",
            hex_data(tx["input"]) == expected_call,
            Reason.SEMANTIC_MISMATCH,
            expected_call,
            tx["input"],
            critical=True,
        )
        receipt = rpc.get("receipt")
        if not isinstance(receipt, dict):
            return unavailable(data.evm.error_reason or Reason.RPC_RECEIPT_NOT_FOUND)
        emit(
            "receipt.success",
            quantity(receipt["status"]) == 1,
            Reason.TX_REVERTED,
            1,
            quantity(receipt["status"]),
        )
        block = rpc.get("receipt_block")
        canonical = rpc.get("receipt_canonical")
        canonical_ok = (
            isinstance(block, dict)
            and isinstance(canonical, dict)
            and hex_data(block["hash"], 32)
            == hex_data(canonical["hash"], 32)
            == hex_data(receipt["blockHash"], 32)
            and quantity(block["number"]) == quantity(receipt["blockNumber"])
        )
        emit(
            "receipt.canonical",
            canonical_ok,
            Reason.PENDING_FINALITY,
            receipt["blockHash"],
            canonical.get("hash") if isinstance(canonical, dict) else None,
            unknown=True,
        )
        confirmations = quantity(rpc["head"]["number"]) - quantity(receipt["blockNumber"]) + 1
        emit(
            "receipt.finality",
            canonical_ok and confirmations >= facts.confirmation_depth,
            Reason.PENDING_FINALITY,
            facts.confirmation_depth,
            confirmations,
            unknown=True,
        )
        if quantity(receipt["status"]) == 0:
            return unavailable(Reason.TX_REVERTED)
        decoded = []
        for log in receipt["logs"]:
            topics = log.get("topics", [])
            if len(topics) != 3 or hex_data(topics[0], 32) != EVENT_TOPIC:
                continue
            indexed_executor = hex_data(topics[1], 32)
            if indexed_executor[2:26] != "0" * 24:
                continue
            if quantity(log["logIndex"]) > 2**53 - 1:
                raise ValueError("log index outside evidence range")
            decoded.append(
                {
                    "emitter": hex_data(log["address"], 20),
                    "executor": "0x" + indexed_executor[-40:],
                    "request": hex_data(topics[2], 32),
                    "record": hex_data(log["data"], 32),
                    "index": quantity(log["logIndex"]),
                    "raw": log,
                }
            )
        matching = [
            item
            for item in decoded
            if item["emitter"] == facts.target_contract
            and item["executor"] == facts.executor
            and item["request"] == task.request_id
        ]
        event = (
            matching[0]
            if len(matching) == 1
            else min(decoded, key=lambda item: item["index"])
            if decoded
            else None
        )
        emit(
            "record.event",
            event is not None and len(matching) <= 1,
            Reason.SEMANTIC_MISMATCH,
            EVENT_TOPIC,
            len(decoded),
            critical=True,
        )
        if event is None:
            return unavailable(Reason.SEMANTIC_MISMATCH)
        emit(
            "record.emitter",
            event["emitter"] == facts.target_contract,
            Reason.LOG_EMITTER_MISMATCH,
            facts.target_contract,
            event["emitter"],
            critical=True,
        )
        emit(
            "record.executor",
            event["executor"] == facts.executor,
            Reason.TX_WRONG_EXECUTOR,
            facts.executor,
            event["executor"],
            critical=True,
        )
        emit(
            "record.request",
            event["request"] == task.request_id,
            Reason.TASK_ID_MISMATCH,
            task.request_id,
            event["request"],
            critical=True,
        )
        emit(
            "record.hash",
            event["record"] == task.record_hash,
            Reason.RECORD_HASH_MISMATCH,
            task.record_hash,
            event["record"],
            critical=True,
        )
        raw = event["raw"]
        location = (
            hex_data(raw["transactionHash"], 32)
            == hex_data(receipt["transactionHash"], 32)
            == data.evm.candidate_tx_hash
            and hex_data(raw["blockHash"], 32)
            == hex_data(receipt["blockHash"], 32)
            == hex_data(tx["blockHash"], 32)
            and quantity(raw["blockNumber"]) == quantity(receipt["blockNumber"])
            and quantity(raw["transactionIndex"])
            == quantity(receipt["transactionIndex"])
            == quantity(tx["transactionIndex"])
            and raw.get("removed", False) is False
        )
        emit(
            "record.location",
            location,
            Reason.SEMANTIC_MISMATCH,
            data.evm.candidate_tx_hash,
            raw["transactionHash"],
            critical=True,
        )
        if isinstance(block, dict):
            lower_block = (
                max(int(facts.pre_dispatch_block), int(witness.snapshot_core.read_block_number))
                if witness
                else int(facts.pre_dispatch_block)
            )
            too_early = quantity(receipt["blockNumber"]) <= lower_block or quantity(
                block["timestamp"]
            ) < seconds(dispatched or facts.window_start)
            in_window = (
                witness is not None
                and not too_early
                and quantity(block["timestamp"]) <= seconds(facts.deadline)
            )
            emit(
                "record.window",
                in_window,
                Reason.SEMANTIC_MISMATCH if too_early else Reason.ACCEPTED_TASK_DEADLINE_EXCEEDED,
                {
                    "after_block": str(lower_block),
                    "time_window": [dispatched or facts.window_start, facts.deadline],
                },
                {
                    "block_number": str(quantity(receipt["blockNumber"])),
                    "timestamp": str(quantity(block["timestamp"])),
                },
                critical=too_early,
            )
        else:
            emit(
                "record.window",
                False,
                Reason.PENDING_FINALITY,
                [facts.window_start, facts.deadline],
                None,
                unknown=True,
            )
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return unavailable(data.evm.error_reason or Reason.SCHEMA_ERROR)
    return finish()
