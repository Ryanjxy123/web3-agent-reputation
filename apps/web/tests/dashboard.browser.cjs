const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

const baseUrl = process.env.WEB_SMOKE_ORIGIN || 'http://127.0.0.1:4173';
const reportHash = '0x' + 'a'.repeat(64);
const agentA = { id: 'agent-a', agent_ref: { namespace: 'eip155', chain_id: '31337', registry_address: 'registry', agent_id: '1' }, source_type: 'controlled', status: 'SNAPSHOT_CAPTURED', current_snapshot_id: 'snapshot-a' };
const agentB = { ...agentA, id: 'agent-b', agent_ref: { ...agentA.agent_ref, agent_id: '2' }, source_type: 'public_registry', status: 'UNVERIFIED', current_snapshot_id: null };
const snapshot = { snapshot_id: 'snapshot-a', snapshot_hash: 'snapshot-hash', evidence_refs: [], core: { agent_ref: agentA.agent_ref, source_type: 'controlled', owner: 'owner-of-agent-a', declared_executor: 'executor-a', captured_at: '2026-10-12T00:00:00Z', registry_revision: 1, read_block_number: '1', read_block_hash: 'block', normalized_metadata: { capabilities: ['anchor_record'] }, endpoints: [{ endpoint_id: 'fixture-a', protocol: 'controlled-http-v1', scheme: 'http', host: '127.0.0.1', port: 8101, path: '/tasks' }] } };
const dim = { state: 'UNKNOWN', score_bp: null, observed_score_bp: null, coverage_bp: 0, sample_bp: 0, reason_codes: ['INSUFFICIENT_SAMPLES'] };
const report = { report_id: 'report-a', report_hash: reportHash, core: { agent_ref: agentA.agent_ref, snapshot_hash: 'snapshot-hash', run_id: 'run-a', schema_version: '1.5.0', evaluated_at: '2026-10-12T00:00:00Z', profile: 'record-write-v1', policy_hash: 'policy', policy_version: 'policy-v1', scoring_rule_version: 'three-dimensional-v1', assessment_rule_version: 'evidence-assessment-v1', scores: { evaluation_state: 'PARTIAL', overall_score_bp: null, sufficiency_bp: 0, advice: 'INSUFFICIENT_EVIDENCE', critical_conflict: true, limitations: ['test evidence gap'], dimensions: { availability: dim, consistency: dim, behavior: dim } }, limitations: ['explicit browser test fixture'], task_counts: { PASS: 0, FAIL: 1, UNKNOWN: 1, NOT_APPLICABLE: 0 }, task_results: [{ slot_id: 'slot-a', capability_id: 'anchor_record', outcome: 'FAIL', reason_code: 'SEMANTIC_MISMATCH', rule_version: '6', input_evidence_id: 'input-a' }], assertions: [{ slot_id: 'slot-a', assertion_id: 'assertion-a', rule_id: 'task-match', outcome: 'FAIL', reason_code: 'SEMANTIC_MISMATCH', expected: 'request-a', observed: 'request-old', critical: true, evidence_refs: ['input-a'] }], risk_assessment: { conclusion: 'CONFIRMED_CRITICAL_CONFLICT', critical_findings: [{ slot_id: 'slot-a', assertion_id: 'assertion-a', rule_id: 'task-match', reason_code: 'SEMANTIC_MISMATCH', evidence_refs: ['input-a'] }], evidence_gap_slots: [], ordinary_failure_slots: [] } }, manifest: { publication: { chain: { chain_id: '31337' } } } };
report.core.raw_statistics = { availability: { planned: 2, decided: 1, responded: 1 }, capabilities: [{ capability_id: 'anchor_record', planned: 2, decided: 1, passed: 0 }], uncovered_claim_count: 2 };
report.core.evidence_sufficiency = { gate_status: 'PARTIAL', dimensions: { consistency: { claim_count: 3, tested_claim_count: 1, planned: 2, decided: 1 } }, capabilities: [{ capability_id: 'anchor_record', covered_classes: ['normal'], required_classes: ['normal', 'unsupported_chain'] }], missing_evidence: ['test gap'], uncovered_claims: ['verify_record', 'get_tx_status'] };
const olderReport = JSON.parse(JSON.stringify(report));
olderReport.report_id = 'report-old'; olderReport.core.policy_hash = 'different-policy'; olderReport.core.evaluated_at = '2026-10-11T00:00:00Z';

