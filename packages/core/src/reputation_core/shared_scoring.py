"""Pure, scope-specific scoring of shared task evidence and declaration cases."""
from datetime import datetime
from math import ceil, floor, isfinite
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.scoring import DimensionScore, ScoringOutcome, SHARED_POLICY_VERSION, MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION

Dimension = Literal['availability', 'functional', 'behavioral']
CoverageStatus = Literal['FULL', 'PARTIAL', 'NONE']
DIMENSIONS = ('availability', 'functional', 'behavioral')


class SharedModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ScoreInterval(SharedModel):
    lower: float
    upper: float

    @model_validator(mode='after')
    def valid_interval(self) -> Self:
        if not (isfinite(self.lower) and isfinite(self.upper) and 0 <= self.lower <= self.upper <= 100):
            raise ValueError('score interval must be finite and within 0..100')
        return self


class SharedDeclarationGroup(SharedModel):
    group_id: str
    title: str
    description: str = ''
    selected: bool
    selection_reason: str = ''
    source_references: list[str]


class SharedCapability(SharedModel):
    capability_id: str
    title: str
    description: str = ''
    selected: bool
    write_operation: bool
    declaration_groups: list[SharedDeclarationGroup]


class SharedCase(SharedModel):
    case_id: str
    capability_id: str
    dimension: Dimension
    declaration_group_id: str | None
    title: str
    criterion_ids: list[str]
    task_keys: list[str]
    normal_execution: bool
    required_decisive: int


class SharedTask(SharedModel):
    task_key: str
    capability_id: str
    input_summary: str
    outcome: Literal['completed', 'failed', 'rejected', 'protected_exit', 'not_executed', 'unknown']
    attribution: Literal['provider', 'operator', 'network', 'chain_or_market', 'unknown']
    observed_at: datetime | None
    evidence: list[str]


class SharedObservation(SharedModel):
    task_key: str
    case_id: str
    criterion_id: str
    dimension: Dimension
    verdict: Verdict
    reason: str
    evidence: list[str]
    measurement_validity: Literal['valid', 'invalid', 'unknown']
    elapsed_ms: float | None
    response_complete: bool | None = None
    critical: bool = False


class SharedCounts(SharedModel):
    planned: int = 0
    observed: int = 0
    passed: int = 0
    failed: int = 0
    unknown: int = 0
    not_applicable: int = 0
    measurement_invalid: int = 0
    not_run: int = 0
    protected_exit: int = 0


class SharedDimensionResult(SharedModel):
    interval: ScoreInterval | None
    counts: SharedCounts
    coverage: CoverageStatus
    blocked_reasons: list[str]
    p50_ms: float | None = None
    p95_ms: float | None = None
    case_ids: list[str]


class SharedCaseResult(SharedDimensionResult):
    case_id: str
    capability_id: str
    dimension: Dimension
    declaration_group_id: str | None
    title: str


class SharedCapabilityResult(SharedModel):
    capability_id: str
    title: str
    selected: bool
    declaration_coverage: CoverageStatus
    availability: SharedDimensionResult
    functional: SharedDimensionResult
    behavioral: SharedDimensionResult


class SharedAssessmentResult(SharedModel):
    overall: ScoreInterval | None
    score_status: Literal['AVAILABLE', 'INSUFFICIENT']
    selected_scope_coverage: CoverageStatus
    declaration_coverage: CoverageStatus
    availability: SharedDimensionResult
    functional: SharedDimensionResult
    behavioral: SharedDimensionResult
    capabilities: list[SharedCapabilityResult]
    cases: list[SharedCaseResult]
    task_count: int
    observation_count: int
    selected_capabilities: list[str]
    unselected_capabilities: list[str]
    risk_status: Literal['NORMAL', 'MAJOR_VIOLATION']
    blocked_reasons: list[str]


