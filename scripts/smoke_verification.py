"""Real API/worker A PASS and D semantic FAIL, including independent RPC assertions."""

import json
import os
import time
from pathlib import Path

from smoke_execution import main as execution_smoke
from smoke_identity import ROOT, operator_client


def main() -> None:
    execution_smoke()
    runtime = Path(os.environ.get("LOCAL_RUNTIME_DIR", ROOT / "runtime/local-chain"))
    executions = json.loads((runtime / "execution-smoke.json").read_bytes())
    results = {}
    with operator_client() as client:
        for sample, execution in executions.items():
            run_id = execution["run"]["run_id"]
            deadline = time.monotonic() + 60
            while True:
                response = client.get(f"/api/v1/evaluations/{run_id}/verification")
                if response.status_code == 200:
                    break
                if response.status_code != 404 or time.monotonic() >= deadline:
                    raise RuntimeError("Independent worker verification did not complete")
                time.sleep(0.25)
            result = response.json()
            rules = {item["rule_id"]: item for item in result["assertions"]}
            assert rules["receipt.success"]["outcome"] == "PASS"
            if sample == "a":
                assert result["outcome"] == "PASS", result["reason_code"]
                assert result["task_link"]["verified_tx_hash"]
            else:
                assert sample == "d"
                assert result["outcome"] == "FAIL" and result["reason_code"] == "SEMANTIC_MISMATCH"
                assert rules["record.request"]["reason_code"] == "TASK_ID_MISMATCH"
                assert rules["record.hash"]["reason_code"] == "RECORD_HASH_MISMATCH"
                assert result["task_link"]["verified_tx_hash"] is None
            results[sample] = {"run_id": run_id, "verification": result}
    (runtime / "verification-smoke.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "VERIFICATION_SMOKE_PASS: A PASS; D real successful receipt rejected as SEMANTIC_MISMATCH"
    )


if __name__ == "__main__":
    main()