async function run() {
  let server;
  let browser;
  try {
    if (!process.env.WEB_SMOKE_ORIGIN) {
      server = spawn(process.execPath, [path.resolve(__dirname, '../node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '4173', '--strictPort'], { cwd: path.resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'] });
      let serverOutput = '';
      const stripAnsi = value => value.replace(/\u001b\[[0-?]*[ -\/]*[@-~]/g, '');
      const capture = chunk => { serverOutput = stripAnsi(serverOutput + chunk.toString()).slice(-8000); };
      server.stdout.on('data', capture); server.stderr.on('data', capture);
      for (let attempt = 0; !serverOutput.includes(baseUrl) && attempt < 100; attempt += 1) {
        if (server.exitCode !== null) throw new Error(`Vite failed to start: ${serverOutput}`);
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      if (!serverOutput.includes(baseUrl)) throw new Error(`Vite did not become ready: ${serverOutput}`);
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE });
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let runReads = 0;
    let reportRequested = false;
    let reportJobFailed = false;
    const starts = [];
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const resource = url.pathname;
      let body;
      let status = 200;
      if (resource === '/api/v1/agents') body = { items: [agentA, agentB], next_cursor: null };
      else if (resource === '/api/v1/agents/agent-a') body = agentA;
      else if (resource === '/api/v1/agents/agent-b') body = agentB;
      else if (resource.endsWith('/snapshots')) body = { items: resource.includes('agent-a') ? [snapshot] : [], next_cursor: null };
      else if (resource.endsWith('/reports')) body = { items: resource.includes('agent-a') ? [report, olderReport] : [], next_cursor: null };
      else if (resource === '/api/v1/snapshots/snapshot-a') body = snapshot;
      else if (resource.endsWith('/bindings')) body = [{ binding_id: 'binding', status: 'VERIFIED', message: { executor: 'executor-a', deadline: 1 }, reason_code: null }];
      else if (resource === '/api/v1/evaluations' && request.method() === 'POST') {
        starts.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'], auth: request.headers().authorization });
        body = { run_id: 'run-a', status: 'QUEUED', status_url: '/api/v1/evaluations/run-a' };
      } else if (resource === '/api/v1/evaluations/run-a') {
        runReads += 1;
        body = { run_id: 'run-a', status: runReads === 1 ? 'RUNNING' : 'PARTIAL', stage: runReads === 1 ? 'EXECUTING' : 'DONE', planned: 2, settled: runReads === 1 ? 0 : 2, unknown: 1, latest_report_id: null, cancel_requested: false };
      } else if (resource.endsWith('/observations')) body = [];
      else if (resource.endsWith('/plan')) body = { confirmed_capabilities: ['anchor_record'], suite_id: 'm1-smoke-v1' };
      else if (resource.endsWith('/verification')) { status = 404; body = { error: { message: 'Pending' } }; }
      else if (resource.endsWith('/report') && request.method() === 'POST') { reportRequested = true; body = { job_id: 'job-report', status_url: '/api/v1/jobs/job-report', status: 'QUEUED' }; }
      else if (resource.endsWith('/report')) { status = 404; body = { error: { message: 'Pending report' } }; }
      else if (resource === '/api/v1/jobs/job-report') { reportJobFailed = true; body = { id: 'job-report', state: 'FAILED', reason_code: 'FREEZE_BLOCKED', snapshot_id: null }; }
      else if (resource.endsWith('/anchor')) body = { status: 'NOT_REQUESTED', tx_hash: null };
    else if (resource.includes('/evidence/')) body = { record: { evidence_id: 'input-a', blob_hash: 'input-hash' }, body: { schema_version: 'record-verification-input-v1', slot: { task: { request_id: 'request-a' } }, agent_task_status: 'succeeded', agent_response: { status: 'succeeded' }, agent_result: { tx_hash: 'tx-success' }, evm: { results: { receipt: { status: '0x1' }, transaction: { input: '0x' + 'cd'.repeat(8192) } } }, snapshot: { secret_fixture_note: 'must-not-render' } } };
      else { status = 404; body = { error: { message: 'Unknown test endpoint' } }; }
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.route('**/health/live', route => route.fulfill({ contentType: 'application/json', body: '{"status":"ok"}' }));
    await page.goto(baseUrl);
    await page.getByRole('button', { name: 'Agent #1' }).click();
    await page.getByText('owner-of-agent-a', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Agent #2' }).click();
    await page.getByText('UNVERIFIED', { exact: true }).waitFor();
    assert.equal(await page.getByText('owner-of-agent-a', { exact: true }).count(), 0, 'switching Agent must clear its owner/snapshot');
    console.log('PASS: Agent selection clears stale snapshot and owner');

    await page.getByRole('button', { name: '任务评价', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: '启动评价', exact: true }).isDisabled(), true);
    await page.getByLabel('本地 Operator token（仅当前页面内存）').fill('browser-test-token');
    await page.getByLabel('快照 UUID', { exact: true }).fill('snapshot-a');
    await page.getByLabel('已有授权 grant UUID（逗号分隔）').fill('existing-grant');
    await page.getByLabel('公共第三方免费只读（HTTP 与 MCP 两个授权）').uncheck();
    await page.getByLabel('Idempotency key').fill('one-browser-operation');
    await page.getByRole('button', { name: '启动评价', exact: true }).click();
    await page.getByText('PARTIAL', { exact: true }).waitFor({ timeout: 10000 });
    assert.equal(starts.length, 1);
    assert.equal(starts[0].body.suite_id, 'm1-smoke-v1');
    assert.deepEqual(starts[0].body.grant_ids, ['existing-grant']);
    assert.equal(starts[0].key, 'one-browser-operation');
    assert.equal(starts[0].auth, 'Bearer browser-test-token');
    const terminalReadCount = runReads;
    await page.waitForTimeout(2300);
    assert.equal(runReads, terminalReadCount, 'polling must stop after terminal PARTIAL');
    await page.getByRole('button', { name: '生成冻结报告', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'FREEZE_BLOCKED' }).waitFor();
    assert.ok(reportRequested && reportJobFailed);
    console.log('PASS: authorized start uses grant/key, polling stops terminal, failed report job is visible');

    await page.getByLabel('本地评价套件').selectOption('capabilities-v1');
    await page.getByLabel('评价能力', { exact: true }).selectOption('get_tx_status');
    await page.getByLabel('Query tx_hash').fill('0x' + '1'.repeat(64));
    await page.getByLabel('Idempotency key').fill('query-operation');
    await page.getByRole('button', { name: '启动评价', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '评价已排队' }).waitFor();
    assert.equal(starts[1].body.capability_id, 'get_tx_status');
    assert.equal(starts[1].body.profile, 'record-read-v1');
    assert.equal(starts[1].body.query_tx_hash, '0x' + '1'.repeat(64));
    await page.getByLabel('评价能力', { exact: true }).selectOption('verify_record');
    await page.getByLabel('Record executor').fill('0x' + '2'.repeat(40));
    await page.getByLabel('Record request_id').fill('0x' + '3'.repeat(64));
    await page.getByLabel('Record hash').fill('0x' + '4'.repeat(64));
    await page.getByLabel('Idempotency key').fill('record-operation');
    await page.getByRole('button', { name: '启动评价', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '评价已排队' }).waitFor();
    assert.equal(starts[2].body.capability_id, 'verify_record');
    assert.equal(starts[2].body.query_tx_hash, null);
    assert.equal(starts[2].body.record_executor, '0x' + '2'.repeat(40));
    console.log('PASS: both local read capabilities send their matching existing DTO inputs');

    await page.getByRole('button', { name: 'Agent 与身份', exact: true }).click();
    await page.getByRole('button', { name: 'Agent #1' }).click();
    await page.getByText('owner-of-agent-a', { exact: true }).waitFor();
    await page.getByRole('button', { name: '历史对比', exact: true }).click();
    await page.getByRole('button', { name: '查看', exact: true }).first().click();
    await page.getByText('综合分：未形成正式评分', { exact: true }).waitFor();
    await page.getByText('UNANCHORED / NOT_REQUESTED', { exact: true }).waitFor();
    await page.getByText('实际样本数与能力覆盖（后端统计）', { exact: true }).click();
    assert.ok((await page.locator('body').innerText()).includes('"planned": 2'));
    assert.ok((await page.locator('body').innerText()).includes('"tested_claim_count": 1'));
    await page.getByText('anchor_record · FAIL · SEMANTIC_MISMATCH', { exact: true }).click();
    await page.getByRole('button', { name: '读取冻结任务输入、响应与链上证据' }).click();
    await page.getByRole('heading', { name: '冻结任务输入与原始证据' }).waitFor();
    const width = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: window.innerWidth }));
    assert.ok(width.page <= width.viewport, 'long frozen transaction hex must scroll inside its evidence panel');
    assert.equal(await page.getByText('must-not-render').count(), 0, 'evidence view must exclude unrelated identity metadata');
    assert.ok((await page.locator('body').innerText()).includes('tx-success'));
    assert.ok((await page.locator('body').innerText()).includes('服务可用性'));
    console.log('PASS: PARTIAL/null score, anchor state, task input/response/chain evidence are rendered truthfully');

    await page.locator('input[type="file"]').setInputFiles({
      name: 'verifier.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({
        status: 'PASS', offline: 'PASS', report_hash: reportHash,
        task_results: [{ slot_id: 'slot-a', capability_id: 'anchor_record', outcome: 'FAIL', reason_code: 'SEMANTIC_MISMATCH', live_chain: { status: 'CONFLICT', outcome: 'PASS', historical_outcome: 'FAIL', historical_reason_code: 'SEMANTIC_MISMATCH' } }],
        task_counts: { PASS: 0, FAIL: 1, UNKNOWN: 0, NOT_APPLICABLE: 0 }, task_count_comparison: 'MATCH', assessment_comparison: 'MATCH',
        anchor: { status: 'NOT_CHECKED', reason: 'trusted RPC was not configured' },
      })),
    });
    await page.getByText('MATCH：与当前平台报告摘要一致', { exact: true }).waitFor();
    await page.getByText('· 当前 PASS', { exact: true }).waitFor();
    assert.ok((await page.locator('body').innerText()).includes('历史 FAIL / SEMANTIC_MISMATCH'));
    if (process.env.WEB_SMOKE_SCREENSHOT) await page.screenshot({ path: path.resolve(process.env.WEB_SMOKE_SCREENSHOT), fullPage: true });
    await page.locator('input[type="file"]').setInputFiles({ name: 'failure.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ status: 'FAIL', code: 'REPLAY_MISMATCH', message: 'frozen evidence differs <img src=x>', private_note: 'never-display-imported-metadata' })) });
    await page.getByText('未提供 report_hash，无法确认对应当前报告', { exact: true }).waitFor();
    await page.getByText('Verifier 失败原因：frozen evidence differs <img src=x>', { exact: true }).waitFor();
    assert.equal(await page.locator('img').count(), 0, 'imported message must remain text');
    assert.equal(await page.getByText('never-display-imported-metadata').count(), 0);
    await page.locator('input[type="file"]').setInputFiles({ name: 'mismatch.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ status: 'PASS', offline: 'PASS', report_hash: '0x' + 'b'.repeat(64) })) });
    await page.getByText('MISMATCH：与当前平台报告摘要不一致，不能归因到当前报告', { exact: true }).waitFor();
    console.log('PASS: local Verifier import separates live result, labels hash mismatch/no-hash, and safely displays CLI failure');

    await page.getByRole('button', { name: '历史对比', exact: true }).click();
    await page.getByLabel('与当前报告比较').selectOption('report-old');
    await page.getByText('规则、报告版本或评价范围不同，分数不可直接比较。', { exact: true }).waitFor();
    assert.ok(!(await page.locator('body').innerText()).includes('→'), 'incompatible reports must not display numeric score deltas');
    console.log('PASS: history refuses numeric comparison across different policies');
    await page.getByRole('button', { name: '查看', exact: true }).last().click();
    assert.equal(await page.getByText('CLI 顶层状态', { exact: true }).count(), 0, 'changing report must clear the imported CLI result');
    assert.equal(await page.getByRole('heading', { name: '冻结任务输入与原始证据' }).count(), 0, 'changing report must clear the previous task evidence');

    await page.getByRole('button', { name: '任务评价', exact: true }).click();
    await page.getByLabel('Run UUID').fill('run-a');
    await page.getByRole('button', { name: '加载 / 刷新', exact: true }).click();
    await page.getByText('PARTIAL', { exact: true }).waitFor();
    let releaseReportStart;
    const delayedReportStart = new Promise(resolve => { releaseReportStart = resolve; });
    await page.route('**/api/v1/evaluations/run-a/report', async route => {
      if (route.request().method() !== 'POST') return route.fallback();
      await delayedReportStart;
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ job_id: 'job-report', status_url: '/api/v1/jobs/job-report', status: 'QUEUED' }) });
    });
    const pendingReportStart = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/evaluations/run-a/report' && request.method() === 'POST');
    await page.getByRole('button', { name: '生成冻结报告', exact: true }).click();
    await pendingReportStart;
    await page.getByRole('button', { name: '历史对比', exact: true }).click();
    await page.getByRole('button', { name: '查看', exact: true }).first().click();
    await page.getByText(reportHash, { exact: true }).waitFor();
    const staleReportAccepted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/evaluations/run-a/report' && response.request().method() === 'POST');
    releaseReportStart();
    await staleReportAccepted;
    await page.getByRole('status').filter({ hasText: '正在请求平台…' }).waitFor({ state: 'hidden' });
    assert.equal(await page.getByRole('alert').count(), 0, 'a report request completed after a history switch must not dereference the cleared evaluation');
    assert.equal(await page.getByText('报告生成任务已排队。', { exact: true }).count(), 0, 'the stale report request must not claim it queued a report in the newly selected context');
    assert.equal(await page.getByText(reportHash, { exact: true }).count(), 1, 'the selected historical report must survive the old report request completion');
    console.log('PASS: delayed report POST completion preserves the selected historical report');

    await page.route('**/api/v1/evaluations/run-c', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ run_id: 'run-c', status: 'RUNNING', stage: 'EXECUTING', planned: 2, settled: 0, unknown: 0, latest_report_id: null, cancel_requested: false }) }));
    let releaseCancellation;
    const delayedCancellation = new Promise(resolve => { releaseCancellation = resolve; });
    await page.route('**/api/v1/evaluations/run-c/cancel', async route => {
      await delayedCancellation;
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ run_id: 'run-c', status: 'RUNNING', stage: 'EXECUTING', planned: 2, settled: 0, unknown: 0, latest_report_id: null, cancel_requested: true }) });
    });
    await page.getByRole('button', { name: '任务评价', exact: true }).click();
    await page.getByLabel('Run UUID').fill('run-c');
    await page.getByRole('button', { name: '加载 / 刷新', exact: true }).click();
    await page.getByText('RUNNING', { exact: true }).waitFor();
    const pendingCancellation = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/evaluations/run-c/cancel');
    await page.getByRole('button', { name: '取消评价', exact: true }).click();
    await pendingCancellation;
    await page.getByRole('button', { name: '历史对比', exact: true }).click();
    await page.getByRole('button', { name: '查看', exact: true }).first().click();
    await page.getByText(reportHash, { exact: true }).waitFor();
    const staleCancellationAccepted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/evaluations/run-c/cancel');
    releaseCancellation();
    await staleCancellationAccepted;
    await page.getByRole('status').filter({ hasText: '正在请求平台…' }).waitFor({ state: 'hidden' });
    assert.equal(await page.getByRole('alert').count(), 0, 'a cancellation completed after a history switch must not dereference the cleared evaluation');
    assert.equal(await page.getByText('取消请求已提交；已发生的任务和证据保留。', { exact: true }).count(), 0, 'the stale cancellation must not display its message in the historical report context');
    assert.equal(await page.getByText(reportHash, { exact: true }).count(), 1, 'the selected historical report must survive the old cancellation completion');
    console.log('PASS: delayed cancellation completion preserves the selected historical report');

    for (const staleOutcome of ['success', 'failure']) {
      const staleRunId = `run-history-${staleOutcome}`;
      let releaseRunLoad;
      const delayedRunLoad = new Promise(resolve => { releaseRunLoad = resolve; });
      await page.route(`**/api/v1/evaluations/${staleRunId}`, async route => {
        await delayedRunLoad;
        const body = staleOutcome === 'success'
          ? { run_id: staleRunId, status: 'CANCELLED', stage: 'DONE', planned: 2, settled: 2, unknown: 0, latest_report_id: null, cancel_requested: true }
          : { error: { message: 'stale initial run load failed' } };
        await route.fulfill({ status: staleOutcome === 'success' ? 200 : 500, contentType: 'application/json', body: JSON.stringify(body) });
      });
      await page.getByRole('button', { name: '任务评价', exact: true }).click();
      await page.getByLabel('Run UUID').fill(staleRunId);
      const pendingRunLoad = page.waitForRequest(request => new URL(request.url()).pathname === `/api/v1/evaluations/${staleRunId}`);
      await page.getByRole('button', { name: '加载 / 刷新', exact: true }).click();
      await pendingRunLoad;
      await page.getByRole('button', { name: '历史对比', exact: true }).click();
      await page.getByRole('button', { name: '查看', exact: true }).first().click();
      await page.getByText(reportHash, { exact: true }).waitFor();
      const staleRunLoaded = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/evaluations/${staleRunId}`);
      releaseRunLoad();
      await staleRunLoaded;
      await page.getByRole('status').filter({ hasText: '正在请求平台…' }).waitFor({ state: 'hidden' });
      assert.equal(await page.getByRole('alert').count(), 0, `an initial run ${staleOutcome} after a history switch must not display a stale error`);
      await page.getByRole('heading', { name: '冻结报告与任务证据', exact: true }).waitFor();
      assert.equal(await page.getByText(reportHash, { exact: true }).count(), 1, `an initial run ${staleOutcome} must preserve the selected historical report and evidence tab`);
    }
    console.log('PASS: delayed initial run success/failure preserves the selected historical report and tab');
    await page.getByRole('button', { name: 'Agent 与身份', exact: true }).click();
    await page.getByRole('button', { name: 'Agent #2' }).click();
    await page.getByText('UNVERIFIED', { exact: true }).waitFor();
    await page.getByRole('button', { name: '声誉与证据', exact: true }).click();
    await page.getByText('尚未选择冻结报告。', { exact: true }).waitFor();
    console.log('PASS: report and Agent switches clear old report, task evidence and imported verifier attribution');

    await page.route('**/api/v1/jobs/job-report', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'job-report', state: 'RUNNING', reason_code: null }) }));
    await page.getByRole('button', { name: '任务评价', exact: true }).click();
    await page.getByLabel('Run UUID').fill('run-a');
    await page.getByRole('button', { name: '加载 / 刷新', exact: true }).click();
    await page.getByText('PARTIAL', { exact: true }).waitFor();
    await page.getByRole('button', { name: '生成冻结报告', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '报告生成任务已排队。' }).waitFor();
    let releaseOldReportPoll;
    const oldReportPoll = new Promise(resolve => { releaseOldReportPoll = resolve; });
    await page.route('**/api/v1/evaluations/run-a', async route => {
      await oldReportPoll;
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: { message: 'stale Run A report poll failed' } }) });
    });
    let runBReads = 0;
    await page.route('**/api/v1/evaluations/run-b', route => {
      runBReads += 1;
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ run_id: 'run-b', status: runBReads === 1 ? 'RUNNING' : 'PARTIAL', stage: runBReads === 1 ? 'EXECUTING' : 'DONE', planned: 2, settled: runBReads === 1 ? 0 : 2, unknown: 1, latest_report_id: null, cancel_requested: false }) });
    });
    await page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/evaluations/run-a');
    await page.getByLabel('Run UUID').fill('run-b');
    await page.getByRole('button', { name: '加载 / 刷新', exact: true }).click();
    await page.getByText('RUNNING', { exact: true }).waitFor();
    await page.getByRole('status').filter({ hasText: '正在请求平台…' }).waitFor({ state: 'hidden' });
    const oldReportFailure = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/evaluations/run-a' && response.status() === 500);
    releaseOldReportPoll();
    await oldReportFailure;
    await page.getByText('PARTIAL', { exact: true }).waitFor({ timeout: 10000 });
    assert.ok(runBReads >= 2, 'a stale report-poll failure must not stop the newly selected run polling');
    assert.equal(await page.getByRole('alert').filter({ hasText: 'stale Run A report poll failed' }).count(), 0, 'an old report poll must not display its failure for the new run');
    console.log('PASS: delayed old report-poll failure leaves the new run polling and notices intact');
    assert.deepEqual(errors, [], 'browser runtime must have no uncaught errors');
  } finally {
    await browser?.close();
    if (server && server.exitCode === null) {
      const closed = new Promise(resolve => server.once('exit', resolve));
      server.kill(); await closed;
    }
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
