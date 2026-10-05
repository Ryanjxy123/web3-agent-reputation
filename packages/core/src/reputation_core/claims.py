"""Deterministic declaration candidate extraction.

This is deliberately a narrow dictionary extractor.  It preserves where a
claim came from, but never confirms it, creates a task, or grants a score.
"""

import re
from dataclasses import dataclass
from typing import Literal

from .models.domain import Capability

Polarity = Literal["positive", "negative", "ambiguous"]
EXTRACTOR_VERSION = "dictionary-v1"


@dataclass(frozen=True)
class ClaimCandidateDraft:
    """An unreviewed declaration candidate with a Unicode code-point span."""

    field_path: str
    quote: str
    start: int
    end: int
    polarity: Polarity
    candidate_capability: Capability | None
    extractor_version: str = EXTRACTOR_VERSION


@dataclass(frozen=True)
class _Pattern:
    expression: re.Pattern[str]
    capability: Capability | None


_PATTERNS = (
    _Pattern(re.compile(r"链上存证|上链存证|anchor[_ ]?record|record anchoring", re.IGNORECASE), "anchor_record"),
    _Pattern(re.compile(r"不(?:支持|提供)(?:链上)?写入"), "anchor_record"),
    _Pattern(re.compile(r"查询交易状态|交易状态查询|get[_ ]?tx[_ ]?status|transaction status", re.IGNORECASE), "get_tx_status"),
    _Pattern(re.compile(r"只读核验|核验凭证|验证存证|verify[_ ]?record|verify credential", re.IGNORECASE), "verify_record"),
    _Pattern(re.compile(r"支持(?:所有|任意|多种)?(?:链上操作|区块链操作|web3 操作)", re.IGNORECASE), None),
)

_NEGATIVE = re.compile(
    r"(?:不(?:支持|提供|具备|执行)|暂不|无法|禁止|does\s+not|do\s+not|don't|cannot|can't|without)"
    r"(?:\s+(?:support|provide|perform|execute|anchor|write|verify|query))?",
    re.IGNORECASE,
)
_AMBIGUOUS = re.compile(r"(?:可能|计划|待支持|maybe|planned|\?)", re.IGNORECASE)
_CLAUSE_BREAK = re.compile(r"[。；;.!?\n，,]")


def _clause_before(document: str, start: int) -> str:
    """Return the local clause so a prior phrase cannot change this claim's meaning."""

    previous = [match.end() for match in _CLAUSE_BREAK.finditer(document, 0, start)]
    return document[previous[-1] if previous else 0 : start]


def _polarity(document: str, start: int, end: int) -> Polarity:
    clause = _clause_before(document, start)
    if _NEGATIVE.search(clause):
        return "negative"
    if _AMBIGUOUS.search(clause) or _AMBIGUOUS.search(document[start:end]):
        return "ambiguous"
    return "positive"


def extract_claim_candidates(document: str, field_path: str) -> tuple[ClaimCandidateDraft, ...]:
    """Extract non-overlapping capability declarations from one metadata field.

    Generic claims are retained with ``candidate_capability=None``.  A caller
    must attach evidence and obtain human review before constructing a domain
    ``CapabilityClaim`` or scheduling any test.
    """

    if not document:
        return ()
    if not field_path:
        raise ValueError("field_path is required")

    matches: list[tuple[int, int, Capability | None]] = []
    for pattern in _PATTERNS:
        matches.extend((match.start(), match.end(), pattern.capability) for match in pattern.expression.finditer(document))

    chosen: list[tuple[int, int, Capability | None]] = []
    for start, end, capability in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(start < selected_end and end > selected_start for selected_start, selected_end, _ in chosen):
            continue
        chosen.append((start, end, capability))

    return tuple(
        ClaimCandidateDraft(
            field_path=field_path,
            quote=document[start:end],
            start=start,
            end=end,
            polarity=_polarity(document, start, end),
            candidate_capability=capability,
        )
        for start, end, capability in chosen
    )
