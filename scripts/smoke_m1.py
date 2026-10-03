"""Finish the M1 gate: publish A, verify it independently, and reject a tamper."""

import io
import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

from reputation_verifier import VerificationError, verify_bundle
from smoke_identity import ROOT, operator_client


def tampered(source: bytes) -> str:
    output = tempfile.NamedTemporaryFile(suffix="-tampered.zip", delete=False)
    output.close()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output.name, "w") as changed:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "policy.json":
                data = data.replace(b"20", b"21", 1)
            changed.writestr(info, data)
    return output.name


def main() -> None:
    runtime = Path(os.environ.get("LOCAL_RUNTIME_DIR", ROOT / "runtime/local-chain"))
    record = json.loads((runtime / "report-smoke.json").read_bytes())
    with operator_client() as client:
        report_id = record["a"]["report_id"]
        queued = client.post(f"/api/v1/reports/{report_id}/anchor")
        if queued.status_code != 202:
            raise RuntimeError(f"Anchor request returned HTTP {queued.status_code}")
        deadline = time.monotonic() + 90
        while True:
            bundle = client.get(f"/api/v1/reports/{report_id}/bundle")
            if bundle.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
                    if json.loads(archive.read("anchor_receipt.json"))["status"] == "CONFIRMED":
                        break
            job = client.get(queued.json()["status_url"]).json()
            if job["state"] == "FAILED" or time.monotonic() >= deadline:
                raise RuntimeError(f"Anchor worker did not confirm: {job.get('reason_code')}")
            time.sleep(0.25)
        path = runtime / "report-a.zip"
        path.write_bytes(bundle.content)
        deployment = json.loads((runtime / "deployment.json").read_bytes())
        offline = verify_bundle(str(path))
        online = verify_bundle(str(path), rpc_url=deployment["rpc_url"])
        if offline["status"] != "PASS" or offline["anchor"]["status"] != "NOT_CHECKED":
            raise RuntimeError("Offline verifier did not preserve NOT_CHECKED anchor semantics")
        if online["anchor"]["status"] != "CONFIRMED":
            raise RuntimeError("Trusted RPC verifier did not confirm the published anchor")
        bad = tampered(bundle.content)
        try:
            try:
                verify_bundle(bad)
            except VerificationError:
                pass
            else:
                raise RuntimeError("Tampered bundle unexpectedly verified")
        finally:
            Path(bad).unlink(missing_ok=True)
    print("M1_ACCEPTANCE_PASS: A/D bundles, A anchor, offline/online verifier, tamper rejection")


if __name__ == "__main__":
    main()
