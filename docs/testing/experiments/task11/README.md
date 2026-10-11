# Task 11 real comparison experiment

The plan in `fixtures/experiments/task11_cases.json` contains scenario configuration and independent intended Ground Truth only. No measured outcomes, verifier verdicts, timings, or request counts are checked in as synthetic experimental results.

Run after the other PostgreSQL/Anvil tests finish, using the same environment setup as the existing integration suite:

```powershell
. ./scripts/tools.ps1
uv run --env-file .env --all-packages python scripts/task11_comparison.py capture --output runtime/task11-run --repetitions 3
uv run --env-file .env --all-packages python scripts/task11_comparison.py analyse --output runtime/task11-run
uv run --env-file .env --all-packages pytest tests/unit/test_task11_comparison.py -q
```

Capture reuses `prepared`, `flow`, `controlled_run`, and `advance` from the existing real integration tests. Each scenario executes API planning → real controlled HTTP Agent → Worker execution → independent local-chain verification → report freeze → exported Bundle. The version, binding, and refused-RPC faults are actual local controlled changes. The experiment-only `task11_hash_agent` reuses the existing durable Agent and signs a real transaction with a different nonzero record digest while claiming the requested one. The undeclared-capability case captures a real narrower registry declaration, confirms an excluded capability and follows the existing no-dispatch N/A path. Every repetition creates a new task request; repeated attempts are retained rather than counted as independent tasks.

`captures/<case>-<repetition>` retains the frozen verification input, Bundle ZIP, computed independent verifier output, and a trace containing Worker timings, actual `SafeHttpClient.request` attempts, platform `HTTPProvider.make_request` calls by stage/method, and separately persisted attempts/observations. Captures are written before asserting Ground Truth, so a failed run leaves its evidence available. Capture requires a new or empty output directory and never overwrites prior evidence. The frozen plan hash, source manifest, Git commit/dirty flag, OS/CPU/architecture, Python/Anvil/PostgreSQL versions and dependency lock hash are retained; changes to hashed sources during capture invalidate completion.

Offline analysis validates completion, the exact case×repeat set and plan/source/input/Bundle hashes, re-executes `verify_record` with the actual input evidence UUID, and runs `verify_bundle`. It writes raw JSON, summary JSON, per-task CSV, a report and SVG under `analysis`. No result is taken from the scenario label. Binary metrics exclude unknown Ground Truth; UNKNOWN predictions are abstentions, and a false negative requires predicted PASS. Main Recall includes all known errors, including abstentions; F1 is its harmonic mean with Precision. Conditional Recall and missed-known-error counts remain separate. Precision is zero when known samples exist but there are no predicted failures; empty/undefined denominators remain null. Receipt evaluation is N/A for read tasks. Both each method's applicable set and the common write-task intersection are reported with explicit denominators. Undeclared N/A uses rule 2/report 1.1: task outcome/reason are replayed, while absent legacy risk assessments are explicitly excluded from risk-consistency counts.

Resource figures are actual shared-pipeline observations, with repeat count, per-case min/max and standard deviation. They are not separate baseline benchmarks. RPC instrumentation covers the platform process; the controlled Agent subprocess's RPC traffic is outside that count. The intermittent fixture selects one deterministic service-error slot with `failure_every=1`; this does not estimate an intermittent failure probability. The matrix has no distinct wrong-business-read fixture: read coverage demonstrates normal read PASS and receipt N/A, while write mismatch cases cover business inconsistency. Read-task detection should not be generalised until that fixture is added. Local controlled cases do not establish production prevalence or statistical significance. Actual experiment acceptance requires a successful capture run and review of its retained results.

The accepted formal result is frozen in `formal-20261012-three-repeats-v2/`. It retains all 36 `captures/<case>-<repeat>/{input.json,bundle.zip,verifier.json,trace.json}`, `plan.json`, `execution.json`, and generated `analysis/` JSON/CSV/report/SVG, so a fresh clone can replay the original bytes:

```powershell
. ./scripts/tools.ps1
uv run --all-packages python -c "import shutil; shutil.copytree('docs/testing/experiments/task11/formal-20261012-three-repeats-v2', 'runtime/task11-replay')"
uv run --all-packages python scripts/task11_comparison.py analyse --output runtime/task11-replay
```

The replay directory must be new. Analyse the copy so the published freeze remains unchanged. Generated text line endings follow the host OS; compare JSON values/CSV rows when replaying across operating systems, while `publication-manifest.json` continues to commit the original captured bytes.

The actual capture command was:

```powershell
. ./scripts/tools.ps1
$env:FIXTURE_PORT_A='23101'
$env:FIXTURE_PORT_D='23102'
uv run --env-file .env --all-packages python scripts/task11_comparison.py capture --output runtime/task11/formal-20261012-three-repeats-v2 --repetitions 3
```

Capture recorded 36 passed tasks in 461.04 seconds, exit code 0, and no source change during capture. It recorded commit `76b411af797e480b0b8c117a5d06b78ebcfccd24` with `git_dirty=true`: the exact authorized experiment, API prerequisite and ledger changes were uncommitted at capture time. At Task 11 acceptance, the 82-file source manifest matched the capture workspace byte-for-byte, and `source-snapshot.zip` preserves precisely those listed files. The later Task 12 read-only receipt projection correction changes `services/platform/src/reputation_platform/application/reports.py` to expose safe pending/failed outbox states; it leaves unrequested capture Bundles, task verification, frozen scoring and all retained results unchanged. Final checkout source hashes therefore must not be substituted for the original capture manifest; the exact captured source snapshot remains authoritative. Its SHA-256 is `378d373ecd0a2089af862eae72bfeefcb03f4636b3e038048984cb8cd9a0dd3d`; the canonical source-manifest SHA-256 is `6510212a16ec181677ad6031d2be6f4e170fdf9cc65083da551196c25984c650`. Source line-ending normalization on another checkout can change file hashes without changing behavior; use the exact snapshot bytes when comparing captured source hashes. Captured artifacts use Git `-text` to preserve their byte hashes.

Main known-error Recall is online 0.200, receipt 0.000 and proposed 1.000 on each method's predeclared applicable scope; on common write tasks it is 0.000/0.000/1.000. Proposed outcomes are 6 PASS, 15 FAIL, 12 UNKNOWN and 3 N/A; the 12 UNKNOWN cases remain evidence gaps, and no single-slot report is promoted to a sufficient overall reputation score. Independent Bundle outcome/reason consistency is 36/36, risk consistency 33/33, with 3 legacy N/A reports explicitly lacking risk assessments. These are controlled-case results; they do not establish production accuracy.

`publication-manifest.json` records hashes for every retained artifact and the credential scan scope. The frozen summary SHA-256 is `a865dd79a31ec4f25b101b027fc95cd27232e6621284ad7e1bd4b720a861881b`, raw rows `2f1d5417b9880d282fccc0b52255ed0ff5ba1fc177684aeae6fe8bfc9ead8da5`, and report `45e69275e69bc4bff3b417c5b2bd5255b40c82cc9589cf9bdf22d66df9f549ae`. Evidence and Bundle members contain controlled test addresses, public binding signatures, synthetic tasks and observations; no runtime private keys or API/database credentials are published.

The earlier 30-task pre-review run and the first 36-task formal run remain under local `runtime/task11/` as superseded review evidence. The first formal run passed its tasks and replay, but a subsequent report-limit text edit changed the script source hash, so the accepted v2 run was recaptured with stable final sources. Earlier data were retained rather than rewritten.
