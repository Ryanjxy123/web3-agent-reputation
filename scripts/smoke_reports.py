"""Export reports for the latest verified A/D runs; repeated execution reuses frozen reports."""

import io
import json
import os
import time
import zipfile
from pathlib import Path

from reputation_core.evidence import hash_bytes, strict_json
from smoke_identity import ROOT, operator_client
from smoke_verification import main as verification_smoke


def main() -> None:
    runtime = Path(os.environ.get("LOCAL_RUNTIME_DIR", ROOT / "runtime/local-chain"))
    if not (runtime / "verification-smoke.json").exists():
        verification_smoke()
    verified = json.loads((runtime / "verification-smoke.json").read_bytes())
    results = {}
    with operator_client() as client:
        for sample, item in verified.items():
            base = f"/api/v1/evaluations/{item['run_id']}/report"
            queued = client.post(base)
            if queued.status_code != 202:
                raise RuntimeError(f"Report request returned HTTP {queued.status_code}")
            deadline = time.monotonic() + 90
            while True:
                response = client.get(base)
                if response.status_code == 200:
                    break
                job = client.get(queued.json()["status_url"]).json()
                if (
                    response.status_code != 404
                    or job["state"] == "FAILED"
                    or time.monotonic() >= deadline
                ):
                    raise RuntimeError(
                        f"Report worker did not freeze the report: {job.get('reason_code')}"
                    )
                time.sleep(0.25)
            report = response.json()
            assert report["core"]["scores"]["evaluation_state"] == "PARTIAL"
            assert report["core"]["scores"]["overall_score_bp"] is None
            assert report["core"]["scores"]["critical_conflict"] == (sample == "d")
            path = f"/api/v1/reports/{report['report_id']}/bundle"
            downloaded = client.get(path)
            assert downloaded.status_code == 200
            assert client.get(path).content == downloaded.content
            with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
                assert hash_bytes(archive.read("report_core.json")) == report["report_hash"]
                assert strict_json(archive.read("anchor_receipt.json"))["status"] == "NOT_REQUESTED"
            (runtime / f"report-{sample}.zip").write_bytes(downloaded.content)
            results[sample] = {
                "run_id": item["run_id"],
                "report_id": report["report_id"],
                "report_hash": report["report_hash"],
                "bundle": f"report-{sample}.zip",
            }
    (runtime / "report-smoke.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "REPORT_SMOKE_PASS: A/D immutable PARTIAL bundles exported; overall=null; anchoring NOT_REQUESTED"
    )


if __name__ == "__main__":
    main()
