import type { EvaluationCreate, PublicReadonlyEvaluationCreate, ReportView } from './api/client';
import type { components } from './api/generated/schema';

export const dimensionLabels = [
  { key: 'availability', label: '服务可用性' },
  { key: 'consistency', label: '功能声明一致性' },
  { key: 'behavior', label: '交易行为可靠性' },
] as const;

export function scoreLabel(value: number | null | undefined): string {
  return value == null ? '未形成正式评分' : `${(value / 100).toFixed(2)} / 100`;
}

export function reportSampleSections(report: ReportView): {
  statistics: Record<string, components['schemas']['JsonValue']>;
  dimensions: components['schemas']['EvidenceSufficiency']['dimensions'] | null;
  capabilities: components['schemas']['EvidenceSufficiency']['capabilities'] | null;
} {
  const keys = ['availability', 'behavior', 'capabilities', 'uncovered_claim_count', 'uncovered_claims'];
  return {
    statistics: Object.fromEntries(keys.filter(key => key in report.core.raw_statistics).map(key => [key, report.core.raw_statistics[key]])),
    dimensions: report.core.evidence_sufficiency?.dimensions ?? null,
    capabilities: report.core.evidence_sufficiency?.capabilities ?? null,
  };
}

export function taskEvidenceSections(packet: components['schemas']['EvidencePacket']): { input: unknown; response: unknown; chain: unknown } {
  if (typeof packet.body !== 'object' || packet.body === null || !('schema_version' in packet.body)) {
    throw new Error('证据不是受支持的逐任务核验输入。');
  }
  if (packet.body.schema_version === 'record-verification-input-v1') {
    const body = packet.body as components['schemas']['RecordVerificationInput'];
    return { input: body.slot.task, response: { task_status: body.agent_task_status, response: body.agent_response, result: body.agent_result }, chain: body.evm };
  }
  if (packet.body.schema_version === 'public-readonly-verification-input-v1') {
    const body = packet.body as components['schemas']['PublicReadonlyVerificationInput'];
    return {
      input: body.slot.task,
      response: body.packets.filter(item => body.agent_evidence_refs.includes(item.record.evidence_id)),
      chain: body.packets.filter(item => body.business_evidence_refs.includes(item.record.evidence_id)),
    };
  }
  throw new Error('历史核验输入格式请通过独立 Verifier 查看。');
}

export function reportComparison(left: ReportView, right: ReportView): string | null {
  const a = left.core;
  const b = right.core;
  if (a.agent_ref.namespace !== b.agent_ref.namespace || a.agent_ref.chain_id !== b.agent_ref.chain_id
    || a.agent_ref.registry_address !== b.agent_ref.registry_address || a.agent_ref.agent_id !== b.agent_ref.agent_id) return '属于不同 Agent，不能比较。';
  const taskScope = (report: ReportView) => [...new Set((report.core.task_results ?? []).map(item => `${item.capability_id}:${item.rule_version}`))].sort().join(',');
  if (a.policy_hash !== b.policy_hash || a.profile !== b.profile || a.schema_version !== b.schema_version
    || a.scoring_rule_version !== b.scoring_rule_version || a.assessment_rule_version !== b.assessment_rule_version
    || taskScope(left) !== taskScope(right)) {
    return '规则、报告版本或评价范围不同，分数不可直接比较。';
  }
  if (a.scores.evaluation_state !== 'COMPLETE' || b.scores.evaluation_state !== 'COMPLETE') {
    return '至少一份报告证据不足，仅展示状态、风险和充分度变化。';
  }
  return null;
}

export const MAX_VERIFIER_IMPORT_BYTES = 1024 * 1024;
const verifierOutcomes = ['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'] as const;
const verifierLiveStatuses = ['NOT_REQUIRED', 'NOT_CHECKED', 'UNKNOWN', 'RESOLVED', 'CONFIRMED', 'CONFLICT'] as const;
const verifierComparisons = ['MATCH', 'MISMATCH', 'NOT_AVAILABLE_LEGACY_REPORT', 'UNKNOWN'] as const;
const verifierAnchorStatuses = ['CONFIRMED', 'NOT_CHECKED', 'UNKNOWN'] as const;

export type VerifierOutcome = (typeof verifierOutcomes)[number];
export type VerifierLiveStatus = (typeof verifierLiveStatuses)[number];
export type VerifierCliResult = {
  status: 'PASS' | 'FAIL';
  offline: 'PASS' | null;
  reportHash: string | null;
  code: string | null;
  message: string | null;
  taskResults: Array<{
    slotId: string;
    capabilityId: string;
    outcome: VerifierOutcome;
    reasonCode: string | null;
    liveChain: { status: VerifierLiveStatus; reason: string | null; reasonCode: string | null; outcome: VerifierOutcome | null; historicalOutcome: VerifierOutcome | null; historicalReasonCode: string | null } | null;
  }>;
  taskCounts: Partial<Record<VerifierOutcome, number>> | null;
  taskCountComparison: string | null;
  assessmentComparison: string | null;
  anchor: { status: (typeof verifierAnchorStatuses)[number]; reason: string | null; confirmations: number | null } | null;
};