class SharedAssessment(SharedModel):
    schema_version: Literal['shared-task-assessment-v1', 'shared-task-assessment-v2', 'shared-task-assessment-v3'] = 'shared-task-assessment-v1'
    capabilities: list[SharedCapability]
    cases: list[SharedCase]
    tasks: list[SharedTask]
    observations: list[SharedObservation]

    @model_validator(mode='after')
    def valid_bindings(self) -> Self:
        capabilities = {item.capability_id: item for item in self.capabilities}
        cases = {item.case_id: item for item in self.cases}
        tasks = {item.task_key: item for item in self.tasks}
        if len(capabilities) != len(self.capabilities) or len(cases) != len(self.cases) or len(tasks) != len(self.tasks):
            raise ValueError('duplicate shared capability, case or task identifier')
        for capability in self.capabilities:
            groups = capability.declaration_groups
            if len({item.group_id for item in groups}) != len(groups):
                raise ValueError('duplicate declaration group')
            if not capability.selected and any(group.selected for group in groups):
                raise ValueError('an unselected capability cannot select a declaration group')
        for task in self.tasks:
            if task.capability_id not in capabilities:
                raise ValueError('task references a missing capability')
        for case in self.cases:
            capability = capabilities.get(case.capability_id)
            if capability is None or not capability.selected:
                raise ValueError('case must belong to a selected capability')
            if not case.criterion_ids or len(set(case.criterion_ids)) != len(case.criterion_ids):
                raise ValueError('case requires unique criterion identifiers')
            if len(set(case.task_keys)) != len(case.task_keys) or case.required_decisive < 1:
                raise ValueError('case requires unique tasks and a positive prospective evidence target')
            if case.task_keys and case.required_decisive > len(case.task_keys):
                raise ValueError('case evidence target exceeds its bound task plan')
            if any(key not in tasks or tasks[key].capability_id != case.capability_id for key in case.task_keys):
                raise ValueError('case references a missing or differently bound task')
            if case.normal_execution and (case.dimension != 'behavioral' or not capability.write_operation):
                raise ValueError('normal execution applies only to a write capability behavioral case')
            if case.dimension == 'functional':
                group = next((item for item in capability.declaration_groups
                              if item.group_id == case.declaration_group_id), None)
                if group is None or not group.selected:
                    raise ValueError('functional case requires a selected declaration group')
        seen = set()
        for item in self.observations:
            case = cases.get(item.case_id)
            if (case is None or case.dimension != item.dimension or item.task_key not in case.task_keys
                    or item.criterion_id not in case.criterion_ids):
                raise ValueError('observation differs from its frozen case, dimension or criterion')
            key = item.task_key, item.dimension, item.criterion_id
            if key in seen:
                raise ValueError('duplicate task/dimension/criterion observation')
            seen.add(key)
            if item.elapsed_ms is not None and (not isfinite(item.elapsed_ms) or item.elapsed_ms < 0):
                raise ValueError('elapsed time must be finite and nonnegative')
        return self

    @computed_field
    @property
    def result(self) -> SharedAssessmentResult:
        return calculate_shared_assessment(self)


def _interval(lower, upper):
    # Outward rounding never turns a nonzero unresolved range into a point.
    return ScoreInterval(lower=floor(lower * 100 + 1e-9) / 100,
                         upper=ceil(upper * 100 - 1e-9) / 100)


def _mean(values):
    if not values:
        return _interval(0, 100)
    return _interval(sum(item.lower for item in values) / len(values),
                     sum(item.upper for item in values) / len(values))


def _coverage(values):
    if values and all(value == 'FULL' for value in values):
        return 'FULL'
    return 'PARTIAL' if any(value != 'NONE' for value in values) else 'NONE'


def _timings(observations):
    values = sorted(item.elapsed_ms for item in observations
                    if item.dimension == 'availability' and item.measurement_validity == 'valid'
                    and item.elapsed_ms is not None
                    and (item.response_complete is True
                         or (item.response_complete is None and item.verdict == Verdict.PASS)))
    return ((values[ceil(.5 * len(values)) - 1], values[ceil(.95 * len(values)) - 1]) if values else (None, None))


def _verdict(items, expected, task, normal_execution):
    """One case/task is one conjunctive judgment, never several fake tasks."""
    if not items:
        return 'not_run'
    valid = [item for item in items if item.measurement_validity == 'valid']
    if any(item.verdict == Verdict.FAIL for item in valid):
        return 'failed'
    if normal_execution and task.outcome == 'protected_exit':
        return 'protected_exit'
    if all(item.measurement_validity == 'invalid' for item in items):
        return 'measurement_invalid'
    if len(items) < len(expected) or any(item.measurement_validity != 'valid' for item in items):
        return 'unknown'
    applicable = [item for item in items if item.verdict != Verdict.NOT_APPLICABLE]
    if not applicable:
        return 'not_applicable'
    if any(item.verdict == Verdict.UNKNOWN for item in applicable):
        return 'unknown'
    if normal_execution and task.outcome != 'completed':
        return 'not_run' if task.outcome in ('not_executed', 'rejected') else 'unknown'
    return 'passed'


def _counts(case_list, all_observations, tasks):
    keys = {key for case in case_list for key in case.task_keys}
    by_task = {key: [] for key in keys}
    observed = set()
    for case in case_list:
        for key in case.task_keys:
            items = [item for item in all_observations if item.case_id == case.case_id and item.task_key == key]
            if items:
                observed.add(key)
            by_task[key].append(_verdict(items, case.criterion_ids, tasks[key], case.normal_execution))
    counts = SharedCounts(planned=len(keys), observed=len(observed),
                          protected_exit=sum(tasks[key].outcome == 'protected_exit' for key in keys))
    order = ('failed', 'unknown', 'measurement_invalid', 'not_run', 'passed', 'not_applicable', 'protected_exit')
    for states in by_task.values():
        state = next(value for value in order if value in states)
        if state != 'protected_exit':
            setattr(counts, state, getattr(counts, state) + 1)
    return counts


