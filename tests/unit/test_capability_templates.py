"""Capability-specific wire inputs, output validation, and legacy hash compatibility."""

import pytest
from pydantic import ValidationError
from reputation_core.evidence import hash_json
from reputation_core.models import (
    AccessGrantCreate,
    ClaimsConfirm,
    EvaluationCreate,
    TaskEnvelope,
    TaskLink,
    TaskResult,
)

from tests.factories import slot


def test_anchor_wire_keeps_original_fields_and_rejects_query_parameters():
    original = slot().task.model_dump(mode="json")
    assert set(original) == {
        "protocol",
        "request_id",
        "capability_id",
        "snapshot_hash",
        "chain_id",
        "chain_instance_id",
        "target_contract",
        "record_hash",
        "deadline",
    }
    assert TaskEnvelope.model_validate(original).model_dump(mode="json") == original
    with pytest.raises(ValidationError):
        TaskEnvelope.model_validate({**original, "query_tx_hash": "0x" + "ab" * 32})
    result = {
        "chain_id": "31337",
        "tx_hash": "0x" + "ab" * 32,
        "executor": "0x" + "11" * 20,
        "record_hash": "0x" + "12" * 32,
    }
    assert TaskResult.model_validate(result).model_dump(mode="json") == result


def query_task(capability="get_tx_status", **changes):
    original = slot().task.model_dump(mode="json")
    original.update(
        capability_id=capability,
        target_contract=None,
        record_hash=None,
        query_tx_hash="0x" + "ab" * 32,
        read_block_number="12",
        read_block_hash="0x" + "34" * 32,
    )
    return TaskEnvelope.model_validate({**original, **changes})


def test_read_templates_require_frozen_block_and_capability_specific_inputs():
    task = query_task()
    assert task.capability_id == "get_tx_status" and task.target_contract is None
    for changes in (
        {"read_block_hash": None},
        {"query_tx_hash": None},
        {"target_contract": "0x" + "11" * 20},
        {"record_hash": "0x" + "12" * 32},
    ):
        with pytest.raises(ValidationError):
            query_task(**changes)
    record = query_task(
        "verify_record",
        query_tx_hash=None,
        target_contract="0x" + "11" * 20,
        record_hash="0x" + "12" * 32,
        record_executor="0x" + "13" * 20,
        record_request_id="0x" + "14" * 32,
    )
    assert record.record_request_id != record.request_id
    with pytest.raises(ValidationError):
        TaskEnvelope.model_validate({**record.model_dump(), "record_executor": None})


def test_read_outputs_reject_missing_state_and_cross_capability_fields():
    values = {
        "capability_id": "get_tx_status",
        "chain_id": "31337",
        "tx_hash": "0x" + "ab" * 32,
        "tx_status": "NOT_FOUND",
        "read_block_number": "12",
        "read_block_hash": "0x" + "34" * 32,
    }
    assert TaskResult.model_validate(values).tx_status == "NOT_FOUND"
    for changes in (
        {"read_block_hash": None},
        {"tx_status": None},
        {"executor": "0x" + "11" * 20},
        {"record_exists": False},
    ):
        with pytest.raises(ValidationError):
            TaskResult.model_validate({**values, **changes})
    record = {
        "capability_id": "verify_record",
        "chain_id": "31337",
        "record_hash": "0x" + "00" * 32,
        "record_executor": "0x" + "11" * 20,
        "record_request_id": "0x" + "12" * 32,
        "record_exists": False,
        "record_matches": False,
        "read_block_number": "12",
        "read_block_hash": "0x" + "34" * 32,
    }
    assert TaskResult.model_validate(record).record_exists is False
    with pytest.raises(ValidationError):
        TaskResult.model_validate({**record, "record_exists": "false"})


def test_api_boundary_rejects_wrong_capability_inputs_and_empty_write_grants():
    from uuid import uuid4

    values = {
        "snapshot_id": str(uuid4()),
        "review_version": 1,
        "profile": "record-read-v1",
        "policy_version": "policy-v1",
        "grant_ids": [str(uuid4())],
        "suite_id": "capabilities-v1",
        "capability_id": "get_tx_status",
        "query_tx_hash": "0x" + "ab" * 32,
    }
    assert EvaluationCreate.model_validate(values).capability_id == "get_tx_status"
    with pytest.raises(ValidationError):
        EvaluationCreate.model_validate({**values, "target_contract": "0x" + "11" * 20})
    with pytest.raises(ValidationError):
        EvaluationCreate.model_validate({**values, "profile": "record-write-v1"})
    grant = {
        "snapshot_id": str(uuid4()),
        "endpoint_id": "agent",
        "max_tasks": 1,
        "expires_at": "2026-10-09T12:00:00.000Z",
        "consent_ref": "explicit test consent",
        "capabilities": ["get_tx_status"],
        "contract_allowlist": [],
    }
    assert AccessGrantCreate.model_validate(grant).contract_allowlist == ()
    with pytest.raises(ValidationError):
        AccessGrantCreate.model_validate({**grant, "capabilities": ["anchor_record"]})
    with pytest.raises(ValidationError):
        ClaimsConfirm(
            confirmed_claims=("verify_record", "verify_record"),
            reason="duplicate claims",
            expected_review_version=0,
        )


def test_legacy_evaluation_request_hash_keeps_prior_idempotency_payload():
    from uuid import uuid4

    original = {
        "snapshot_id": str(uuid4()),
        "review_version": 1,
        "profile": "record-write-v1",
        "policy_version": "policy-v1",
        "grant_ids": [str(uuid4())],
        "suite_id": "m1-smoke-v1",
    }
    assert EvaluationCreate.model_validate(original).model_dump(mode="json") == original
    assert hash_json(
        EvaluationCreate.model_validate(original).model_dump(mode="json")
    ) == hash_json(original)
    targeted = {**original, "target_contract": "0x" + "11" * 20}
    assert hash_json(
        EvaluationCreate.model_validate(targeted).model_dump(mode="json")
    ) != hash_json(original)


def test_read_task_links_require_truthful_transaction_and_fixed_record_block():
    base = {
        "capability_id": "get_tx_status",
        "request_id": "0x" + "12" * 32,
        "candidate_tx_hash": "0x" + "34" * 32,
        "verified_tx_hash": None,
        "executor": "0x" + "11" * 20,
        "block_number": None,
        "block_hash": None,
        "log_index": None,
        "match_status": "PASS",
    }
    assert TaskLink.model_validate(base).verified_tx_hash is None
    with pytest.raises(ValidationError):
        TaskLink.model_validate({**base, "verified_tx_hash": base["candidate_tx_hash"]})
    fixed = {
        **base,
        "capability_id": "verify_record",
        "candidate_tx_hash": None,
        "block_number": "12",
        "block_hash": "0x" + "56" * 32,
    }
    assert TaskLink.model_validate(fixed).block_number == "12"
    with pytest.raises(ValidationError):
        TaskLink.model_validate({**fixed, "block_hash": None})
