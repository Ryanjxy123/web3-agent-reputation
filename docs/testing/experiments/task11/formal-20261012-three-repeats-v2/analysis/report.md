# Task 11 actual controlled experiment

Generated from retained input/Bundle bytes by `scripts/task11_comparison.py analyse`.

Applicability is fixed before prediction: receipt only applies to write tasks. Ground Truth UNKNOWN is excluded from binary metrics. Prediction UNKNOWN is an abstention; FN requires prediction PASS. Unexpected predicted N/A stays in the known Ground Truth denominator.
Precision=TP/(TP+FP) (zero with known samples and no FAIL predictions), main recall=TP/all known errors including abstentions, F1=harmonic mean of precision and main recall (zero if both zero), FPR=FP/healthy Ground Truth, FNR=predicted-PASS FN/error Ground Truth. Conditional recall=TP/(TP+FN) is separately retained in JSON. Missed known errors include abstentions; known coverage=all binary predictions/known Ground Truth.

## Recorded environment

```json
{
  "os": "Windows-11-10.0.26200-SP0",
  "architecture": "AMD64",
  "processor": "Intel64 Family 6 Model 183 Stepping 1, GenuineIntel",
  "logical_cpu_count": 32,
  "python": "3.12.4",
  "anvil": "anvil Version: 1.8.4\nCommit SHA: 50af4efe189dc64bad2b75ed6990b835de66c4ae\nBuild Timestamp: 2026-10-01T13:50:42.600348400Z (1790862642)\nBuild Profile: dist",
  "postgres_binary": "postgres (PostgreSQL) 17.11"
}
```

## Observed cases

Counts below are real repeated tasks; they are not independent samples of production prevalence.

| Scenario | Independent GT | Online | Receipt | Proposed | Proposed reason | Critical risk |
|---|---|---|---|---|---|---|
| normal_write | PASS | PASS × 3 | PASS × 3 | PASS × 3 | — | 0/3 |
| historical_tx_reuse | FAIL | PASS × 3 | PASS × 3 | FAIL × 3 | TASK_ID_MISMATCH | 3/3 |
| wrong_executor | FAIL | PASS × 3 | PASS × 3 | FAIL × 3 | TX_WRONG_EXECUTOR | 3/3 |
| record_hash_mismatch | FAIL | PASS × 3 | PASS × 3 | FAIL × 3 | RECORD_HASH_MISMATCH | 3/3 |
| unsupported_claim | FAIL | PASS × 3 | UNKNOWN × 3 | FAIL × 3 | CAPABILITY_EXPLICITLY_UNSUPPORTED | 0/3 |
| intermittent_service_failure | FAIL | FAIL × 3 | NOT_APPLICABLE × 3 | FAIL × 3 | AGENT_SERVICE_ERROR | 0/3 |
| service_timeout | UNKNOWN | UNKNOWN × 3 | NOT_APPLICABLE × 3 | UNKNOWN × 3 | SERVICE_TIMEOUT | 0/3 |
| version_changed | UNKNOWN | UNKNOWN × 3 | UNKNOWN × 3 | UNKNOWN × 3 | IDENTITY_CHANGED | 0/3 |
| binding_changed | UNKNOWN | UNKNOWN × 3 | UNKNOWN × 3 | UNKNOWN × 3 | BINDING_UNVERIFIED | 0/3 |
| platform_rpc_failure | UNKNOWN | PASS × 3 | UNKNOWN × 3 | UNKNOWN × 3 | PLATFORM_RPC_ERROR | 0/3 |
| readonly_normal | PASS | PASS × 3 | NOT_APPLICABLE × 3 | PASS × 3 | — | 0/3 |
| undeclared_capability | NOT_APPLICABLE | UNKNOWN × 3 | NOT_APPLICABLE × 3 | NOT_APPLICABLE × 3 | CAPABILITY_NOT_DECLARED | 0/3 |

## method_applicable

| Method | PASS/FAIL/UNKNOWN/N/A | Known GT | TP/FP/FN | Abstention | Known coverage | Error detection | FPR/FNR | Precision/Recall/F1 | Key risks |
|---|---|---:|---|---:|---:|---:|---|---|---|
| online | 21/3/12/0 | 21 | 3/0/12 | 0 | 1.000 | 0.200 | 0.000/0.800 | 1.000/0.200/0.333 | 0/9 |
| receipt | 12/0/12/12 | 15 | 0/0/9 | 3 | 0.800 | 0.000 | 0.000/0.750 | 0.000/0.000/0.000 | 0/9 |
| proposed | 6/15/12/3 | 21 | 15/0/0 | 0 | 1.000 | 1.000 | 0.000/0.000 | 1.000/1.000/1.000 | 9/9 |

