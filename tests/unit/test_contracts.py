import hashlib
import json
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from pydantic import TypeAdapter, ValidationError
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AgentRef,
    AnchorReceipt,
    AssertionResult,
    CapabilityClaim,
    RunPlan,
    ScoreResult,
    TaskLink,
)
from reputation_core.models.base import BasisPoints, Timestamp
from reputation_core.registry import require_protocol
from reputation_core.scoring_reference import evaluate_from_stats

from tests.factories import agent, plan_data, slot

ROOT = Path(__file__).resolve().parents[2]
HASH = "0x" + "a1" * 32
ZERO = "0x" + "00" * 32
ADDRESS = "0x" + "ab" * 20
NOW = "2026-10-02T12:00:00.000Z"
DEADLINE = "2026-10-02T12:01:00.000Z"


def test_large_agent_id_roundtrip_and_address_normalization():
    ref = agent()
    assert AgentRef.model_validate_json(ref.model_dump_json()) == ref
    assert json.loads(ref.model_dump_json())["agent_id"] == str(2**255 + 123)
    assert (
        AgentRef(
            chain_id="1", registry_address=ADDRESS.upper().replace("0X", "0x"), agent_id="1"
        ).registry_address
        == ADDRESS
    )
    assert ref.key_text == f"eip155:31337:{ADDRESS}:{2**255 + 123}"


@pytest.mark.parametrize("value", [1, -1, True, "01", "-1", "1.0", "1e3", str(2**256), "9" * 79])
def test_invalid_uint256(value):
    with pytest.raises(ValidationError):
        AgentRef(chain_id="1", registry_address=ADDRESS, agent_id=value)


@pytest.mark.parametrize("value", ["0x12", "z" * 42, "0x" + "gg" * 20, "0x" + "00" * 20])
def test_invalid_registry_address(value):
    with pytest.raises(ValidationError):
        AgentRef(chain_id="1", registry_address=value, agent_id="1")


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30T12:00:00.000Z",
        "2026-10-02T12:00:00Z",
        "2026-10-02T20:00:00.000+08:00",
        "2026-10-02",
    ],
)
def test_timestamp_requires_real_utc_millisecond_time(value):
    with pytest.raises(ValidationError):
        TypeAdapter(Timestamp).validate_python(value)


@pytest.mark.parametrize("value", [True, 1.0, -1, 10001, "100"])
def test_scores_are_integer_basis_points(value):
    with pytest.raises(ValidationError):
        TypeAdapter(BasisPoints).validate_python(value)


def test_unknown_requires_reason_and_decision_requires_evidence():
    values = dict(
        assertion_id=uuid4(),
        slot_id=uuid4(),
        rule_id="CHAIN_MATCH",
        rule_version="1",
        outcome="UNKNOWN",
        reason_code=None,
        expected="31337",
        observed=None,
        evidence_refs=[],
        critical=False,
    )
    with pytest.raises(ValidationError):
        AssertionResult(**values)
    values["reason_code"] = "PLATFORM_RPC_ERROR"
    assert AssertionResult(**values).outcome == "UNKNOWN"
    values.update(outcome="FAIL", reason_code="SEMANTIC_MISMATCH")
    with pytest.raises(ValidationError):
        AssertionResult(**values)
    values["evidence_refs"] = [uuid4()]
    assert AssertionResult(**values).outcome == "FAIL"


def test_plan_rejects_snapshot_mismatch_duplicate_requests_and_readonly_writes():
    assert RunPlan(**plan_data()).profile == "record-write-v1"
    for mutation in (
        {"profile": "record-read-v1"},
        {"snapshot_hash": ZERO},
        {"slots": [slot(), slot()]},
    ):
        with pytest.raises(ValidationError):
            RunPlan(**(plan_data() | mutation))