function recordText(value: unknown, field: string, max = 512): string | null {
  if (value == null) return null;
  if (typeof value !== 'string' || value.trim().length === 0 || value.length > max) throw new Error(`Verifier ${field} 字段无效。`);
  return value;
}

function recordStatus<T extends readonly string[]>(value: unknown, values: T, field: string): T[number] {
  if (typeof value !== 'string' || !values.includes(value)) throw new Error(`Verifier ${field} 状态无效。`);
  return value as T[number];
}

function recordObject(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error(`Verifier ${field} 必须是对象。`);
  return value as Record<string, unknown>;
}

export function parseVerifierCliJson(value: unknown): VerifierCliResult {
  const root = recordObject(value, '结果');
  const status = recordStatus(root.status, ['PASS', 'FAIL'] as const, '顶层') as 'PASS' | 'FAIL';
  const reportHash = recordText(root.report_hash, 'report_hash', 200);
  if (reportHash && !/^0x[0-9a-fA-F]{64}$/.test(reportHash)) throw new Error('Verifier report_hash 必须为 0x 加 64 位十六进制摘要。');
  const offline = root.offline == null ? null : recordStatus(root.offline, ['PASS'] as const, 'offline') as 'PASS';
  const code = recordText(root.code, 'code', 128);
  const message = recordText(root.message, 'message', 1024);
  if (status === 'PASS' && !reportHash) throw new Error('Verifier PASS 结果缺少 report_hash。');
  if (status === 'FAIL' && (!code || !message)) throw new Error('Verifier FAIL 结果需要 code 和 message。');

  const rawTasks = root.task_results;
  if (rawTasks != null && (!Array.isArray(rawTasks) || rawTasks.length > 200)) throw new Error('Verifier task_results 数量无效。');
  const taskResults = (rawTasks ?? []).map((item, index) => {
    const task = recordObject(item, `task_results[${index}]`);
    const slotId = recordText(task.slot_id, `task_results[${index}].slot_id`, 200);
    const capabilityId = recordText(task.capability_id, `task_results[${index}].capability_id`, 128);
    if (!slotId || !capabilityId) throw new Error(`Verifier task_results[${index}] 缺少任务标识。`);
    const outcome = recordStatus(task.outcome, verifierOutcomes, `task_results[${index}].outcome`) as VerifierOutcome;
    const reasonCode = recordText(task.reason_code, `task_results[${index}].reason_code`, 128);
    let liveChain: VerifierCliResult['taskResults'][number]['liveChain'] = null;
    if (task.live_chain != null) {
      const live = recordObject(task.live_chain, `task_results[${index}].live_chain`);
      liveChain = {
        status: recordStatus(live.status, verifierLiveStatuses, `task_results[${index}].live_chain`) as VerifierLiveStatus,
        reason: recordText(live.reason, `task_results[${index}].live_chain.reason`, 512),
        reasonCode: recordText(live.reason_code, `task_results[${index}].live_chain.reason_code`, 128),
        outcome: live.outcome == null ? null : recordStatus(live.outcome, verifierOutcomes, `task_results[${index}].live_chain.outcome`) as VerifierOutcome,
        historicalOutcome: live.historical_outcome == null ? null : recordStatus(live.historical_outcome, verifierOutcomes, `task_results[${index}].live_chain.historical_outcome`) as VerifierOutcome,
        historicalReasonCode: recordText(live.historical_reason_code, `task_results[${index}].live_chain.historical_reason_code`, 128),
      };
    }
    return { slotId, capabilityId, outcome, reasonCode, liveChain };
  });

  let taskCounts: VerifierCliResult['taskCounts'] = null;
  if (root.task_counts != null) {
    const rawCounts = recordObject(root.task_counts, 'task_counts');
    taskCounts = {};
    for (const outcome of verifierOutcomes) {
      const count = rawCounts[outcome];
      if (count == null) continue;
      if (typeof count !== 'number' || !Number.isInteger(count) || count < 0 || count > 100000) throw new Error(`Verifier task_counts.${outcome} 无效。`);
      taskCounts[outcome] = count;
    }
  }
  const taskCountComparison = root.task_count_comparison == null ? null : recordStatus(root.task_count_comparison, verifierComparisons, 'task_count_comparison');
  const assessmentComparison = root.assessment_comparison == null ? null : recordStatus(root.assessment_comparison, verifierComparisons, 'assessment_comparison');
  let anchor: VerifierCliResult['anchor'] = null;
  if (root.anchor != null) {
    const rawAnchor = recordObject(root.anchor, 'anchor');
    const confirmations = rawAnchor.confirmations == null ? null : rawAnchor.confirmations;
    if (confirmations != null && (typeof confirmations !== 'number' || !Number.isInteger(confirmations) || confirmations < 0)) throw new Error('Verifier anchor.confirmations 无效。');
    anchor = {
      status: recordStatus(rawAnchor.status, verifierAnchorStatuses, 'anchor') as (typeof verifierAnchorStatuses)[number],
      reason: recordText(rawAnchor.reason, 'anchor.reason', 512),
      confirmations: confirmations as number | null,
    };
  }
  return { status, offline, reportHash, code, message, taskResults, taskCounts, taskCountComparison, assessmentComparison, anchor };
}

