# Task 11 independent review

Reviewed on 2026-10-12 by the delivery reviewer, independently of the experiment implementation. The reviewed formal result is [formal-20261012-three-repeats-v2](formal-20261012-three-repeats-v2/); method and reproduction instructions are in [README.md](README.md). **No blocking findings remain for Task 11 acceptance.** This recommendation covers the retained experiment and its declared scope, not final project regression, CI, or Release acceptance.

## Source and execution provenance

The final run completed all 12 cases × 3 repetitions = 36 tasks in 461.04 seconds, exit code 0, with `source_changed_during_capture=[]`. The recorded base commit is `76b411af797e480b0b8c117a5d06b78ebcfccd24`, with `git_dirty=true`; this base Git identity is not substituted for the exact captured source. All 82 captured source-file hashes matched the reviewed workspace and the exact files in `source-snapshot.zip` at review time.

- Plan SHA-256: `3c3a898c5cc5848f9aa179849def172f2836f956e0df24bf80ecc2038050e38f`.
- Canonical source-manifest SHA-256: `6510212a16ec181677ad6031d2be6f4e170fdf9cc65083da551196c25984c650`.
- Source snapshot SHA-256: `378d373ecd0a2089af862eae72bfeefcb03f4636b3e038048984cb8cd9a0dd3d`.
- Summary SHA-256: `a865dd79a31ec4f25b101b027fc95cd27232e6621284ad7e1bd4b720a861881b`.
- Raw data SHA-256: `2f1d5417b9880d282fccc0b52255ed0ff5ba1fc177684aeae6fe8bfc9ead8da5`.
- Report SHA-256: `45e69275e69bc4bff3b417c5b2bd5255b40c82cc9589cf9bdf22d66df9f549ae`.

The publication manifest covers exactly 152 retained files. Every published artifact hash passed, and all files other than the added source snapshot matched the retained runtime run byte-for-byte. Git `-text` preserves artifact bytes; other checkouts may normalize source line endings, so byte-level source comparisons should use the exact snapshot. Later changes must be identified separately and must not rewrite this captured source identity or the formal results. Superseded and failed local runs remain retained.

## Method, evidence, and denominator review

The reviewer read the final experiment script, frozen Ground Truth plan, integration runner, hash-mismatch Agent, and reused controlled execution lifecycle. Ground Truth is declared before execution from injected business facts: a fresh request, an independently configured signer, a deliberately different digest, a narrower declaration, or an actual version/binding/RPC fault. It is not derived from the verifier verdict. The hash-mismatch case submits a real successful Anvil transaction with this request and an incorrect digest. The N/A case uses the existing excluded-capability/no-dispatch path.

Execution uses real PostgreSQL, a controlled HTTP Agent subprocess, Anvil, Worker jobs, the existing record verifier, report freezing, and exported Bundles. All methods inspect the same frozen task trace. The online baseline measures initial HTTP accessibility/status, with 5xx FAIL and absent responses UNKNOWN; its PASS does not assert business correctness. Receipt evaluation only applies to write tasks and never turns read tasks into failures. Both method-applicable populations and the common write intersection are reported.

Independent recomputation confirmed the known Ground Truth populations, TP/FP/FN counts, coverage, Precision, main Recall, and F1. Binary metrics exclude UNKNOWN Ground Truth. Predicted UNKNOWN is an abstention; FN requires predicted PASS. Main Recall is TP divided by all known errors, so missed known errors include abstentions; the separately reported conditional Recall is not used to inflate F1. Empty denominators stay null. The 3 N/A reports use legacy report 1.1/rule 2, so their missing independent risk assessment is explicitly excluded from risk consistency.

Distributions below cover all 36 tasks; binary denominators use each method's predeclared applicable population.

| Method | PASS / FAIL / UNKNOWN / N/A | Known GT | Known errors | Known coverage | Recall | FPR | FNR | Precision | F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Online | 21 / 3 / 12 / 0 | 21 | 15 | 1.000 | 0.200 | 0.000 | 0.800 | 1.000 | 0.333 |
| Receipt | 12 / 0 / 12 / 12 | 15 | 12 | 0.800 | 0.000 | 0.000 | 0.750 | 0.000 | 0.000 |
| Proposed | 6 / 15 / 12 / 3 | 21 | 15 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |

The common write intersection contains 24 tasks, 15 known Ground Truth tasks and 12 known errors. Recall is 0.000 / 0.000 / 1.000 for Online / Receipt / Proposed; known coverage is 1.000 / 0.800 / 1.000. Receipt has 9 predicted-PASS false negatives and 3 abstentions among the 12 known errors. Proposed identifies all 9 expected critical risks; neither baseline evaluates those task-linked risks. These controlled-case counts are not production accuracy or prevalence estimates.

## Independent replay and resource checks

- `uv run --all-packages pytest tests/unit/test_task11_comparison.py -q`: **7 passed, 0 skipped**.
- Exact case/repetition set, plan/source/input/Bundle hashes, 36 traces, and finite nonnegative timings checked. Recorded RPC/HTTP attempt counts match the lengths of their actual instrumented traces.
- Independently recomputed metrics, resources, and verifier summaries match the retained summary exactly. Bundle outcome/reason consistency is **36/36**, and critical-risk consistency is **33/33**, excluding the 3 disclosed legacy N/A reports.
- Copied the completed output to a temporary unrelated directory, unset database/RPC/operator environment variables, and ran analysis from an unrelated working directory. All **36 Bundles** replayed offline, and `raw.json`, `summary.json`, `results.csv`, `report.md`, and `metrics.svg` matched the original bytes exactly.

Shared-pipeline observations are execution mean 3319.562 ms (SD 4053.745), chain verification mean 466.341 ms (SD 591.483), and report generation mean 2695.770 ms (SD 213.632), across 36 tasks. Platform RPC attempts total 2433 and Agent HTTP attempts total 48. The script reports per-case repeat counts, minima, maxima and SD. These are measured pipeline costs, not separate baseline runtime benchmarks; Agent subprocess RPC traffic is outside the platform counter.

The matrix has no distinct wrong-business-read fixture. Its deterministic `failure_every=1` service-error case does not estimate intermittent failure probability. Three repeats characterize these controlled observations only; they do not establish statistical significance. Reports retain insufficient evidence and `overall=null` rather than upgrading single-slot results to a sufficient reputation score.

The isolated offline replay verifies independence from the running database/chain and working directory. A brand-new clone plus dependency installation and full Linux Compose startup were not performed by this reviewer; project-level deployment and required CI remain final acceptance checks.

## Related repeat-demo review

The reviewer also inspected the final `scripts/smoke_m1.py` loop that anchors and independently verifies **both A and D** before tamper rejection. This addresses the previously unanchored D report blocking a later report's predecessor chain. The root agent's retained repeat logs (`task13-localdemo-repeat-verification.log`, `task13-localdemo-repeat-reports.log`, `task13-localdemo-repeat-m1.log`) show the repeat flow passing. Independent offline replay of those A/D Bundles confirms A business PASS and D business FAIL with critical conflict, both with receipt CONFIRMED and `overall=null`; offline anchor remains NOT_CHECKED. D's anchor commits its FAIL report without changing the business verdict. Live anchor confirmation and tamper rejection are recorded in the M1 smoke log.
