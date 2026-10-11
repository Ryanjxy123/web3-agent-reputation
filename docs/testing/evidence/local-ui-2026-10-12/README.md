# Real local dashboard acceptance — 2026-10-12

These are actual A/D dashboard downloads and screenshots from an isolated PostgreSQL/Anvil/API/Worker/HTTP Agent setup. The user-facing page started authorized evaluations through the existing token/grant and current dual-signature binding checks; it later loaded their terminal runs, displayed task assertions, read manifest-scoped evidence, downloaded the Bundles and imported the independently executed CLI results.

A is business PASS. D has a successful receipt but business FAIL/TASK_ID_MISMATCH. Both single-slot M1 reports remain PARTIAL/overall=null, legacy report 1.1 and NOT_REQUESTED/UNANCHORED. Their independent CLI output proves offline internal consistency, not anchor confirmation. Earlier real CLI smoke separately anchored both local reports and verified them with trusted loopback RPC; these UI downloads deliberately show the subsequent unanchored reports.

The A start initially completed while development HMR reset the page; the final acceptance reloads that existing UI-started run. D initially received HTTP409/BINDING_UNVERIFIED after its time-limited binding expired; renewing the local dual signatures and creating a new one-task grant allowed the authorized UI start. No backend guard was bypassed. These failed development attempts remain in ignored local runtime and are not counted as passing runs.

Actual long evidence initially expanded the page width; the card/grid minimum-width correction was rechecked with a 1360px viewport, asserted page width1360 after both evidence load and real CLI import, and captured the reviewed screenshots. The pinned browser regression also covers that boundary. The operator field is masked; no private context is included.

Replay the original downloaded bytes from a clean checkout:

```powershell
uv run --all-packages reputation-verify docs/testing/evidence/local-ui-2026-10-12/ui-a.zip
uv run --all-packages reputation-verify docs/testing/evidence/local-ui-2026-10-12/ui-d.zip
```

`publication-manifest.json` commits the exact Bundle/CLI JSON/acceptance/screenshot bytes. The original report source version truthfully records the dirty capture checkout; these are local controlled demo reports, not a claim of mainnet identity, production adequacy or final Release acceptance.
