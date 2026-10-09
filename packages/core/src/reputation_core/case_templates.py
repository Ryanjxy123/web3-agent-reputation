"""Frozen policy-v1 case classes and narrowly defined safe rejection probes."""

import re
from datetime import datetime, timedelta
from typing import Any

from .models import CaseSlot

CASE_CLASSES = {
    "get_tx_status": (
        "success", "revert", "pending", "not_found", "invalid_format", "unsupported_chain"
    ),
    "verify_record": (
        "match", "not_found", "hash_mismatch", "invalid_format", "forbidden_contract"
    ),
    "anchor_record": ("normal", "expired_deadline", "forbidden_contract", "unsupported_chain"),
}

REJECTION_CASES = {
    "invalid_format": (422, "SCHEMA_ERROR"),
    "forbidden_contract": (403, "TARGET_NOT_ALLOWED"),
    "unsupported_chain": (403, "TARGET_NOT_ALLOWED"),
    "expired_deadline": (422, "INVALID_DEADLINE"),
}


def mutated_payload(slot: CaseSlot) -> dict[str, Any]:
    """Return the actual wire request; the typed baseline retains authorization facts.

    Only a fixed functional negative class can alter the request. A forbidden
    target is frozen explicitly and must also be checked against the access grant.
    """
    payload = slot.task.model_dump(mode="json")
    overrides = slot.request_overrides
    if slot.case_kind != "negative":
        if overrides is not None:
            raise ValueError("positive requests cannot contain overrides")
        return payload
    case = slot.required_class
    if (
        slot.purpose != "functional"
        or slot.expected_outcome != "PASS"
        or slot.applicability_reason is not None
        or case not in CASE_CLASSES[slot.capability_id]
        or case not in REJECTION_CASES
        or (case != "forbidden_contract" and overrides is not None)
    ):
        raise ValueError("unsupported rejection probe")
    if case == "invalid_format":
        key = "query_tx_hash" if slot.capability_id == "get_tx_status" else "record_request_id"
        payload[key] = "invalid-hash"
    elif case == "unsupported_chain":
        payload["chain_id"] = str(int(slot.task.chain_id) + 1)
    elif case == "expired_deadline":
        payload["deadline"] = (
            datetime.fromisoformat(slot.expected.window_start) - timedelta(seconds=1)
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    else:
        target = overrides.get("target_contract") if isinstance(overrides, dict) else None
        if (
            not isinstance(overrides, dict)
            or set(overrides) != {"target_contract"}
            or not isinstance(target, str)
            or re.fullmatch(r"0x[0-9a-f]{40}", target) is None
            or target == "0x" + "00" * 20
            or target == slot.task.target_contract
        ):
            raise ValueError("forbidden-contract probe requires a distinct frozen address")
        payload["target_contract"] = target
    return payload