def _case_result(case, observations, tasks):
    items = [item for item in observations if item.case_id == case.case_id]
    counts = _counts([case], items, tasks)
    criterion_coverage = []
    for criterion in case.criterion_ids:
        decisive = [item for item in items if item.criterion_id == criterion
                    and item.measurement_validity == 'valid' and item.verdict in (Verdict.PASS, Verdict.FAIL)
                    and (not case.normal_execution or tasks[item.task_key].outcome in ('completed', 'failed'))]
        criterion_coverage.append('FULL' if len(decisive) >= case.required_decisive else 'PARTIAL' if decisive else 'NONE')
    coverage = _coverage(criterion_coverage)
    blocked = []
    if case.normal_execution and coverage != 'FULL':
        interval = None
        blocked.append('正常履约案例尚未达到预先声明的可判执行目标；保护退出不替代正常履约证据。')
    else:
        unresolved = counts.unknown + counts.not_run + counts.measurement_invalid
        n = counts.passed + counts.failed + unresolved
        interval = (_interval(100 * counts.passed / n, 100 * (counts.passed + unresolved) / n)
                    if n else _interval(0, 100))
    p50, p95 = _timings(items)
    return SharedCaseResult(case_id=case.case_id, capability_id=case.capability_id,
        dimension=case.dimension, declaration_group_id=case.declaration_group_id, title=case.title,
        interval=interval, counts=counts, coverage=coverage, blocked_reasons=blocked,
        p50_ms=p50, p95_ms=p95, case_ids=[case.case_id])


def _dimension_result(capability, dimension, cases, results, observations, tasks, *, expanded=False):
    chosen = [case for case in cases if case.capability_id == capability.capability_id and case.dimension == dimension]
    selected_results = [results[case.case_id] for case in chosen]
    blocked = [reason for result in selected_results for reason in result.blocked_reasons]
    if dimension != 'behavioral':
        if not chosen:
            blocked.append('已选范围尚未安排该维度的评估案例。')
        elif not (expanded and dimension == 'availability') and not any(item.case_id in {case.case_id for case in chosen}
                     and item.measurement_validity == 'valid' and item.verdict in (Verdict.PASS, Verdict.FAIL)
                     for item in observations):
            blocked.append('该维度尚无可判观察，暂不发布范围主结果。')
    if dimension == 'functional' and not any(group.selected for group in capability.declaration_groups):
        blocked.append('已选功能尚未选择有来源的功能声明组。')
    if dimension == 'behavioral':
        if not capability.write_operation:
            blocked.append('该功能没有适用的链上写入履约，不能补成100或重新分配权重。')
        elif not any(case.normal_execution for case in chosen):
            blocked.append('已选写入范围尚未安排正常真实履约案例。')
    if blocked:
        interval = None
    elif dimension == 'functional':
        groups = [group for group in capability.declaration_groups if group.selected]
        interval = _mean([_mean([results[case.case_id].interval for case in chosen
                                if case.declaration_group_id == group.group_id]) for group in groups])
    else:
        interval = _mean([result.interval for result in selected_results])
    coverage_values = [result.coverage for result in selected_results]
    if dimension == 'functional':
        for group in capability.declaration_groups:
            if group.selected and not any(case.declaration_group_id == group.group_id for case in chosen):
                coverage_values.append('NONE')
    p50, p95 = _timings([item for item in observations if any(item.case_id == case.case_id for case in chosen)])
    return SharedDimensionResult(interval=interval, counts=_counts(chosen, observations, tasks),
        coverage=_coverage(coverage_values), blocked_reasons=list(dict.fromkeys(blocked)),
        p50_ms=p50, p95_ms=p95, case_ids=[case.case_id for case in chosen])