def test_task_link_does_not_equate_candidate_with_verified():
    values = dict(
        request_id=HASH,
        candidate_tx_hash=HASH,
        verified_tx_hash=None,
        executor=ADDRESS,
        block_number=None,
        block_hash=None,
        log_index=None,
        match_status="UNKNOWN",
    )
    assert TaskLink(**values).verified_tx_hash is None
    with pytest.raises(ValidationError):
        TaskLink(**(values | {"match_status": "PASS"}))
    with pytest.raises(ValidationError):
        TaskLink(**(values | {"verified_tx_hash": HASH}))


def test_claim_span_counts_unicode_codepoints():
    values = dict(
        source_evidence_id=uuid4(),
        field_path="description",
        quote="核验🦄",
        start=2,
        end=5,
        polarity="positive",
        candidate_capability="verify_record",
        extractor_version="manual-v1",
    )
    assert CapabilityClaim(**values).end == 5
    with pytest.raises(ValidationError):
        CapabilityClaim(**(values | {"end": 6}))


def test_confirmed_anchor_needs_actual_transaction():
    values = dict(
        report_hash=HASH,
        status="NOT_REQUESTED",
        trusted_chain_key="local-demo",
        chain_instance_id=HASH,
        contract=ADDRESS,
        publisher=ADDRESS,
        tx_hash=None,
        sequence=None,
        block_number=None,
        block_hash=None,
        confirmations=0,
    )
    AnchorReceipt(**values)
    with pytest.raises(ValidationError):
        AnchorReceipt(**(values | {"status": "CONFIRMED"}))


def test_protocol_registry_does_not_load_external_code():
    assert require_protocol("controlled-http-v1") == "controlled-http-v1"
    with pytest.raises(ValueError, match="UNSUPPORTED_PROTOCOL"):
        require_protocol("python:os.system")


def test_schema_validates_wire_sample_and_forbids_extra_fields():
    schema = json.loads((ROOT / "packages/schemas/generated/AgentRef.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(agent().model_dump(mode="json"), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(agent().model_dump(mode="json") | {"score": 100}, schema)


def test_all_generated_schemas_are_valid():
    for path in (ROOT / "packages/schemas/generated").glob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_score_contract_accepts_reference_and_rejects_fake_partial_total():
    golden = json.loads((ROOT / "fixtures/datasets/scoring-golden-v1.json").read_text())
    policy = json.loads((ROOT / "configs/policies/policy-v1.json").read_text())
    result = evaluate_from_stats(golden["input"], policy)
    assert ScoreResult.model_validate(result).overall_score_bp == 8600
    with pytest.raises(ValidationError):
        ScoreResult.model_validate(result | {"evaluation_state": "PARTIAL"})


def test_jcs_rfc8785_number_and_string_example():
    # RFC 8785 section 3.2.2: canonical numeric representations, not json.dumps sorting.
    value = {"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]}
    assert canonical_bytes(value) == b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    assert hash_json({"b": 2, "a": 1}) == hash_json({"a": 1, "b": 2})
    assert hash_json({"a": 1}) != hash_json({"a": 2})


def test_jcs_sorts_utf16_keys_and_preserves_large_integers_as_strings():
    assert canonical_bytes({"\ue000": 2, "😀": 1}).decode() == '{"😀":1,"\ue000":2}'
    assert str(2**255).encode() in canonical_bytes({"agent_id": str(2**255)})
    with pytest.raises(ValueError):
        canonical_bytes({"unsafe_integer": 2**53})


def test_ethereum_keccak_is_not_nist_sha3():
    assert hash_bytes(b"") == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert hash_bytes(b"") != "0x" + hashlib.sha3_256(b"").hexdigest()


@pytest.mark.parametrize(
    "data",
    [
        b'{"a":1,"a":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"\xef\xbb\xbf{}",
        b'{"x":"\\ud800"}',
        b"\xff",
    ],
)
def test_strict_json_rejects_ambiguous_or_noncanonical_input(data):
    with pytest.raises((ValueError, UnicodeError)):
        strict_json(data)
