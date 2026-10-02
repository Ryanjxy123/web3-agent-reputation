"""Local operator: sign demo challenges client-side; API and worker never receive keys."""

import json
import time
from pathlib import Path

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    runtime = ROOT / "runtime/local-chain"
    samples = json.loads((runtime / "samples.json").read_bytes())
    keys = json.loads((runtime / "setup-secrets.json").read_bytes())["keys"]
    config = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    output = {}
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        trust_env=False,
        timeout=20,
        headers={"Authorization": "Bearer " + config["OPERATOR_TOKEN"]},
    ) as client:

        def request(method, path, body=None):
            result = client.request(method, path, json=body)
            if result.is_error:
                # Do not include arbitrary remote content or credentials in diagnostics.
                raise RuntimeError(f"Identity API returned HTTP {result.status_code} for {path}")
            return result.json()

        for sample, values in samples.items():
            agent = request("POST", "/api/v1/agents", {"agent_ref": values["agent_ref"]})
            queued = request("POST", f"/api/v1/agents/{agent['id']}/refresh", {})
            deadline = time.monotonic() + 60
            while True:
                job = request("GET", queued["status_url"])
                if job["state"] == "SUCCEEDED":
                    break
                if job["state"] in {"FAILED", "CANCELLED"} or time.monotonic() > deadline:
                    raise RuntimeError("Identity worker did not complete the refresh")
                time.sleep(0.25)
            snapshot = request("GET", f"/api/v1/snapshots/{job['snapshot_id']}")
            base = f"/api/v1/snapshots/{snapshot['snapshot_id']}"
            review = request(
                "POST",
                base + "/claims/confirm",
                {
                    "confirmed_claims": ["anchor_record"],
                    "expected_review_version": 0,
                    "reason": "Local operator confirmed the controlled anchor_record declaration.",
                },
            )
            challenge = request(
                "POST",
                base + "/bindings/challenge",
                {
                    "executor": values["executor"],
                    "endpoint_id": f"fixture-{sample}",
                    "execution_chain_key": "local-demo",
                },
            )
            signatures = {
                f"{role}_signature": Account.sign_message(
                    encode_typed_data(full_message=challenge[f"{role}_typed_data"]),
                    keys[f"{role}-{sample}"],
                ).signature.to_0x_hex()
                for role in ("owner", "executor")
            }
            proof = request(
                "POST",
                base + "/bindings/verify",
                {"challenge_id": challenge["challenge_id"], **signatures},
            )
            assert proof["status"] == "VERIFIED"
            output[sample] = {
                "agent_id": agent["id"],
                "job_id": queued["job_id"],
                "snapshot": snapshot,
                "review": review,
                "binding": proof,
            }
    (runtime / "identity-smoke.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "IDENTITY_SMOKE_PASS: A/D snapshot, independent worker, reviewed claims, dual EIP-712 binding"
    )


if __name__ == "__main__":
    main()