def calculate_shared_assessment(assessment: SharedAssessment) -> SharedAssessmentResult:
    if assessment.schema_version == 'shared-task-assessment-v3':
        from reputation_core.point_scoring import calculate_point_assessment
        return calculate_point_assessment(assessment)
    expanded = assessment.schema_version == 'shared-task-assessment-v2'
    tasks = {task.task_key: task for task in assessment.tasks}
    cases = assessment.cases
    results = {case.case_id: _case_result(case, assessment.observations, tasks) for case in cases}
    capability_results = []
    catalog_coverage = []
    for capability in assessment.capabilities:
        dimensions = {dimension: _dimension_result(capability, dimension, cases, results,
                                                   assessment.observations, tasks, expanded=expanded) for dimension in DIMENSIONS}
        groups = []
        for group in capability.declaration_groups:
            matching = [result.coverage for result in results.values()
                        if result.capability_id == capability.capability_id and result.dimension == 'functional'
                        and result.declaration_group_id == group.group_id]
            groups.append(_coverage(matching) if capability.selected and group.selected else 'NONE')
        declaration_coverage = _coverage(groups)
        catalog_coverage.extend(groups or ['NONE'])
        capability_results.append(SharedCapabilityResult(capability_id=capability.capability_id,
            title=capability.title, selected=capability.selected, declaration_coverage=declaration_coverage, **dimensions))
    selected = [item for item in capability_results if item.selected]
    aggregate = {}
    for dimension in DIMENSIONS:
        eligible = [item for item in selected if dimension != 'behavioral'
                    or next(cap.write_operation for cap in assessment.capabilities if cap.capability_id == item.capability_id)]
        dimension_results = [getattr(item, dimension) for item in eligible]
        blocked = [reason for result in dimension_results for reason in result.blocked_reasons]
        if not eligible:
            blocked.append('当前已选范围没有该维度适用的功能。')
        if expanded and dimension == 'availability':
            chosen_ids = {case.case_id for case in cases if case.dimension == dimension}
            if not any(item.case_id in chosen_ids and item.measurement_validity == 'valid'
                       and item.verdict in (Verdict.PASS, Verdict.FAIL) for item in assessment.observations):
                blocked.append('整个已选范围尚无有效可判的业务响应；未知区间不能单独充当可用性主结果。')
        interval = None if blocked else _mean([item.interval for item in dimension_results])
        chosen = [case for case in cases if case.dimension == dimension]
        p50, p95 = _timings([item for item in assessment.observations if item.dimension == dimension])
        aggregate[dimension] = SharedDimensionResult(interval=interval,
            counts=_counts(chosen, assessment.observations, tasks),
            coverage=_coverage([item.coverage for item in dimension_results]),
            blocked_reasons=list(dict.fromkeys(blocked)), p50_ms=p50, p95_ms=p95,
            case_ids=[case.case_id for case in chosen])
    bounds = [aggregate[dimension].interval for dimension in DIMENSIONS]
    has_decisive = any(item.measurement_validity == 'valid' and item.verdict in (Verdict.PASS, Verdict.FAIL)
                       for item in assessment.observations)
    overall = (_interval(sum(bound.lower * weight for bound, weight in zip(bounds, (.3, .4, .3))),
                         sum(bound.upper * weight for bound, weight in zip(bounds, (.3, .4, .3))))
               if selected and has_decisive and all(bound is not None for bound in bounds) else None)
    major = any(item.critical and item.measurement_validity == 'valid' and item.verdict == Verdict.FAIL
                for item in assessment.observations)
    return SharedAssessmentResult(overall=overall, score_status='AVAILABLE' if overall is not None else 'INSUFFICIENT',
        selected_scope_coverage=_coverage([getattr(item, dimension).coverage for item in selected
            for dimension in DIMENSIONS if dimension != 'behavioral'
            or next(cap.write_operation for cap in assessment.capabilities if cap.capability_id == item.capability_id)]),
        declaration_coverage=_coverage(catalog_coverage), **aggregate, capabilities=capability_results,
        cases=list(results.values()), task_count=len(tasks), observation_count=len(assessment.observations),
        selected_capabilities=[item.capability_id for item in selected],
        unselected_capabilities=[item.capability_id for item in capability_results if not item.selected],
        risk_status='MAJOR_VIOLATION' if major else 'NORMAL',
        blocked_reasons=list(dict.fromkeys(reason for value in aggregate.values() for reason in value.blocked_reasons)))


def shared_legacy_scores(assessment: SharedAssessment) -> ScoringOutcome:
    """Legacy fields carry only exact points; interval endpoints are never scores."""
    result = assessment.result
    dimensions = {}
    for dimension in DIMENSIONS:
        source = getattr(result, dimension)
        point = (source.interval.lower if source.interval is not None
                 and source.interval.lower == source.interval.upper else None)
        count = source.counts
        dimensions[dimension] = DimensionScore(value=point, planned=count.planned, observed=count.observed,
            passed=count.passed, failed=count.failed, unknown=count.unknown,
            not_applicable=count.not_applicable, p95_ms=source.p95_ms)
    point = (result.overall.lower if result.overall is not None
             and result.overall.lower == result.overall.upper else None)
    policy_version = {'shared-task-assessment-v1': SHARED_POLICY_VERSION,
                      'shared-task-assessment-v2': MULTICAP_POLICY_VERSION,
                      'shared-task-assessment-v3': POINT_POLICY_VERSION}[assessment.schema_version]
    return ScoringOutcome(policy_version=policy_version, **dimensions, overall=point,
        status='COMPLETE' if point is not None else 'PARTIAL' if assessment.observations else 'NOT_EVALUATED')
