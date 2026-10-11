import { describe, expect, it } from 'vitest';
import type { ReportView } from '../src/api/client';
import { dimensionLabels, evaluationRequest, MAX_VERIFIER_IMPORT_BYTES, parseVerifierCliJson, readVerifierCliFile, reportComparison, reportSampleSections, scoreLabel, taskEvidenceSections, verifierHashMatch } from '../src/model';

function report(): ReportView {
  return {
    report_id: 'report', report_hash: 'hash',
    core: {
      agent_ref: { namespace: 'eip155', chain_id: '31337', registry_address: 'registry', agent_id: '1' },
      agent_key_hash: 'agent', snapshot_hash: 'snapshot', run_id: 'run', profile: 'record-write-v1',
      schema_version: '1.5.0', policy_version: 'policy-v1', policy_hash: 'policy', code_version: 'code',
      evaluated_at: '2026-10-12T00:00:00Z', observation_start: '2026-10-12T00:00:00Z', observation_end: '2026-10-12T00:00:00Z',
      scoring_rule_version: 'three-dimensional-v1', assessment_rule_version: 'evidence-assessment-v1',
      evidence_manifest_hash: 'manifest', previous_report_hash: 'previous', limitations: [],
      scores: { policy_version: 'policy-v1', profile: 'record-write-v1', evaluation_state: 'COMPLETE', dimensions: {}, overall_score_bp: 10000, sufficiency_bp: 10000, advice: 'RECOMMENDED_WITHIN_SCOPE', critical_conflict: false, limitations: [] },
      assertions: [], task_results: [], raw_statistics: {}, evidence_sufficiency: null, risk_assessment: null, task_counts: null, task_success_rate_bp: null,
    },
    manifest: {
      schema_version: 'evidence-manifest-v1', documents: [], evidence: [],
      publication: { trusted_chain_key: 'local-demo', chain: { chain_id: '31337', genesis_hash: 'genesis', deployment_instance_id: 'instance', registry_code_hash: 'registry', instance_hash: 'instance' }, contract: 'contract', publisher: 'publisher', confirmation_depth: 1, previous_report_hash: 'previous', head_sequence: 0, head_block_number: '0', head_block_hash: 'block', platform_instance_id: 'platform' },
    },
  };
}

