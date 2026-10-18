"""Select the implemented historical-liquidity verifier from backend source descriptors."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import CandidateRecord, Verdict
from reputation_core.claims import DeclarationAnalysis


class LiquidityHistoryDescriptor(BaseModel):
    """Backend-parsed source locations and claimed identifiers, not verified chain facts."""

    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    claim_ids: list[str]
    chain_id: int | None = None
    protocol: str | None = None
    history_shape: str | None = None
    history_source_file: str | None = None
    history_json_path: str | None = None
    published_execution_wallet: str | None = None
    trusted_manager: str | None = None


class PlanSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    status: Literal["SELECTED", "NEEDS_INFO", "UNSUPPORTED"]
    policy_id: Literal["liquidity-history-v1"] | None
    claim_ids: list[str]
    reasons: list[str]
    pending_evidence: list[str]


def select_plan(
    analysis: DeclarationAnalysis, candidate: CandidateRecord,
    descriptor: LiquidityHistoryDescriptor,
) -> PlanSelection:
    """Select a verifier; the caller must first source-validate the declaration analysis."""
    pending = [f"{check.code.value}: {check.status.value}"
               for check in candidate.checks if check.status != Verdict.PASS]
    pending.append("Selection does not authorize execution or establish publication/sample sufficiency")

    def result(status: str, reasons: list[str]) -> PlanSelection:
        return PlanSelection(
            candidate_key=candidate.key, status=status,
            policy_id="liquidity-history-v1" if status == "SELECTED" else None,
            claim_ids=descriptor.claim_ids if status == "SELECTED" else [],
            reasons=reasons, pending_evidence=pending,
        )

    if descriptor.candidate_key != candidate.key:
        return result("NEEDS_INFO", ["Source descriptor belongs to a different candidate"])
    ids = [claim.claim_id for claim in analysis.claims]
    if len(ids) != len(set(ids)):
        return result("NEEDS_INFO", ["Declaration analysis contains duplicate claim_id values"])
    if not descriptor.claim_ids or len(descriptor.claim_ids) != len(set(descriptor.claim_ids)):
        return result("NEEDS_INFO", ["Source descriptor requires nonempty, unique claim_ids"])
    claims = {claim.claim_id: claim for claim in analysis.claims}
    if any(claim_id not in claims for claim_id in descriptor.claim_ids):
        return result("NEEDS_INFO", ["Referenced claim_id is absent from the source-validated analysis"])
    if any(not claims[claim_id].citations or any(not citation.source_id.strip() or not citation.quote.strip()
           for citation in claims[claim_id].citations) for claim_id in descriptor.claim_ids):
        return result("NEEDS_INFO", ["Each selected claim requires a nonempty source citation"])
    missing = []
    if not candidate.registration_reference.strip():
        missing.append("A public registration reference is required")
    for name in ("chain_id", "protocol", "history_shape", "history_source_file", "history_json_path",
                 "published_execution_wallet", "trusted_manager"):
        value = getattr(descriptor, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"Missing source descriptor field: {name}")
    for name, supported in (("chain_id", 56), ("protocol", "pancakeswap-v3-npm"),
                            ("history_shape", "run-history-increase-v1")):
        value = getattr(descriptor, name)
        if value is not None and (not isinstance(value, str) or value.strip()) and value != supported:
            return result("UNSUPPORTED", [f"No implemented historical-liquidity plan for {name}={value}"])
    if descriptor.history_source_file and "://" in descriptor.history_source_file:
        missing.append("History source must identify a retained local file, not a remote endpoint")
    if descriptor.history_json_path and not descriptor.history_json_path.startswith("$"):
        missing.append("History source requires an explicit JSONPath location")
    for name in ("published_execution_wallet", "trusted_manager"):
        value = getattr(descriptor, name)
        if value and not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
            missing.append(f"Invalid address in source descriptor: {name}")
    if missing:
        return result("NEEDS_INFO", missing)
    return result("SELECTED", [
        "Source-backed historical increase records match the implemented BSC PancakeSwap V3 NPM plan",
        "Only public history reads and existing-transaction verification are selected; no new asset operations",
    ])
