"""Deterministic task rules over frozen Agent responses and independent RPC reads."""

import re
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from .binding import agent_key_hash, endpoint_hash, signatures_match
from .case_templates import REJECTION_CASES, mutated_payload
from .evidence import hash_bytes, hash_json
from .models import (
    AssertionResult,
    ControlledTaskView,
    Outcome,
    Reason,
    RecordVerificationInput,
    RecordVerificationResult,
    TaskEnvelope,
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


def transaction_evidence_reason(
    rpc: dict[str, Any], candidate: str, *, writing: bool
) -> Reason | None:
    """Separate malformed/contradictory RPC observations from genuine pending finality."""
    try:
        tx, receipt = rpc["transaction"], rpc["receipt"]
        if tx is None and receipt is None:
            return None
        if not isinstance(tx, dict) or receipt is not None and not isinstance(receipt, dict):
            raise ValueError("malformed transaction/receipt")
        tx_hash = hex_data(tx["hash"], 32)
        tx_chain = quantity(tx["chainId"])
        if writing:
            hex_data(tx["from"], 20)
            if tx["to"] is not None:
                hex_data(tx["to"], 20)
            hex_data(tx["input"])
        if tx_hash != candidate or tx_chain != quantity(rpc["chain_id"]):
            return Reason.EVIDENCE_INCONSISTENT
        if receipt is None:
            if (tx["blockHash"] is None) != (tx["blockNumber"] is None):
                return Reason.EVIDENCE_INCONSISTENT
            if tx["blockHash"] is not None:
                hex_data(tx["blockHash"], 32)
                quantity(tx["blockNumber"])
            return None
        for value in (tx, receipt):
            hex_data(value["blockHash"], 32)
            quantity(value["blockNumber"])
            if writing:
                quantity(value["transactionIndex"])
        receipt_hash = hex_data(receipt["transactionHash"], 32)
        if quantity(receipt["status"]) not in (0, 1) or (
            writing and not isinstance(receipt["logs"], list)
        ):
            raise ValueError("malformed receipt status/logs")
        if receipt_hash != tx_hash or any(
            (hex_data(tx[field], 32) != hex_data(receipt[field], 32))
            if field == "blockHash" else quantity(tx[field]) != quantity(receipt[field])
            for field in (("blockHash", "blockNumber", "transactionIndex") if writing
                          else ("blockHash", "blockNumber"))
        ):
            return Reason.EVIDENCE_INCONSISTENT
        block, canonical, head = rpc["receipt_block"], rpc["receipt_canonical"], rpc["head"]
        for value in (block, canonical, head):
            hex_data(value["hash"], 32)
            quantity(value["number"])
        if writing:
            quantity(block["timestamp"])
        if (
            hex_data(block["hash"], 32) != hex_data(receipt["blockHash"], 32)
            or quantity(block["number"]) != quantity(receipt["blockNumber"])
            or quantity(canonical["number"]) != quantity(receipt["blockNumber"])
            or quantity(head["number"]) < quantity(receipt["blockNumber"])
        ):
            return Reason.EVIDENCE_INCONSISTENT
        if (
            quantity(head["number"]) == quantity(canonical["number"])
            and hex_data(canonical["hash"], 32) == hex_data(receipt["blockHash"], 32)
            and hex_data(head["hash"], 32) != hex_data(canonical["hash"], 32)
        ):
            return Reason.EVIDENCE_INCONSISTENT
        # A different canonical block can be a reorg; the existing finality rule handles it.
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return Reason.PLATFORM_RPC_ERROR
    return None


def query_evidence_reason(rpc: dict[str, Any], task: TaskEnvelope) -> Reason | None:
    """Retain malformed fixed-block reads separately from a genuine canonical fork."""
    try:
        block, canonical = rpc["read_block"], rpc["read_canonical"]
        for value in (block, canonical):
            hex_data(value["hash"], 32)
            quantity(value["number"])
        if (
            hex_data(block["hash"], 32) != task.read_block_hash
            or str(quantity(block["number"])) != task.read_block_number
            or str(quantity(canonical["number"])) != task.read_block_number
        ):
            return Reason.EVIDENCE_INCONSISTENT
        if hex_data(canonical["hash"], 32) != task.read_block_hash:
            return Reason.STALE_EVIDENCE
        if task.capability_id == "verify_record":
            raw = hex_data(rpc["record_call"], 64)
            flag = int(raw[2:66], 16)
            if flag not in (0, 1) or (flag == 0) != (raw[66:] == "00" * 32):
                raise ValueError("invalid record lookup")
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return Reason.PLATFORM_RPC_ERROR
    return None


def preserve_rpc_unknown(
    data: RecordVerificationInput, result: RecordVerificationResult
) -> bool:
    """A later healthy RPC read cannot replace an already frozen platform evidence gap."""
    return result.outcome == Outcome.UNKNOWN and (
        data.rule_version in {"2", "3", "4", "5", "6"}
        and data.evm.error_reason == Reason.PLATFORM_RPC_ERROR
        or data.rule_version in {"5", "6"} and any(
            item.rule_id == "receipt.logs" and item.outcome == Outcome.UNKNOWN
            and item.reason_code in {Reason.EVIDENCE_INCONSISTENT, Reason.PLATFORM_RPC_ERROR}
            and item.expected is not None
            for item in result.assertions
        )
        or data.rule_version == "6" and any(
            item.rule_id in {"receipt.evidence", "query.evidence", "chain.available", "chain.identity", "chain.position"}
            and item.outcome == Outcome.UNKNOWN
            and item.reason_code in {
                Reason.EVIDENCE_INCONSISTENT, Reason.PLATFORM_RPC_ERROR, Reason.CHAIN_INSTANCE_CHANGED,
            }
            and item.expected is not None
            for item in result.assertions
        )
    )


def verify_record(
    data: RecordVerificationInput, evidence_refs: tuple[UUID, ...]
) -> RecordVerificationResult:
    slot, snapshot, proof = data.slot, data.snapshot, data.binding
    # Raw JSON-RPC is deliberately decoded at each rule boundary below.
    rpc = cast(dict[str, Any], data.evm.results)
    facts, task = slot.expected, slot.task
    read_only = slot.capability_id != "anchor_record"
    negative = data.rule_version in {"3", "4", "5", "6"} and slot.case_kind == "negative"
    business_rules = (
        ("functional.rejection",)
        if negative
        else
        (
            "query.response",
            "query.block",
            "query.parameters",
            "query.transaction",
            "query.status",
            "query.canonical",
        )
        if slot.capability_id == "get_tx_status"
        else ("query.response", "query.block", "query.record", "query.parameters")
        if read_only
        else BUSINESS_RULES
    )
    assertions = []
    event: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    version = data.rule_version
    if version in {"5", "6"} and not read_only and not negative:
        business_rules = (*business_rules, "receipt.logs")
    if version == "6" and slot.capability_id in {"anchor_record", "get_tx_status"} and not negative:
        business_rules = (*business_rules, "receipt.evidence")
    if version == "6" and read_only and not negative:
        business_rules = (*business_rules, "query.evidence")
    declared = snapshot.core.normalized_metadata.get("capabilities")
    declared_valid = (
        isinstance(declared, list)
        and 1 <= len(declared) <= 10
        and all(isinstance(item, str) and 1 <= len(item) <= 2000 for item in declared)
    )

    def emit(
        rule, passed, reason, expected, observed, *, unknown=False, critical=False, applicable=True
    ):
        outcome = (
            Outcome.NOT_APPLICABLE
            if not applicable
            else Outcome.PASS
            if passed
            else Outcome.UNKNOWN
            if unknown
            else Outcome.FAIL
        )
        # Stable result identifiers only; unpredictable execution challenges are generated outside core.
        identifier = UUID(
            bytes=bytes.fromhex(hash_json([str(slot.slot_id), rule, version])[2:34]), version=4
        )
        assertion = AssertionResult(
            assertion_id=identifier,
            slot_id=slot.slot_id,
            rule_id=rule,
            rule_version=version,
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
        not_applicable = [item for item in assertions if item.outcome == Outcome.NOT_APPLICABLE]
        outcome = (
            Outcome.FAIL
            if failures
            else Outcome.UNKNOWN
            if unknowns
            else Outcome.NOT_APPLICABLE
            if not_applicable
            else Outcome.PASS
        )
        priority = (
            Reason.CAPABILITY_EXPLICITLY_UNSUPPORTED,
            Reason.AGENT_SERVICE_ERROR,
            Reason.TX_REVERTED,
            Reason.AGENT_TASK_FAILED,
            Reason.SCHEMA_ERROR,
            Reason.TX_WRONG_CHAIN,
            Reason.TX_WRONG_EXECUTOR,
            Reason.TX_WRONG_TARGET,
            Reason.LOG_EMITTER_MISMATCH,
            Reason.TASK_ID_MISMATCH,
            Reason.RECORD_HASH_MISMATCH,
            Reason.ACCEPTED_TASK_DEADLINE_EXCEEDED,
        )
        reason = (
            (
                Reason.SEMANTIC_MISMATCH
                if version == "1"
                else min(
                    failures,
                    key=lambda item: priority.index(item.reason_code)
                    if item.reason_code in priority
                    else len(priority),
                ).reason_code
            )
            if failures
            else unknowns[0].reason_code
            if unknowns
            else not_applicable[0].reason_code
            if not_applicable
            else None
        )
        matched = outcome == Outcome.PASS
        block_number, block_hash, log_index = None, None, None
        if matched and not read_only and not negative:
            assert receipt is not None and event is not None
            block_number, block_hash = (
                str(quantity(receipt["blockNumber"])),
                hex_data(receipt["blockHash"], 32),
            )
            log_index = event["index"]
        elif matched and receipt is not None and not negative:
            block_number = str(quantity(receipt["blockNumber"]))
            block_hash = hex_data(receipt["blockHash"], 32)
        elif matched and slot.capability_id == "verify_record" and not negative:
            block_number, block_hash = task.read_block_number, task.read_block_hash
        link = TaskLink(
            capability_id=slot.capability_id,
            request_id=task.request_id,
            candidate_tx_hash=data.evm.candidate_tx_hash if not negative else None,
            verified_tx_hash=data.evm.candidate_tx_hash
            if matched and not negative and (not read_only or receipt is not None)
            else None,
            executor=facts.executor,
            block_number=block_number,
            block_hash=block_hash,
            log_index=log_index,
            match_status=outcome,
            completion_kind="rejection" if negative else "execution",
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
        for rule in business_rules:
            if rule not in existing:
                emit(rule, False, reason, None, None, unknown=True)
        return finish()

    def class_available(actual_class):
        if version not in {"3", "4", "5", "6"} or slot.purpose != "functional":
            return True
        return emit(
            "functional.case_available", slot.required_class == actual_class,
            Reason.MISSING_EVIDENCE, slot.required_class, actual_class, unknown=True,
        )

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
    if version in {"2", "3", "4", "5", "6"} and slot.applicability_reason is not None:
        metadata = snapshot.core.normalized_metadata
        exclusion_ok = (
            context_ok
            and snapshot.core.metadata_hash == hash_json(metadata)
            and data.review.review_version == data.review_version
            and declared_valid
            and isinstance(declared, list)
            and set(data.review.confirmed_claims).issubset(declared)
            and slot.capability_id not in declared
            and slot.capability_id not in data.review.confirmed_claims
            and slot.capability_id in data.review.excluded_capabilities
            and slot.expected_outcome == Outcome.NOT_APPLICABLE
            and data.dispatch_started_at is None
            and data.dispatch_payload_hash is None
            and data.agent_http is None
            and data.agent_response is None
            and data.agent_result is None
            and data.agent_task_status is None
            and (version not in {"3", "4", "5", "6"} or data.initial_agent_http is None)
            and data.evm.candidate_tx_hash is None
        )
        emit(
            "task.applicability",
            False,
            Reason.CAPABILITY_NOT_DECLARED if exclusion_ok else Reason.EVIDENCE_INCONSISTENT,
            slot.capability_id,
            declared,
            unknown=not exclusion_ok,
            applicable=not exclusion_ok,
        )
        return finish()
    context_ok &= emit(
        "context.mapping",
        slot.capability_id in data.review.confirmed_claims
        and data.review.review_version == data.review_version
        and (
            version == "1"
            or (
                declared_valid
                and slot.capability_id
                in cast(list[Any], snapshot.core.normalized_metadata["capabilities"])
                and snapshot.core.metadata_hash == hash_json(snapshot.core.normalized_metadata)
            )
        ),
        Reason.MAPPING_UNCONFIRMED,
        slot.capability_id,
        list(data.review.confirmed_claims),
        unknown=True,
    )
    dispatched = data.dispatch_started_at
    request_payload = task.model_dump(mode="json")
    if version in {"3", "4", "5", "6"}:
        try:
            request_payload = mutated_payload(slot)
        except (TypeError, ValueError, KeyError):
            emit(
                "functional.request_validity", False, Reason.EVIDENCE_INCONSISTENT,
                "fixed version-3 request mutation", slot.request_overrides, unknown=True,
            )
            return unavailable(Reason.EVIDENCE_INCONSISTENT)
    elif slot.request_overrides is not None:
        emit(
            "functional.request_validity", False, Reason.RULE_VERSION_MISMATCH,
            "legacy task without request overrides", slot.request_overrides, unknown=True,
        )
        return unavailable(Reason.RULE_VERSION_MISMATCH)
    payload_hash = hash_json(request_payload)
    intent_ok = (
        dispatched is not None
        and snapshot.core.captured_at
        <= facts.window_start
        <= data.intent_persisted_at
        <= dispatched
        <= task.deadline
        and data.dispatch_payload_hash == payload_hash
        and (read_only or slot.synthetic_input is not None)
    )
    context_ok &= emit(
        "task.intent",
        intent_ok,
        data.execution_reason or Reason.DISPATCH_UNCERTAIN,
        payload_hash,
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
        and (read_only or (witness.owner_code == "0x" and witness.executor_code == "0x"))
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
    if not read_only:
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
        and (task.target_contract is None or task.target_contract in grant.contract_allowlist)
        and task.chain_instance_id in grant.chain_instances
        and "POST" in grant.methods
        and "/tasks" in grant.paths
        and any(
            endpoint.endpoint_id in grant.endpoint_ids
            and (
                read_only
                or (proof is not None and endpoint_hash(endpoint) == proof.message.endpoint_hash)
            )
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
    if negative:
        context_ok &= emit(
            "functional.request_validity",
            grant is not None
            and (
                slot.required_class != "forbidden_contract"
                or request_payload["target_contract"] not in grant.contract_allowlist
            ),
            Reason.EVIDENCE_INCONSISTENT,
            {"required_class": slot.required_class, "payload_hash": payload_hash},
            {"request_overrides": slot.request_overrides},
            unknown=True,
        )
    if version in {"2", "3", "4", "5", "6"} and context_ok:
        http = data.agent_http
        if (
            version in {"4", "5", "6"} and not read_only and data.agent_result is not None
            and (http is None or "response" not in http)
        ):
            emit(
                "agent.evidence", False, Reason.MISSING_EVIDENCE,
                "raw HTTP envelope for the claimed write result", None, unknown=True,
            )
            return unavailable(Reason.MISSING_EVIDENCE)
        if http is not None:
            status = http.get("http_status")
            try:
                started, ended = http.get("started_at"), http.get("ended_at")
                valid_times = all(
                    isinstance(value, str)
                    and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value)
                    and seconds(value) >= 0
                    for value in (started, ended)
                )
            except (ValueError, TypeError):
                valid_times = False
            valid_http = (
                valid_times
                and (status is None or type(status) is int and 100 <= status <= 599)
                and http.get("request_id") == task.request_id
                and grant is not None
                and http.get("method") in grant.methods
                and ("/tasks" if http.get("method") == "POST" else "/tasks/{request_id}")
                in grant.paths
                and any(
                    http.get("origin") == endpoint.origin
                    and grant is not None
                    and endpoint.endpoint_id in grant.endpoint_ids
                    for endpoint in snapshot.core.endpoints
                )
                and (
                    (http.get("method") == "POST" and http.get("path") == "/tasks")
                    or (
                        http.get("method") == "GET"
                        and http.get("path") == "/tasks/" + task.request_id
                    )
                )
                and http.get("started_at") is not None
                and http.get("ended_at") is not None
                and data.dispatch_started_at is not None
                and data.dispatch_started_at <= str(http["started_at"]) <= str(http["ended_at"])
                and str(http["started_at"]) <= task.deadline
            )
            if (
                not valid_http
                or http.get("response") != data.agent_response
                or negative and (
                    http.get("method") != "POST" or data.initial_agent_http != http
                )
            ):
                emit(
                    "agent.evidence",
                    False,
                    Reason.EVIDENCE_INCONSISTENT,
                    "matching frozen HTTP envelope",
                    http,
                    unknown=True,
                )
                return unavailable(Reason.EVIDENCE_INCONSISTENT)
            if negative:
                if status is None or status == 429:
                    return unavailable(
                        Reason.RATE_LIMIT_UNATTRIBUTED if status == 429
                        else data.execution_reason or Reason.PLATFORM_NETWORK_ERROR
                    )
                # Refusals are checked only after independent chain/context evidence below.
            elif type(status) is int and 500 <= status <= 599:
                emit(
                    "agent.service", False, Reason.AGENT_SERVICE_ERROR, "successful service", status
                )
                return unavailable(Reason.AGENT_SERVICE_ERROR)
            if not negative and type(status) is int and 200 <= status <= 299 and "response" in http:
                try:
                    view = ControlledTaskView.model_validate(http["response"])
                    if (
                        view.request_id != task.request_id
                        or view.status_path != "/tasks/" + task.request_id
                    ):
                        raise ValueError("task handle mismatch")
                    if view.result is not None and view.result.capability_id != task.capability_id:
                        raise ValueError("result capability mismatch")
                    if (
                        view.result != data.agent_result
                        or view.task_status != data.agent_task_status
                    ):
                        emit(
                            "agent.evidence",
                            False,
                            Reason.EVIDENCE_INCONSISTENT,
                            view.model_dump(mode="json"),
                            data.agent_result.model_dump(mode="json")
                            if data.agent_result
                            else None,
                            unknown=True,
                        )
                        return unavailable(Reason.EVIDENCE_INCONSISTENT)
                    if view.task_status == "failed":
                        reason = (
                            Reason.CAPABILITY_EXPLICITLY_UNSUPPORTED
                            if view.reason_code
                            in {
                                "UNSUPPORTED_CAPABILITY",
                                "CAPABILITY_EXPLICITLY_UNSUPPORTED",
                                "NOT_SUPPORTED",
                                "UNSUPPORTED_PROTOCOL",
                            }
                            else Reason.AGENT_TASK_FAILED
                        )
                        emit(
                            "agent.service",
                            False,
                            reason,
                            "completed declared task",
                            view.reason_code,
                        )
                        # A canonical reverted candidate gives the more specific chain cause.
                        # Keep the Agent failure if its candidate cannot be independently read.
                        if (
                            slot.capability_id != "anchor_record"
                            or data.evm.candidate_tx_hash is None
                        ):
                            return unavailable(reason)
                    if view.task_status == "succeeded" and view.result is None:
                        raise ValueError("succeeded task requires result")
                except (ValueError, TypeError):
                    emit(
                        "agent.service",
                        False,
                        Reason.SCHEMA_ERROR,
                        "valid controlled task response",
                        http["response"],
                    )
                    return unavailable(Reason.SCHEMA_ERROR)
            elif not negative and (
                status is None
                or status in {401, 403, 429}
                or not (type(status) is int and 200 <= status <= 299)
            ):
                reason = (
                    Reason.RATE_LIMIT_UNATTRIBUTED
                    if status == 429
                    else (
                        Reason.ACCESS_NOT_GRANTED
                        if status in {401, 403}
                        else data.execution_reason or Reason.PLATFORM_NETWORK_ERROR
                    )
                )
                emit(
                    "agent.service", False, reason, "observable task response", status, unknown=True
                )
                return unavailable(reason)
        elif data.execution_reason is not None or read_only or negative:
            missing_reason = (
                data.execution_reason
                if data.execution_reason
                in {
                    Reason.PLATFORM_NETWORK_ERROR,
                    Reason.PLATFORM_RPC_ERROR,
                    Reason.SERVICE_TIMEOUT,
                    Reason.ACCESS_NOT_GRANTED,
                    Reason.CANCELLED_BY_OPERATOR,
                    Reason.CHAIN_INSTANCE_CHANGED,
                    Reason.DISPATCH_UNCERTAIN,
                }
                else Reason.MISSING_EVIDENCE
            )
            emit(
                "agent.evidence",
                False,
                missing_reason,
                "http HTTP task evidence",
                None,
                unknown=True,
            )
            return unavailable(missing_reason)
    try:
        if version == "6":
            hex_data(rpc["head"]["hash"], 32)
            quantity(rpc["head"]["number"])
            quantity(rpc["pre_dispatch_block"]["number"])
            quantity(rpc["dispatch_block"]["number"])
        identity = {
            "chain_id": str(quantity(rpc["chain_id"])),
            "genesis_hash": hex_data(rpc["genesis"]["hash"], 32),
            "deployment_instance_id": hex_data(rpc["deployment_instance"], 32 if version == "6" else None),
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
        if task.target_contract is not None:
            code_hash = hash_bytes(bytes.fromhex(hex_data(rpc["record_code"])[2:]))
            context_ok &= emit(
                "chain.record_code",
                facts.target_code_hash is not None and code_hash == facts.target_code_hash,
                Reason.CHAIN_INSTANCE_CHANGED
                if facts.target_code_hash
                else Reason.MISSING_EVIDENCE,
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
        if version == "6":
            context_ok &= emit(
                "chain.position",
                quantity(rpc["pre_dispatch_block"]["number"]) == int(facts.pre_dispatch_block)
                and witness is not None
                and quantity(rpc["dispatch_block"]["number"])
                == int(witness.snapshot_core.read_block_number),
                Reason.EVIDENCE_INCONSISTENT,
                {"pre_dispatch_block": facts.pre_dispatch_block,
                 "dispatch_block": witness.snapshot_core.read_block_number if witness else None},
                {"pre_dispatch_block": rpc["pre_dispatch_block"]["number"],
                 "dispatch_block": rpc["dispatch_block"]["number"]},
                unknown=True,
            )
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
        context_reason = next(
            item.reason_code for item in assertions if item.outcome == Outcome.UNKNOWN
        )
        return unavailable(context_reason)
    if negative:
        if data.evm.error_reason:
            return unavailable(data.evm.error_reason)
        assert data.agent_http is not None
        expected_status, expected_code = REJECTION_CASES[slot.required_class]
        rejection_response = {"accepted": False, "error": {"code": expected_code}}
        status = data.agent_http.get("http_status")
        emit(
            "functional.rejection",
            status == expected_status
            and data.agent_response == rejection_response
            and data.agent_result is None
            and data.agent_task_status is None
            and data.evm.candidate_tx_hash is None,
            Reason.AGENT_SERVICE_ERROR
            if type(status) is int and 500 <= status <= 599 else Reason.AGENT_TASK_FAILED,
            {"http_status": expected_status, "code": expected_code},
            {"http_status": status, "response": data.agent_response},
        )
        return finish()
    if version == "6" and slot.capability_id in {"anchor_record", "get_tx_status"}:
        candidate = data.evm.candidate_tx_hash
        if candidate is not None and data.evm.error_reason is None:
            rpc_reason = transaction_evidence_reason(rpc, candidate, writing=not read_only)
            emit(
                "receipt.evidence", rpc_reason is None, rpc_reason,
                "well-formed, internally consistent RPC transaction and receipt",
                {"transaction": rpc.get("transaction"), "receipt": rpc.get("receipt")},
                unknown=True,
            )
            if rpc_reason is not None:
                return unavailable(rpc_reason)
    if read_only:
        response = data.agent_result
        try:
            raw_view = ControlledTaskView.model_validate(data.agent_response)
            raw_matches = (
                raw_view.request_id == task.request_id
                and raw_view.status_path == "/tasks/" + task.request_id
                and raw_view.result == response
                and raw_view.task_status == data.agent_task_status
            )
        except (ValueError, TypeError):
            raw_matches = False
        if not emit(
            "query.raw_response",
            raw_matches,
            Reason.MISSING_EVIDENCE,
            "matching frozen Agent response",
            data.agent_response,
            unknown=True,
        ):
            return unavailable(Reason.MISSING_EVIDENCE)
        if not emit(
            "query.response",
            response is not None
            and response.capability_id == task.capability_id
            and response.chain_id == task.chain_id
            and data.agent_task_status == "succeeded",
            Reason.SCHEMA_ERROR,
            task.capability_id,
            response.model_dump(mode="json") if response else None,
            unknown=response is None,
        ):
            return unavailable(data.execution_reason or Reason.MISSING_EVIDENCE)
        assert response is not None
        if data.evm.error_reason:
            return unavailable(data.evm.error_reason)
        if version in {"3", "4", "5", "6"} and task.capability_id == "get_tx_status" and not emit(
            "query.candidate",
            data.evm.candidate_tx_hash == task.query_tx_hash,
            Reason.EVIDENCE_INCONSISTENT,
            task.query_tx_hash,
            data.evm.candidate_tx_hash,
            unknown=True,
        ):
            return unavailable(Reason.EVIDENCE_INCONSISTENT)
        if version == "6":
            query_reason = query_evidence_reason(rpc, task)
            emit(
                "query.evidence", query_reason is None, query_reason,
                {"read_block_number": task.read_block_number, "read_block_hash": task.read_block_hash,
                 "record_abi": "(bool,bytes32)" if task.capability_id == "verify_record" else None},
                {name: rpc.get(name) for name in ("read_block", "read_canonical", "record_call")},
                unknown=True,
            )
            if query_reason is not None:
                return unavailable(query_reason)
        try:
            block, canonical = rpc["read_block"], rpc["read_canonical"]
            if not emit(
                "query.block",
                hex_data(block["hash"], 32)
                == hex_data(canonical["hash"], 32)
                == task.read_block_hash
                and str(quantity(block["number"]))
                == str(quantity(canonical["number"]))
                == task.read_block_number,
                Reason.STALE_EVIDENCE,
                task.read_block_hash,
                block["hash"],
                unknown=True,
            ):
                return unavailable(Reason.STALE_EVIDENCE)
            def parameters():
                emit(
                    "query.parameters",
                    response.read_block_number == task.read_block_number
                    and response.read_block_hash == task.read_block_hash
                    and (
                        task.capability_id != "get_tx_status" or response.tx_hash == task.query_tx_hash
                    )
                    and (
                        task.capability_id != "verify_record"
                        or (
                            response.record_executor == task.record_executor
                            and response.record_request_id == task.record_request_id
                        )
                    ),
                    Reason.SEMANTIC_MISMATCH,
                    task.model_dump(mode="json"),
                    response.model_dump(mode="json"),
                )

            if version not in {"3", "4", "5", "6"}:
                parameters()
            if task.capability_id == "verify_record":
                raw = hex_data(rpc["record_call"], 64)
                flag = int(raw[2:66], 16)
                actual_hash = "0x" + raw[66:]
                if flag not in (0, 1) or (flag == 0) != (actual_hash == "0x" + "00" * 32):
                    raise ValueError("invalid record lookup")
                actual_class = (
                    "not_found" if not flag
                    else "match" if actual_hash == task.record_hash else "hash_mismatch"
                )
                if not class_available(actual_class):
                    return unavailable(Reason.MISSING_EVIDENCE)
                if version in {"3", "4", "5", "6"}:
                    parameters()
                emit(
                    "query.record",
                    response.record_exists == bool(flag)
                    and response.record_hash == actual_hash
                    and response.record_matches == (bool(flag) and actual_hash == task.record_hash),
                    Reason.RECORD_HASH_MISMATCH,
                    {"exists": bool(flag), "record_hash": actual_hash},
                    response.model_dump(mode="json"),
                )
            else:
                if data.evm.error_reason or "transaction" not in rpc or "receipt" not in rpc:
                    return unavailable(data.evm.error_reason or Reason.MISSING_EVIDENCE)
                tx, receipt = rpc["transaction"], rpc["receipt"]
                if tx is None and receipt is None:
                    if version in {"3", "4", "5", "6"}:
                        if not class_available("not_found"):
                            return unavailable(Reason.MISSING_EVIDENCE)
                        parameters()
                        emit(
                            "query.status", response.tx_status == "NOT_FOUND",
                            Reason.SEMANTIC_MISMATCH,
                            {"tx_hash": task.query_tx_hash, "status": "NOT_FOUND",
                             "scope": "frozen_rpc_observation", "read_block_hash": task.read_block_hash},
                            {"tx_hash": response.tx_hash, "status": response.tx_status},
                        )
                        return finish()
                    return unavailable(Reason.RPC_RECEIPT_NOT_FOUND)
                if (
                    tx is None
                    or not isinstance(tx, dict)
                    or receipt is not None
                    and not isinstance(receipt, dict)
                ):
                    raise ValueError("receipt without transaction")
                if not emit(
                    "query.transaction",
                    hex_data(tx["hash"], 32) == task.query_tx_hash
                    and str(quantity(tx["chainId"])) == facts.execution_chain.chain_id,
                    Reason.SEMANTIC_MISMATCH,
                    task.query_tx_hash,
                    tx["hash"],
                    unknown=True,
                ):
                    return unavailable(Reason.SEMANTIC_MISMATCH)
                observed_status = "PENDING"
                if receipt is None:
                    if "blockHash" not in tx or "blockNumber" not in tx:
                        return unavailable(Reason.SCHEMA_ERROR)
                    if tx["blockHash"] is not None or tx["blockNumber"] is not None:
                        return unavailable(Reason.RPC_RECEIPT_NOT_FOUND)
                if receipt is not None:
                    if quantity(receipt["blockNumber"]) > int(task.read_block_number or "0"):
                        return unavailable(Reason.STALE_EVIDENCE)
                    block, canonical = rpc["receipt_block"], rpc["receipt_canonical"]
                    status = quantity(receipt["status"])
                    if status not in (0, 1):
                        raise ValueError("invalid receipt status")
                    canonical_ok = (
                        hex_data(receipt["transactionHash"], 32) == task.query_tx_hash
                        and hex_data(tx["blockHash"], 32) == hex_data(receipt["blockHash"], 32)
                        and hex_data(block["hash"], 32)
                        == hex_data(canonical["hash"], 32)
                        == hex_data(receipt["blockHash"], 32)
                        and quantity(block["number"]) == quantity(receipt["blockNumber"])
                        and quantity(tx["blockNumber"]) == quantity(receipt["blockNumber"])
                        and quantity(canonical["number"]) == quantity(receipt["blockNumber"])
                        and min(
                            quantity(rpc["head"]["number"]),
                            int(task.read_block_number or "0"),
                        )
                        - quantity(receipt["blockNumber"])
                        + 1
                        >= facts.confirmation_depth
                    )
                    emit(
                        "query.canonical",
                        canonical_ok,
                        Reason.PENDING_FINALITY,
                        receipt["blockHash"],
                        canonical["hash"],
                        unknown=True,
                    )
                    if not canonical_ok:
                        return unavailable(Reason.PENDING_FINALITY)
                    observed_status = "SUCCESS" if status == 1 else "REVERTED"
                actual_class = {"SUCCESS": "success", "REVERTED": "revert", "PENDING": "pending"}[
                    observed_status
                ]
                if not class_available(actual_class):
                    return unavailable(Reason.MISSING_EVIDENCE)
                if version in {"3", "4", "5", "6"}:
                    parameters()
                emit(
                    "query.status",
                    response.tx_hash == task.query_tx_hash
                    and response.tx_status == observed_status,
                    Reason.SEMANTIC_MISMATCH,
                    {"tx_hash": task.query_tx_hash, "status": observed_status},
                    {"tx_hash": response.tx_hash, "status": response.tx_status},
                    unknown=observed_status == "PENDING",
                )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            return unavailable(data.evm.error_reason or Reason.PLATFORM_RPC_ERROR)
        return finish()
    tx = rpc.get("transaction")
    if not isinstance(tx, dict):
        return unavailable(
            data.evm.error_reason or data.execution_reason or Reason.RPC_RECEIPT_NOT_FOUND
        )
    try:
        if version in {"2", "3", "4", "5", "6"}:
            receipt = rpc.get("receipt")
            block = rpc.get("receipt_block")
            canonical = rpc.get("receipt_canonical")
            if (
                not isinstance(receipt, dict)
                or not isinstance(block, dict)
                or not isinstance(canonical, dict)
            ):
                return unavailable(data.evm.error_reason or Reason.RPC_RECEIPT_NOT_FOUND)
            canonical_ok = (
                hex_data(receipt["transactionHash"], 32)
                == data.evm.candidate_tx_hash
                == hex_data(tx["hash"], 32)
                and hex_data(tx["blockHash"], 32)
                == hex_data(receipt["blockHash"], 32)
                == hex_data(block["hash"], 32)
                == hex_data(canonical["hash"], 32)
                and quantity(tx["blockNumber"])
                == quantity(receipt["blockNumber"])
                == quantity(block["number"])
                == quantity(canonical["number"])
                and quantity(tx["transactionIndex"]) == quantity(receipt["transactionIndex"])
                and quantity(receipt["status"]) in (0, 1)
            )
            if data.evm.error_reason or not canonical_ok:
                return unavailable(data.evm.error_reason or Reason.PENDING_FINALITY)
            if (
                quantity(rpc["head"]["number"]) - quantity(receipt["blockNumber"]) + 1
                < facts.confirmation_depth
            ):
                return unavailable(Reason.PENDING_FINALITY)
        if version in {"5", "6"}:
            assert receipt is not None
            if quantity(receipt["status"]) == 1:
                try:
                    logs = receipt["logs"]
                    if not isinstance(logs, list):
                        raise ValueError("malformed RPC log list")
                    previous_index = -1
                    for log in logs:
                        if not isinstance(log, dict) or not isinstance(log.get("topics"), list):
                            raise ValueError("malformed RPC log")
                        for topic in log["topics"]:
                            hex_data(topic, 32)
                        for field, size in (("address", 20), ("transactionHash", 32), ("blockHash", 32)):
                            hex_data(log[field], size)
                        hex_data(log["data"])
                        if log["topics"] and hex_data(log["topics"][0], 32) == EVENT_TOPIC:
                            if len(log["topics"]) != 3:
                                raise ValueError("malformed RecordAnchored topics")
                            hex_data(log["data"], 32)
                            if hex_data(log["topics"][1], 32)[2:26] != "0" * 24:
                                raise ValueError("malformed indexed executor")
                        for field in ("logIndex", "transactionIndex", "blockNumber"):
                            quantity(log[field])
                        if type(log["removed"]) is not bool:
                            raise ValueError("malformed RPC log removal flag")
                        index = quantity(log["logIndex"])
                        consistent = (
                            hex_data(log["transactionHash"], 32) == hex_data(receipt["transactionHash"], 32)
                            and hex_data(log["blockHash"], 32) == hex_data(receipt["blockHash"], 32)
                            and quantity(log["blockNumber"]) == quantity(receipt["blockNumber"])
                            and quantity(log["transactionIndex"]) == quantity(receipt["transactionIndex"])
                            and type(log["removed"]) is bool and not log["removed"]
                            and previous_index < index <= 2**53 - 1
                        )
                        if not consistent:
                            emit(
                                "receipt.logs", False, Reason.EVIDENCE_INCONSISTENT,
                                {"transaction_hash": receipt["transactionHash"], "block_hash": receipt["blockHash"]},
                                log, unknown=True,
                            )
                            return unavailable(Reason.EVIDENCE_INCONSISTENT)
                        previous_index = index
                    emit("receipt.logs", True, None, "consistent canonical receipt logs", len(logs))
                except (KeyError, TypeError, ValueError, AttributeError, IndexError):
                    emit(
                        "receipt.logs", False, Reason.PLATFORM_RPC_ERROR,
                        "well-formed canonical receipt logs", receipt.get("logs"), unknown=True,
                    )
                    return unavailable(Reason.PLATFORM_RPC_ERROR)
        if version in {"4", "5", "6"} and data.agent_result is not None:
            write_result = data.agent_result
            if not emit(
                "agent.result.transaction",
                write_result.tx_hash == data.evm.candidate_tx_hash,
                Reason.EVIDENCE_INCONSISTENT,
                write_result.tx_hash,
                data.evm.candidate_tx_hash,
                unknown=True,
            ):
                return unavailable(Reason.EVIDENCE_INCONSISTENT)
            assert receipt is not None
            if data.agent_task_status == "succeeded" and quantity(receipt["status"]) == 1:
                emit(
                    "agent.result.chain", write_result.chain_id == facts.execution_chain.chain_id,
                    Reason.TX_WRONG_CHAIN, facts.execution_chain.chain_id, write_result.chain_id,
                    critical=True,
                )
                emit(
                    "agent.result.executor", write_result.executor == facts.executor,
                    Reason.TX_WRONG_EXECUTOR, facts.executor, write_result.executor, critical=True,
                )
                emit(
                    "agent.result.hash", write_result.record_hash == task.record_hash,
                    Reason.RECORD_HASH_MISMATCH, task.record_hash, write_result.record_hash, critical=True,
                )
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
            (tx["to"] is not None and hex_data(tx["to"], 20) == facts.target_contract)
            if version == "6" else hex_data(tx["to"], 20) == facts.target_contract,
            Reason.TX_WRONG_TARGET,
            facts.target_contract,
            tx["to"],
            critical=True,
        )
        assert task.record_hash is not None
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
        if version == "4" and not isinstance(receipt["logs"], list):
            raise ValueError("malformed RPC log list")
        decoded = []
        for log in receipt["logs"]:
            if version == "4":
                if not isinstance(log, dict) or not isinstance(log.get("topics"), list):
                    raise ValueError("malformed RPC log")
                for topic in log["topics"]:
                    hex_data(topic, 32)
                for field, size in (("address", 20), ("transactionHash", 32), ("blockHash", 32)):
                    hex_data(log[field], size)
                hex_data(log["data"])
                for field in ("logIndex", "transactionIndex", "blockNumber"):
                    quantity(log[field])
                if type(log["removed"]) is not bool:
                    raise ValueError("malformed RPC log removal flag")
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
        if version in {"2", "3", "4", "5", "6"}:
            # Malformed platform reads cannot establish an Agent business failure.
            assertions[:] = [
                item.model_copy(
                    update={
                        "outcome": Outcome.UNKNOWN,
                        "reason_code": Reason.PLATFORM_RPC_ERROR,
                        "critical": False,
                    }
                )
                if item.outcome == Outcome.FAIL and (
                    not item.rule_id.startswith("agent.")
                    or version in {"4", "5", "6"} and item.rule_id.startswith("agent.result.")
                )
                else item
                for item in assertions
            ]
        return unavailable(data.evm.error_reason or Reason.SCHEMA_ERROR)
    return finish()
