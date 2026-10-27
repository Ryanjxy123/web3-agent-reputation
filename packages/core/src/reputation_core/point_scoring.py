"""Versioned single scores from known judgments; coverage remains independent."""
from reputation_core.admission import Verdict
from reputation_core.shared_scoring import (
    DIMENSIONS, ScoreInterval, SharedAssessmentResult, SharedCapabilityResult,
    SharedDimensionResult, _case_result, _counts, _coverage, _timings,
)


def _point(value):
    value = round(value, 2)
    return ScoreInterval(lower=value, upper=value)


def _mean_points(values):
    known = [value for value in values if value is not None]
    return _point(sum(value.lower for value in known) / len(known)) if known else None


def _point_case(case, observations, tasks):
    result = _case_result(case, observations, tasks)
    known = result.counts.passed + result.counts.failed
    # Derive the point from counts, never from either endpoint of a previous interval.
    result.interval = (_point(100 * result.counts.passed / known)
                       if known and not result.blocked_reasons else None)
    return result


def _capability_dimension(capability, dimension, cases, results, observations, tasks):
    chosen = [case for case in cases if case.capability_id == capability.capability_id
              and case.dimension == dimension]
    selected = [results[case.case_id] for case in chosen]
    blocked = [reason for result in selected for reason in result.blocked_reasons]
    coverage = [result.coverage for result in selected]
    if dimension == 'functional':
        groups = [group for group in capability.declaration_groups if group.selected]
        points = []
        for group in groups:
            members = [results[case.case_id] for case in chosen
                       if case.declaration_group_id == group.group_id]
            points.append(_mean_points([member.interval for member in members]))
            if not members:
                coverage.append('NONE')
        interval = _mean_points(points)
        if not groups:
            blocked.append('该功能尚未选择有来源的声明组，未形成可判功能分。')
    else:
        interval = _mean_points([result.interval for result in selected])
    if dimension == 'behavioral':
        if not capability.write_operation:
            blocked.append('该功能没有适用的链上写入履约，不填100或重新分配权重。')
        elif not any(case.normal_execution for case in chosen):
            blocked.append('已选写入范围尚未安排正常真实履约案例。')
        if blocked:
            interval = None
    if interval is None and not blocked:
        blocked.append('该功能在此维度尚无可判证据，标记未测，不借用其它功能结果。')
    p50, p95 = _timings([item for item in observations
                        if item.case_id in {case.case_id for case in chosen}])
    return SharedDimensionResult(interval=interval, counts=_counts(chosen, observations, tasks),
        coverage=_coverage(coverage), blocked_reasons=list(dict.fromkeys(blocked)),
        p50_ms=p50, p95_ms=p95, case_ids=[case.case_id for case in chosen])


def calculate_point_assessment(assessment) -> SharedAssessmentResult:
    """Known P/(P+V), then equal cases/groups/capabilities and fixed 30/40/30."""
    tasks = {task.task_key: task for task in assessment.tasks}
    cases, observations = assessment.cases, assessment.observations
    results = {case.case_id: _point_case(case, observations, tasks) for case in cases}
    capabilities, catalog_coverage = [], []
    for capability in assessment.capabilities:
        dimensions = {dimension: _capability_dimension(capability, dimension, cases, results,
            observations, tasks) for dimension in DIMENSIONS}
        groups = []
        for group in capability.declaration_groups:
            matching = [result.coverage for result in results.values()
                        if result.capability_id == capability.capability_id
                        and result.dimension == 'functional' and result.declaration_group_id == group.group_id]
            groups.append(_coverage(matching) if capability.selected and group.selected else 'NONE')
        declaration_coverage = _coverage(groups)
        catalog_coverage.extend(groups or ['NONE'])
        capabilities.append(SharedCapabilityResult(capability_id=capability.capability_id,
            title=capability.title, selected=capability.selected,
            declaration_coverage=declaration_coverage, **dimensions))
    selected = [capability for capability in capabilities if capability.selected]
    writable = {capability.capability_id for capability in assessment.capabilities if capability.write_operation}
    aggregate = {}
    for dimension in DIMENSIONS:
        eligible = [capability for capability in selected
                    if dimension != 'behavioral' or capability.capability_id in writable]
        values = [getattr(capability, dimension) for capability in eligible]
        # A/F absent evidence is visible but cannot supply a point. Normal B targets remain mandatory.
        blocked = ([reason for value in values for reason in value.blocked_reasons]
                   if dimension == 'behavioral' else [])
        interval = None if blocked else _mean_points([value.interval for value in values])
        if interval is None and not blocked:
            blocked.append('整个已选范围在此维度尚无可判证据，暂不发布本维度与综合分。')
        chosen = [case for case in cases if case.dimension == dimension]
        p50, p95 = _timings([item for item in observations if item.dimension == dimension])
        aggregate[dimension] = SharedDimensionResult(interval=interval,
            counts=_counts(chosen, observations, tasks), coverage=_coverage([value.coverage for value in values]),
            blocked_reasons=list(dict.fromkeys(blocked)), p50_ms=p50, p95_ms=p95,
            case_ids=[case.case_id for case in chosen])
    bounds = [aggregate[dimension].interval for dimension in DIMENSIONS]
    overall = (_point(sum(value.lower * weight for value, weight in zip(bounds, (.3, .4, .3))))
               if selected and all(value is not None for value in bounds) else None)
    major = any(item.critical and item.measurement_validity == 'valid' and item.verdict == Verdict.FAIL
                for item in observations)
    return SharedAssessmentResult(overall=overall, score_status='AVAILABLE' if overall else 'INSUFFICIENT',
        selected_scope_coverage=_coverage([getattr(capability, dimension).coverage for capability in selected
            for dimension in DIMENSIONS if dimension != 'behavioral' or capability.capability_id in writable]),
        declaration_coverage=_coverage(catalog_coverage), **aggregate, capabilities=capabilities,
        cases=list(results.values()), task_count=len(tasks), observation_count=len(observations),
        selected_capabilities=[capability.capability_id for capability in selected],
        unselected_capabilities=[capability.capability_id for capability in capabilities if not capability.selected],
        risk_status='MAJOR_VIOLATION' if major else 'NORMAL',
        blocked_reasons=list(dict.fromkeys(reason for value in aggregate.values() for reason in value.blocked_reasons)))
