"""Versioned, deterministic capability definitions for the evaluation core.

The definitions only describe what the platform can test.  They do not execute
network calls, infer an Agent's score, or turn an unreviewed declaration into a
confirmed capability.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .models.domain import Capability

CapabilityMode = Literal["read", "write"]


@dataclass(frozen=True)
class FunctionalCaseClass:
    """One mandatory class of functional test cases in a capability suite."""

    case_class: str
    slots: int
    description: str


@dataclass(frozen=True)
class CapabilityTemplate:
    """A small, versioned contract for one currently supported capability."""

    capability_id: Capability
    version: str
    mode: CapabilityMode
    functional_case_classes: tuple[FunctionalCaseClass, ...]

    @property
    def functional_slot_count(self) -> int:
        return sum(case.slots for case in self.functional_case_classes)


CAPABILITY_TEMPLATES = MappingProxyType(
    {
        "get_tx_status": CapabilityTemplate(
            capability_id="get_tx_status",
            version="1",
            mode="read",
            functional_case_classes=(
                FunctionalCaseClass("confirmed_success", 3, "confirmed successful transaction"),
                FunctionalCaseClass("reverted", 2, "confirmed reverted transaction"),
                FunctionalCaseClass("pending", 2, "pending transaction"),
                FunctionalCaseClass("not_found", 1, "unknown transaction hash"),
                FunctionalCaseClass("invalid_hash", 1, "invalid transaction hash input"),
                FunctionalCaseClass("unsupported_chain", 1, "chain outside the agreed scope"),
            ),
        ),
        "verify_record": CapabilityTemplate(
            capability_id="verify_record",
            version="1",
            mode="read",
            functional_case_classes=(
                FunctionalCaseClass("present_match", 4, "record exists with the expected hash"),
                FunctionalCaseClass("not_found", 2, "record does not exist"),
                FunctionalCaseClass("hash_mismatch", 2, "record exists with another hash"),
                FunctionalCaseClass("invalid_input", 1, "malformed lookup input"),
                FunctionalCaseClass("disallowed_contract", 1, "contract outside the allowed scope"),
            ),
        ),
        "anchor_record": CapabilityTemplate(
            capability_id="anchor_record",
            version="1",
            mode="write",
            functional_case_classes=(
                FunctionalCaseClass("valid_anchor", 7, "valid synthetic record write"),
                FunctionalCaseClass("expired_deadline", 1, "expired task rejected without a write"),
                FunctionalCaseClass("disallowed_contract", 1, "disallowed contract rejected"),
                FunctionalCaseClass("unsupported_chain", 1, "unsupported chain rejected"),
            ),
        ),
    }
)


def require_capability_template(capability_id: Capability) -> CapabilityTemplate:
    """Return a supported template without accepting arbitrary metadata names."""

    return CAPABILITY_TEMPLATES[capability_id]
