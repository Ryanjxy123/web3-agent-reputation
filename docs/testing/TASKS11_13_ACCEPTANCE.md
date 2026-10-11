# Tasks 11–13 acceptance record

Recorded on 2026-10-12. This file records actual stage evidence and remaining final checks; it does not assert final full acceptance, current required CI success, merge, or Release publication. Progress and final Git identity are maintained in [STATUS.md](../implementation/STATUS.md).

## Task 11 accepted experiment

Task 11 was accepted and committed as `ba1b148`. Its formal population is 12 controlled scenarios × 3 repetitions = 36 real PostgreSQL/HTTP Agent/Anvil/Worker tasks. The accepted [v2 report](experiments/task11/formal-20261012-three-repeats-v2/analysis/report.md), [reproduction instructions and raw artifacts](experiments/task11/README.md), and [independent Review](experiments/task11/REVIEW.md) record exact source/plan/Bundle hashes, applicability and denominators. Proposed retains 6 PASS / 15 FAIL / 12 UNKNOWN / 3 N/A. Common-write known-error Recall is online 0 / receipt 0 / proposed 1; independent Bundle outcome/reason consistency is 36/36 and risk consistency is 33/33, excluding 3 legacy N/A reports without independent risk assessment.

The capture recorded the original base commit with authorized uncommitted sources; its exact 82-file source snapshot identifies the executed bytes. Subsequent product/read-API changes are separate from those frozen experiment results. A clean checkout can replay the retained outputs offline; the reviewer also replayed them from an unrelated directory with DB/RPC/operator environment variables unset, obtaining identical JSON/CSV/report/SVG bytes. A fresh clone plus installation was not performed by that reviewer. Controlled cases do not establish production accuracy or significance.

## Task 12 product acceptance

Task 12 was accepted and committed as `6e774d2`. Frontend 21 unit tests, build/vue-tsc and 7 browser groups passed. The actual [local UI evidence](evidence/local-ui-2026-10-12/README.md) includes both downloaded Bundles, independent CLI results and reviewed screenshots. Final whole-project gates remain below.

Task 12 uses the real API for Agent/snapshot/history pages, authorized task creation/progress, three dimensions and evidence sufficiency, risk/task assertions, report/Bundle export, anchor status and local Verifier-output import. It retains PARTIAL, UNKNOWN, N/A, `overall=null` and historical/current identity distinctions. Browser test fixtures are labeled test inputs; they are not experimental results or real API acceptance evidence.

The delivery reviewer found no blocking issue in the pending report-anchor projection correction: one atomic outer join reads only job state/public transaction hash and any stored confirmed receipt; confirmed receipt wins, absent jobs stay NOT_REQUESTED, and GET/export share the same projection. Signed transaction bytes are never selected for publication and the frozen report-core hash is unchanged. The real PostgreSQL/Anvil/Worker/API/Verifier test in `runtime/task12-pending-anchor-review.log` passed **1 test / 0 skipped in 19.43 seconds**, covering QUEUED/SIGNED/BROADCAST/FAILED states, export compatibility and signed-byte non-leakage. The two existing dependency deprecation warnings were retained. Related tests cover another report's evidence rejected with 404 and changed/missing committed bytes rejected with 409.

The frontend implementer reports final 21 unit tests, build and 7 browser groups passed; root's `runtime/task12-real-browser-layout-and-verifier-final.log` records real A and D authorized dashboard execution → Worker → task/evidence → Bundle, preserving PARTIAL/null and UNANCHORED. Final stage acceptance, combined directed counts and commit are **PENDING** here until the root reviewer records completion. These stage checks do not replace final full regression or required CI.

## Task 13 deployment and repeat demo

Deployment changes preserve the existing architecture: API/worker share an evidence volume; the worker requires actual `CODE_VERSION`; each service receives only its own read-only configuration; A/D durable ledgers use separate writable volumes. `prepare_compose_runtime.py` validates real host Anvil/deployment/seed/publisher identity, writes only four container configurations, rejects existing output and preserves original host bytes and ledgers. `package_delivery.py` exports one committed Git tree and hashes its bytes, rejects prohibited secret/runtime paths and preserves existing output.

Stage-directed tests used:

```powershell
. ./scripts/tools.ps1
uv run --all-packages pytest tests/unit/test_package_delivery.py tests/integration/test_compose_runtime.py -q
```

The directed stage run completed **14 passed / 0 skipped in 12.72 seconds**, including real Anvil deployment/seed checks, configuration rejection, ledger persistence and committed-source packaging. Ruff, script Mypy, fixture-agent Mypy and `git diff --check` passed. `docker compose config --quiet` passed with a concrete source version; removing `CODE_VERSION` correctly rejected the configuration. These checks do not assert full container startup.