export async function readVerifierCliFile(file: Pick<Blob, 'size' | 'text'>): Promise<VerifierCliResult> {
  if (file.size > MAX_VERIFIER_IMPORT_BYTES) throw new Error('Verifier JSON 超过 1 MiB，已拒绝读取。');
  const text = await file.text();
  if (new TextEncoder().encode(text).byteLength > MAX_VERIFIER_IMPORT_BYTES) throw new Error('Verifier JSON 超过 1 MiB，已拒绝读取。');
  let value: unknown;
  try { value = JSON.parse(text) as unknown; } catch { throw new Error('Verifier 文件不是有效 JSON。'); }
  return parseVerifierCliJson(value);
}

export function verifierHashMatch(result: VerifierCliResult | null, selectedReportHash: string | null): 'MATCH' | 'MISMATCH' | 'NO_HASH' | 'NO_REPORT' {
  if (!result?.reportHash) return 'NO_HASH';
  if (!selectedReportHash) return 'NO_REPORT';
  return result.reportHash.trim().toLowerCase() === selectedReportHash.trim().toLowerCase() ? 'MATCH' : 'MISMATCH';
}

export type StartFields = {
  snapshotId: string; reviewVersion: number; grantIds: string[]; publicReadonly: boolean;
  suiteId?: 'm1-smoke-v1' | 'capabilities-v1'; capabilityId?: EvaluationCreate['capability_id'];
  queryTxHash?: string; targetContract?: string; recordExecutor?: string; recordRequestId?: string; recordHash?: string;
};
export function evaluationRequest(fields: StartFields): { path: string; body: EvaluationCreate | PublicReadonlyEvaluationCreate } {
  if (!fields.snapshotId.trim() || !Number.isInteger(fields.reviewVersion) || fields.reviewVersion < 1 || !fields.grantIds.length) {
    throw new Error('请填写快照 UUID、正整数 review version 和已有授权 grant UUID。');
  }
  if (fields.publicReadonly) {
    if (fields.grantIds.length !== 2 || new Set(fields.grantIds).size !== 2) throw new Error('公共只读评价需要两个不同的 HTTP / MCP grant UUID。');
    return { path: '/api/v1/public-readonly/evaluations', body: {
      snapshot_id: fields.snapshotId.trim(), review_version: fields.reviewVersion, grant_ids: fields.grantIds,
      profile: 'record-read-v1', policy_version: 'policy-v1', suite_id: 'public-readonly-v1', capability_id: 'verify_record',
    } };
  }
  const suite = fields.suiteId ?? 'm1-smoke-v1';
  const capability = fields.capabilityId ?? 'anchor_record';
  if (suite === 'm1-smoke-v1' && capability !== 'anchor_record') throw new Error('m1-smoke-v1 仅支持 anchor_record。');
  if (capability === 'get_tx_status' && !fields.queryTxHash?.trim()) throw new Error('get_tx_status 需要 query_tx_hash。');
  if (capability === 'verify_record' && (!fields.recordExecutor?.trim() || !fields.recordRequestId?.trim() || !fields.recordHash?.trim())) {
    throw new Error('verify_record 需要 executor、request_id 和 record_hash。');
  }
  return { path: '/api/v1/evaluations', body: {
    snapshot_id: fields.snapshotId.trim(), review_version: fields.reviewVersion, grant_ids: fields.grantIds,
    profile: capability === 'anchor_record' ? 'record-write-v1' : 'record-read-v1', policy_version: 'policy-v1', suite_id: suite, capability_id: capability,
    query_tx_hash: capability === 'get_tx_status' ? fields.queryTxHash?.trim() ?? null : null,
    record_executor: capability === 'verify_record' ? fields.recordExecutor?.trim() ?? null : null,
    record_request_id: capability === 'verify_record' ? fields.recordRequestId?.trim() ?? null : null,
    record_hash: capability === 'verify_record' ? fields.recordHash?.trim() ?? null : null,
    target_contract: capability === 'get_tx_status' ? null : fields.targetContract?.trim() || null, transaction_cases: null,
  } };
}
