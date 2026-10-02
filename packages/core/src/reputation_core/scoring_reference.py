"""Executable policy-v1 reference, not an evidence collector or public scoring API.

Input counts must be derived from verified, purpose-separated observations.
No network, database, clock, random values, or fixture labels are used here.
All calculations retain exact rational values until output formatting.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

SCALE = 10_000


def _count(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _flag(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _bp(value: Fraction | None) -> int | None:
    if value is None:
        return None
    if not 0 <= value <= 1:
        raise ValueError("ratio outside [0, 1]")
    scaled = value * SCALE
    return (2 * scaled.numerator + scaled.denominator) // (2 * scaled.denominator)


def _ratio(n: int, d: int) -> Fraction:
    return Fraction(n, d) if d else Fraction(0)


def _quality(n: int, planned: int, required: int, age: Any, ttl: int) -> tuple[Fraction, Fraction, Fraction]:
    if required <= 0 or ttl <= 0 or n > planned:
        raise ValueError("invalid sample requirement or planned count")
    if age is None:
        if n:
            raise ValueError("decided evidence requires oldest_age_seconds")
        freshness = Fraction(0)
    else:
        age = _count(age, "oldest_age_seconds")
        freshness = max(Fraction(0), Fraction(ttl - age, ttl)) if n else Fraction(0)
    return _ratio(n, planned), min(Fraction(n, required), Fraction(1)), freshness


def _dimension(state: str, observed: Fraction | None, quality: tuple[Fraction, Fraction, Fraction], reasons: list[str]) -> tuple[dict[str, Any], Fraction | None, Fraction]:
    cov, sample, fresh = quality
    q = min(cov, sample, fresh)
    official = observed if state == "COMPLETE" else None
    return ({
        "state": state,
        "score_bp": _bp(official),
        "observed_score_bp": _bp(observed),
        "coverage_bp": _bp(cov),
        "sample_bp": _bp(sample),
        "freshness_bp": _bp(fresh),
        "sufficiency_bp": _bp(q),
        "reason_codes": reasons,
    }, official, q)


def evaluate_from_stats(data: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Compute a frozen report result. Input is trusted derived stats, never raw client input.

    age values are measured at a fixed report evaluation timestamp supplied by the
    caller. Current-age display overlays belong outside the immutable report.
    """
    if policy.get("policy_version") != "policy-v1" or policy.get("score_scale") != SCALE:
        raise ValueError("reference implementation only accepts policy-v1 at scale 10000")
    profile = data["profile"]
    if profile not in policy["profiles"]:
        raise ValueError("unsupported profile")
    weights = policy["profiles"][profile]["weights_bp"]
    expected_dims = {"availability", "consistency", "behavior"} if profile == "record-write-v1" else {"availability", "consistency"}
    if set(weights) != expected_dims or sum(_count(v, "weight") for v in weights.values()) != SCALE:
        raise ValueError("invalid profile weights")
    for section, fields in [("availability", ("valid_response_weight_bp", "latency_weight_bp")), ("consistency", ("mapping_weight_bp", "functional_weight_bp"))]:
        if sum(_count(policy[section][f], f) for f in fields) != SCALE:
            raise ValueError("invalid component weights")
    ttl = _count(policy["gates"]["freshness_ttl_seconds"], "ttl")
    min_cov = Fraction(_count(policy["gates"]["min_coverage_bp"], "min_coverage"), SCALE)
    min_q = Fraction(_count(policy["gates"]["min_sufficiency_bp"], "min_sufficiency"), SCALE)
    if not 0 <= min_cov <= 1 or not 0 <= min_q <= 1:
        raise ValueError("invalid gate")
    dimensions: dict[str, Any] = {}
    values: dict[str, Fraction | None] = {}
    qualities: dict[str, Fraction] = {}

    a = data["availability"]
    n, planned, s, l = [_count(a[k], k) for k in ("decided", "planned", "responded", "within_latency")]
    if not l <= s <= n <= planned:
        raise ValueError("availability counts must satisfy latency <= responded <= decided <= planned")
    amin = _count(policy["availability"]["min_samples"], "min_samples")
    aq = _quality(n, planned, amin, a.get("oldest_age_seconds"), ttl)
    av = (Fraction(policy["availability"]["valid_response_weight_bp"], SCALE) * Fraction(s, n)
          + Fraction(policy["availability"]["latency_weight_bp"], SCALE) * Fraction(l, n)) if n else None
    ar = ([] if n >= amin else ["INSUFFICIENT_SAMPLES"]) + ([] if aq[0] >= min_cov else ["INSUFFICIENT_COVERAGE"])
    dimensions["availability"], values["availability"], qualities["availability"] = _dimension("UNKNOWN" if not n else ("COMPLETE" if not ar else "PARTIAL"), av, aq, ar)

    caps = data["capabilities"]
    if not isinstance(caps, list):
        raise ValueError("capabilities must be a list")
    uncovered = _count(data.get("uncovered_claim_count", 0), "uncovered_claim_count")
    ids: set[str] = set()
    b_values: list[Fraction] = []
    b_qualities: list[tuple[Fraction, Fraction, Fraction]] = []
    b_reasons: list[str] = []
    all_complete = bool(caps) and not uncovered
    bmin = _count(policy["consistency"]["min_cases_per_capability"], "min_cases")
    b_total_n = b_total_planned = known_mapping = 0
    per_capability: list[dict[str, Any]] = []
    for c in caps:
        cid = c["capability_id"]
        if not isinstance(cid, str) or not cid or cid in ids:
            raise ValueError("capability identifiers must be nonempty and unique")
        if profile == "record-read-v1" and cid == "anchor_record":
            raise ValueError("read-only profile cannot include an anchor_record claim")
        ids.add(cid)
        cn, cp, passed = [_count(c[k], k) for k in ("decided", "planned", "passed")]
        if not passed <= cn <= cp:
            raise ValueError("capability counts invalid")
        mapping = c.get("mapping")
        if mapping is not None and (type(mapping) is not int or mapping not in (0, 1)):
            raise ValueError("mapping must be 0, 1 or null")
        classes_ok = _flag(c.get("required_classes_decided", False), "required_classes_decided")
        cq = _quality(cn, cp, bmin, c.get("oldest_age_seconds"), ttl)
        cv = (Fraction(policy["consistency"]["mapping_weight_bp"] * mapping, SCALE)
              + Fraction(policy["consistency"]["functional_weight_bp"], SCALE) * Fraction(passed, cn)) if mapping is not None and cn else None
        reasons = []
        if mapping is None:
            reasons.append("MAPPING_UNCONFIRMED")
        else:
            known_mapping += 1
        if cn < bmin:
            reasons.append("INSUFFICIENT_SAMPLES")
        if cq[0] < min_cov or not classes_ok:
            reasons.append("INSUFFICIENT_COVERAGE")
        all_complete = all_complete and not reasons
        if cv is not None:
            b_values.append(cv)
        b_qualities.append(cq)
        b_total_n += cn
        b_total_planned += cp
        b_reasons.extend(reasons)
        per_capability.append({"capability_id": cid, "observed_score_bp": _bp(cv), "reason_codes": reasons})
    if uncovered:
        b_reasons.append("UNCOVERED_CLAIMS")
    if not caps:
        b_reasons.append("INSUFFICIENT_SAMPLES")
    total_claims = len(caps) + uncovered
    b_cov = min(_ratio(b_total_n, b_total_planned), _ratio(known_mapping, total_claims)) if total_claims else Fraction(0)
    b_sample = min((q[1] for q in b_qualities), default=Fraction(0))
    if uncovered:
        b_sample = Fraction(0)  # An uncovered required claim has no valid samples.
    b_fresh = min((q[2] for q in b_qualities), default=Fraction(0))
    b_observed = sum(b_values, Fraction(0)) / len(b_values) if b_values else None
    b_state = "COMPLETE" if all_complete else ("PARTIAL" if b_total_n else "UNKNOWN")
    dimensions["consistency"], values["consistency"], qualities["consistency"] = _dimension(b_state, b_observed, (b_cov, b_sample, b_fresh), sorted(set(b_reasons)))
    dimensions["consistency"]["capabilities"] = per_capability

    binding_ok = _flag(data.get("attribution_verified", False), "attribution_verified")
    critical = _flag(data.get("critical_conflict", False), "critical_conflict")
    if profile == "record-write-v1":
        t = data["behavior"]
        tn, tp, accepted, correct = [_count(t[k], k) for k in ("decided", "planned", "accepted", "correct")]
        if not correct <= tn <= accepted <= tp:
            raise ValueError("behavior counts must satisfy correct <= decided <= accepted <= planned")
        tmin = _count(policy["behavior"]["min_accepted_decided_tasks"], "behavior_min")
        tq = _quality(tn, tp, tmin, t.get("oldest_age_seconds"), ttl)
        tv = Fraction(correct, tn) if tn else None
        tr = ([] if tn >= tmin else ["INSUFFICIENT_SAMPLES"]) + ([] if tq[0] >= min_cov else ["INSUFFICIENT_COVERAGE"])
        if not binding_ok:
            tq, tv, tr = (Fraction(0), Fraction(0), Fraction(0)), None, ["BINDING_UNVERIFIED"]
        tstate = "UNKNOWN" if tv is None else ("COMPLETE" if not tr else "PARTIAL")
        dimensions["behavior"], values["behavior"], qualities["behavior"] = _dimension(tstate, tv, tq, tr)
    else:
        if data.get("behavior") is not None:
            raise ValueError("read-only profile must not contain behavior samples")
        dimensions["behavior"] = {"state": "NOT_APPLICABLE", "score_bp": None, "observed_score_bp": None, "coverage_bp": None, "sample_bp": None, "freshness_bp": None, "sufficiency_bp": None, "reason_codes": ["NOT_DECLARED_READ_ONLY"]}

    q = min(qualities.values(), default=Fraction(0))
    complete = all(values[k] is not None for k in weights)
    gate_ok = complete and q >= min_q and (profile != "record-write-v1" or binding_ok)
    overall = sum((values[k] * Fraction(w, SCALE) for k, w in weights.items()), Fraction(0)) if gate_ok else None
    rec = policy["recommendation"]
    if critical and rec["critical_conflict_veto"]:
        advice = "NOT_RECOMMENDED"
    elif overall is None:
        advice = "INSUFFICIENT_EVIDENCE"
    elif overall < Fraction(rec["limited_total_min_bp"], SCALE):
        advice = "NOT_RECOMMENDED"
    elif overall >= Fraction(rec["recommended_total_min_bp"], SCALE) and all(values[k] >= Fraction(rec["recommended_dimension_min_bp"], SCALE) for k in weights):
        advice = "RECOMMENDED_WITHIN_SCOPE"
    else:
        advice = "LIMITED_OR_MANUAL_REVIEW"
    return {
        "policy_version": policy["policy_version"], "profile": profile,
        "evaluation_state": "COMPLETE" if gate_ok else "PARTIAL",
        "dimensions": dimensions, "overall_score_bp": _bp(overall),
        "sufficiency_bp": _bp(q), "advice": advice,
        "critical_conflict": critical,
        "limitations": ["Engineering policy index; not a calibrated trust probability.", "Input statistics must be independently derived from attributable evidence."],
    }