describe('evaluation display and authorization inputs', () => {
  it('keeps a null formal score distinct from zero and has the backend three dimension keys', () => {
    expect(scoreLabel(null)).toBe('未形成正式评分');
    expect(scoreLabel(undefined)).toBe('未形成正式评分');
    expect(scoreLabel(0)).toBe('0.00 / 100');
    expect(dimensionLabels.map(item => item.key)).toEqual(['availability', 'consistency', 'behavior']);
  });

  it('builds only existing controlled or public readonly suites from existing grants', () => {
    const fields = { snapshotId: 'snapshot', reviewVersion: 1, grantIds: ['grant'], publicReadonly: false };
    expect(evaluationRequest(fields)).toMatchObject({ path: '/api/v1/evaluations', body: { suite_id: 'm1-smoke-v1', profile: 'record-write-v1', grant_ids: ['grant'] } });
    expect(evaluationRequest({ ...fields, publicReadonly: true, grantIds: ['http', 'mcp'] })).toMatchObject({ path: '/api/v1/public-readonly/evaluations', body: { profile: 'record-read-v1', capability_id: 'verify_record' } });
    expect(() => evaluationRequest({ ...fields, reviewVersion: 0 })).toThrow('review version');
    expect(() => evaluationRequest({ ...fields, publicReadonly: true, grantIds: ['same', 'same'] })).toThrow('两个不同');
    expect(() => evaluationRequest({ ...fields, publicReadonly: true })).toThrow('两个不同');
  });

  it('uses the matching read profiles and inputs for the other two local capabilities', () => {
    const fields = { snapshotId: 'snapshot', reviewVersion: 1, grantIds: ['grant'], publicReadonly: false, suiteId: 'capabilities-v1' as const };
    expect(evaluationRequest({ ...fields, capabilityId: 'get_tx_status', queryTxHash: 'tx', targetContract: 'old contract' }).body).toMatchObject({ profile: 'record-read-v1', query_tx_hash: 'tx', target_contract: null, record_executor: null });
    expect(evaluationRequest({ ...fields, capabilityId: 'verify_record', recordExecutor: 'executor', recordRequestId: 'request', recordHash: 'hash' }).body).toMatchObject({ profile: 'record-read-v1', capability_id: 'verify_record', record_executor: 'executor', record_request_id: 'request', record_hash: 'hash', query_tx_hash: null });
    expect(() => evaluationRequest({ ...fields, capabilityId: 'get_tx_status' })).toThrow('query_tx_hash');
    expect(() => evaluationRequest({ ...fields, capabilityId: 'verify_record' })).toThrow('executor');
    expect(() => evaluationRequest({ ...fields, suiteId: 'm1-smoke-v1', capabilityId: 'get_tx_status', queryTxHash: 'tx' })).toThrow('仅支持');
  });

  it('rejects different Agent, rules and incomplete reports as formal numeric comparisons', () => {
    const first = report();
    const second = report();
    expect(reportComparison(first, second)).toBeNull();
    second.core.agent_ref.agent_id = '2';
    expect(reportComparison(first, second)).toContain('不同 Agent');
    second.core.agent_ref.agent_id = '1';
    second.core.policy_hash = 'changed';
    expect(reportComparison(first, second)).toContain('不可直接比较');
    second.core.policy_hash = 'policy';
    second.core.scores.evaluation_state = 'PARTIAL';
    second.core.scores.overall_score_bp = null;
    expect(reportComparison(first, second)).toContain('证据不足');
  });

  it('projects actual backend sample and capability statistics without treating basis-point ratios as counts', () => {
    const selected = report();
    selected.core.raw_statistics = { availability: { planned: 20, decided: 18, responded: 17 }, capabilities: [{ capability_id: 'anchor_record', planned: 10, decided: 9, passed: 8, covered_classes: ['normal'] }], uncovered_claim_count: 2, private_note: 'exclude' };
    const result = reportSampleSections(selected);
    expect(result.statistics).toEqual({ availability: { planned: 20, decided: 18, responded: 17 }, capabilities: [{ capability_id: 'anchor_record', planned: 10, decided: 9, passed: 8, covered_classes: ['normal'] }], uncovered_claim_count: 2 });
    expect(result.dimensions).toBeNull();
    expect(result.capabilities).toBeNull();
    expect(reportSampleSections(report()).statistics).toEqual({});
  });

  it('shows task, response and chain facts without exposing unrelated identity or grant metadata', () => {
    const packet = {
      record: { evidence_id: 'evidence', path: 'blobs/hash.bin', blob_hash: 'hash', byte_count: 1, media_type: 'application/json' as const, source: 'input', observed_at: '2026-10-12T00:00:00Z', collector_version: 'v1', redaction_profile: 'credentials-v1' as const, trust_group: 'test' },
      body: { schema_version: 'record-verification-input-v1', slot: { task: { request_id: 'request' } }, agent_task_status: 'succeeded', agent_response: { status: 'succeeded' }, agent_result: { tx_hash: 'tx' }, evm: { results: { receipt: { status: '0x1' } } }, snapshot: { normalized_metadata: { private_note: 'not for this view' } }, grant: { operator: 'private' } },
    };
    const result = taskEvidenceSections(packet);
    expect(result.input).toEqual({ request_id: 'request' });
    expect(result.response).toMatchObject({ task_status: 'succeeded' });
    expect(result.chain).toEqual({ results: { receipt: { status: '0x1' } } });
    expect(JSON.stringify(result)).not.toContain('private');
    expect(() => taskEvidenceSections({ ...packet, body: null })).toThrow('受支持');
  });

  it('parses independent CLI results with bounded, allow-listed statuses and safe fields', () => {
    const reportHash = '0x' + 'a'.repeat(64);
    const result = parseVerifierCliJson({
      status: 'PASS', offline: 'PASS', report_hash: reportHash,
      task_results: [{ slot_id: 'slot-1', capability_id: 'verify_record', outcome: 'FAIL', reason_code: 'SEMANTIC_MISMATCH', live_chain: { status: 'CONFLICT', outcome: 'PASS', historical_outcome: 'FAIL', historical_reason_code: 'SEMANTIC_MISMATCH', reason: 'new chain state differs' } }],
      task_counts: { PASS: 0, FAIL: 1, UNKNOWN: 0, NOT_APPLICABLE: 0 }, task_count_comparison: 'MATCH', assessment_comparison: 'MATCH',
      anchor: { status: 'NOT_CHECKED', reason: 'trusted RPC was not configured' },
    });
    expect(result).toMatchObject({ status: 'PASS', reportHash, taskResults: [{ outcome: 'FAIL', liveChain: { status: 'CONFLICT', outcome: 'PASS', historicalOutcome: 'FAIL', historicalReasonCode: 'SEMANTIC_MISMATCH' } }], anchor: { status: 'NOT_CHECKED' } });
    expect(verifierHashMatch(result, reportHash)).toBe('MATCH');
    expect(verifierHashMatch(result, '0x' + 'b'.repeat(64))).toBe('MISMATCH');
    expect(() => parseVerifierCliJson({ status: 'PASS' })).toThrow('report_hash');
    expect(() => parseVerifierCliJson({ status: 'PASS', report_hash: 'banana' })).toThrow('十六进制摘要');
    expect(() => parseVerifierCliJson({ status: 'PASS', report_hash: reportHash, offline: 'VERIFIED' })).toThrow('状态无效');
    expect(() => parseVerifierCliJson({ status: 'PASS', report_hash: reportHash, task_results: [{ slot_id: 'slot', capability_id: 'x', outcome: 'BROKEN' }] })).toThrow('状态无效');
    expect(() => parseVerifierCliJson({ status: 'PASS', report_hash: reportHash, task_counts: { PASS: -1 } })).toThrow('无效');
  });

  it('keeps FAIL CLI output unassociated when it has no report hash', () => {
    const result = parseVerifierCliJson({ status: 'FAIL', code: 'REPLAY_MISMATCH', message: 'frozen evidence mismatch' });
    expect(result).toMatchObject({ status: 'FAIL', code: 'REPLAY_MISMATCH', message: 'frozen evidence mismatch', reportHash: null });
    expect(verifierHashMatch(result, '0x' + 'a'.repeat(64))).toBe('NO_HASH');
    expect(verifierHashMatch(result, null)).toBe('NO_HASH');
  });

  it('rejects oversized and malformed local files without rendering arbitrary imported metadata', async () => {
    let read = false;
    await expect(readVerifierCliFile({ size: MAX_VERIFIER_IMPORT_BYTES + 1, text: async () => { read = true; return '{}'; } })).rejects.toThrow('1 MiB');
    expect(read).toBe(false);
    await expect(readVerifierCliFile({ size: 1, text: async () => 'not JSON' })).rejects.toThrow('有效 JSON');
    const result = await readVerifierCliFile({ size: 1, text: async () => JSON.stringify({ status: 'FAIL', code: 'REPLAY_MISMATCH', message: 'mismatch', private_note: 'must-not-display' }) });
    expect(JSON.stringify(result)).not.toContain('must-not-display');
  });
});