The root reviewer ran the native demo against an isolated PostgreSQL database, Anvil at loopback port 18545, API/worker, A/D HTTP services at ports 23301/23302 and the web at 5173. Runtime `task13-localdemo-20261012-001` and the original failure logs were retained. The successful runtime and complete repeat logs record:

| Retained local log | Observed result |
|---|---|
| `runtime/task13-localdemo-runtime.log` | LIVE_RUNTIME_PASS: API, web proxy, auth and local Anvil |
| `runtime/task13-localdemo-repeat-verification.log` | Identity/dual binding and real HTTP dispatch pass; A PASS, D successful receipt rejected as TASK_ID_MISMATCH |
| `runtime/task13-localdemo-repeat-reports.log` | Immutable A/D PARTIAL Bundles exported; overall=null; anchor initially NOT_REQUESTED |
| `runtime/task13-localdemo-repeat-m1.log` | A/D reports both anchored; offline and trusted-RPC verifier pass; tamper rejected |

The reviewer read those logs and independently replayed the latest saved A/D Bundles. A is business PASS; D is business FAIL with critical conflict; both report receipt CONFIRMED and `overall=null`. Offline anchor remains NOT_CHECKED. Anchoring D commits its FAIL report and never upgrades its business result. Anchoring both predecessor reports fixes repeat-demo blockage from an earlier unanchored D report. `smoke_reports.py` intentionally expects a newly unanchored report, so a repeat starts with a fresh verification run before the reports/M1 steps.

The local Docker Linux engine remains unavailable due to the recorded WSL import failure. Full Linux Compose build/start/A/D/report/anchor smoke is **NOT_RUN locally** and requires the updated `foundation-compose` CI job. Historical CI success on older Compose does not prove this new flow. No WSL reset, volume deletion or evidence rewriting was used to manufacture success.

## Delivery scope and known limits

Commands in [README](../../README.md), [local runtime](../runbooks/LOCAL_RUNTIME.md), [demo](../runbooks/DEMO_AND_RELEASE.md) and the [acceptance command table](../implementation/ACCEPTANCE.md) were checked against current CLI parsers, smoke scripts, Compose mounts and CI steps. They use actual `deploy-local`/`seed`, `uvicorn ... --factory`, independent `reputation worker`, and `reputation-verify BUNDLE [--rpc-url TRUSTED_RPC]` entry points. Full checks require Chromium installation; readiness/tool checks do not substitute for business verification or a frozen Bundle.

The [dependency license metadata inventory](../references/DEPENDENCY_LICENSE_METADATA.json) inspected 77 installed Python packages matching `uv.lock`, 168 Web dependency entries (117 package metadata read, 51 platform-optional packages not installed on Windows), and 2 tracked source notices. All three recorded lock hashes match the reviewed files. This is metadata inspection, not a complete binary/redistribution/compatibility audit. Upstream notices remain preserved; the repository has no declared first-party root LICENSE and no license was invented.

Official contest name, rules, deadline, material template and anonymity requirements remain UNVERIFIED because no official original was available. These do not block the user-authorized software Release after technical acceptance and required CI; Release notes must disclose them. Official contest submission must separately check the actual rules. The source delivery archive and Git history are not claimed anonymous.

The real third-party historical result remains 4 PASS / 1 UNKNOWN, PARTIAL, `overall=null`, executor UNKNOWN and UNANCHORED. Its saved evidence can be replayed without new public calls, but external availability and current mainnet state are not established by that replay. No paid APIs, real funds, production keys or mainnet writes are needed for the native A/D demo. Offline verification proves evidence-package consistency; live chain truth depends on the operator's trusted RPC and chain/finality assumptions.

## Final project gate

| Check | Current record |
|---|---|
| Full Python suite with 0 skipped, Ruff/Mypy/Schema/TS drift | PENDING final root-run evidence |
| Final Web type/build/unit/browser checks and real API interaction | PENDING final root-run evidence |
| Foundry/fuzz/ABI, PostgreSQL/Anvil/Worker/Verifier integration and historical Bundles | PENDING final root-run evidence |
| Updated required `foundation-quality` and `foundation-compose` on final PR head | PENDING CI |
| Clean merged main = origin/main, source-content secret review, exact delivery manifest and Release | PENDING final Git/Release evidence |

Final completion requires filling these entries with real commands, counts, exit codes, SHA and CI links after passing checks. [COMPETITION_DELIVERY.md](../runbooks/COMPETITION_DELIVERY.md) defines the software Release and separate official-submission gates.