## common_write_intersection

| Method | PASS/FAIL/UNKNOWN/N/A | Known GT | TP/FP/FN | Abstention | Known coverage | Error detection | FPR/FNR | Precision/Recall/F1 | Key risks |
|---|---|---:|---|---:|---:|---:|---|---|---|
| online | 18/0/6/0 | 15 | 0/0/12 | 0 | 1.000 | 0.000 | 0.000/1.000 | 0.000/0.000/0.000 | 0/9 |
| receipt | 12/0/12/0 | 15 | 0/0/9 | 3 | 0.800 | 0.000 | 0.000/0.750 | 0.000/0.000/0.000 | 0/9 |
| proposed | 3/12/9/0 | 15 | 12/0/0 | 0 | 1.000 | 1.000 | 0.000/0.000 | 1.000/1.000/1.000 | 9/9 |

## Verifier and measured costs

Independent Bundle consistency (outcome and reason): 36/36; critical-risk consistency: 33/33, with 3 legacy N/A reports lacking risk assessment. Cost figures measure the shared platform pipeline on the same traces; they are not independent baseline runs.

| Scenario | Repeats | Execution ms mean ± SD | Chain verify ms mean ± SD | Report ms mean ± SD | RPC provider attempts mean | Agent HTTP attempts mean |
|---|---:|---|---|---|---:|---:|
| normal_write | 3 | 2567.532 ± 52.378 | 347.637 ± 47.471 | 2807.448 ± 173.974 | 76.000 | 2.000 |
| historical_tx_reuse | 3 | 2575.224 ± 65.312 | 445.674 ± 116.909 | 2773.950 ± 95.769 | 76.000 | 2.000 |
| wrong_executor | 3 | 2549.619 ± 90.424 | 381.339 ± 17.270 | 2834.234 ± 48.158 | 76.000 | 2.000 |
| record_hash_mismatch | 3 | 2561.763 ± 19.323 | 379.329 ± 36.993 | 2863.585 ± 128.016 | 76.000 | 2.000 |
| unsupported_claim | 3 | 2659.236 ± 82.002 | 328.994 ± 29.846 | 2859.609 ± 111.096 | 83.000 | 2.000 |
| intermittent_service_failure | 3 | 1543.919 ± 43.190 | 263.953 ± 21.309 | 2843.530 ± 287.954 | 73.000 | 1.000 |
| service_timeout | 3 | 16445.753 ± 110.009 | 280.796 ± 22.245 | 2581.065 ± 48.223 | 73.000 | 1.000 |
| version_changed | 3 | 1365.213 ± 18.520 | 186.796 ± 10.861 | 2607.565 ± 142.295 | 63.000 | 0.000 |
| binding_changed | 3 | 1391.359 ± 51.778 | 184.185 ± 18.003 | 2608.477 ± 71.761 | 66.000 | 0.000 |
| platform_rpc_failure | 3 | 2504.237 ± 45.207 | 2373.155 ± 15.980 | 2660.943 ± 353.458 | 62.000 | 2.000 |
| readonly_normal | 3 | 2508.932 ± 37.797 | 314.817 ± 29.246 | 2412.175 ± 308.015 | 73.000 | 2.000 |
| undeclared_capability | 3 | 1161.956 ± 39.247 | 109.413 ± 1.030 | 2496.653 ± 32.927 | 14.000 | 0.000 |
## Limits

- Controlled local PostgreSQL/Anvil cases do not estimate real-world prevalence or significance.
- The matrix has no distinct wrong-business-read fixture; read coverage demonstrates normal read PASS and receipt N/A, while write mismatch cases cover business inconsistency. Read-task detection should not be generalised until that fixture is added.
- Undeclared capability uses the existing capabilities-v1/rule-2 path; its legacy 1.1 report supports task replay but has no independent risk assessment. Risk consistency excludes these N/A reports explicitly.
- The intermittent fixture is configured failure_every=1 to select a deterministic service-failure slot; repeats do not estimate an intermittent failure probability.
- All methods reuse the same captured trace; resource timings describe the shared platform pipeline, not separate baseline benchmark runs.
- RPC attempts are instrumented in the platform process; controlled Agent subprocess RPC is outside that count.
- UNKNOWN is evidence abstention; read tasks are outside the receipt method and common-write denominator.
