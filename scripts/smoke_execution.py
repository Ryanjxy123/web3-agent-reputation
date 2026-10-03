"""Exercise real API -> independent worker -> A/D; candidates are not verdicts."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from smoke_identity import ROOT, operator_client
from smoke_identity import main as identity_smoke


def main() -> None:
    identity_smoke()  # Fresh snapshots and time-limited signatures; no fixture labels reach the API.
    runtime = Path(os.environ.get("LOCAL_RUNTIME_DIR", ROOT / "runtime/local-chain"))
    identities = json.loads((runtime / "identity-smoke.json").read_bytes())
    output = {}
    with operator_client() as client:

        def request(method, path, body=None, headers=None):
            response = client.request(method, path, json=body, headers=headers)
            if response.is_error:
                raise RuntimeError(f"Dispatch API returned HTTP {response.status_code} for {path}")
            return response.json()

        for sample, identity in identities.items():
            grant = request(
                "POST",
                "/api/v1/access-grants",
                {
                    "snapshot_id": identity["snapshot"]["snapshot_id"],
                    "endpoint_id": f"fixture-{sample}",
                    "max_tasks": 1,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z"),
                    "consent_ref": "Operator-authorized local synthetic credential smoke",
                },
            )["grant"]
            created = request(
                "POST",
                "/api/v1/evaluations",
                {
                    "snapshot_id": identity["snapshot"]["snapshot_id"],
                    "review_version": identity["review"]["review_version"],
                    "profile": "record-write-v1",
                    "policy_version": "policy-v1",
                    "grant_ids": [grant["grant_id"]],
                    "suite_id": "m1-smoke-v1",
                },
                {"Idempotency-Key": f"smoke:{uuid4()}"},
            )
            base = created["status_url"]
            deadline = time.monotonic() + 90
            while True:
                state = request("GET", base)
                if state["settled"] == 1:
                    break
                if time.monotonic() >= deadline or state["status"] == "FAILED":
                    raise RuntimeError("Independent worker did not settle the dispatch")
                time.sleep(0.25)
            observations = request("GET", base + "/observations")
            assert observations[-1]["candidate_tx_hash"], (
                "Expected a real candidate for each controlled service"
            )
            output[sample] = {
                "run": state,
                "grant": grant,
                "plan": request("GET", base + "/plan"),
                "observations": observations,
            }
    (runtime / "execution-smoke.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "DISPATCH_SMOKE_PASS: A/D real HTTP candidates saved; business verdicts require independent verification"
    )


if __name__ == "__main__":
    main()
