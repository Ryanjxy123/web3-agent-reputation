"""One bounded round of documented, free, public read-only checks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.public_targets import PUBLIC_TARGETS
from reputation_platform.safe_http import SafeHttpClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Operator-configured local HTTP proxy")
    parser.add_argument("--targets", nargs="+", choices=[target.key for target in PUBLIC_TARGETS])
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires an explicit --proxy")
    targets = tuple(target for target in PUBLIC_TARGETS if not args.targets or target.key in args.targets)
    plan = [{"key": target.key, "method": target.method, "url": target.url,
             "purpose": target.purpose.value, "json": target.json_body}
            for target in targets]
    if not args.execute_public_readonly:
        print(json.dumps({"execution_enabled": False, "planned_requests": plan}, indent=2))
        return
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"candidate-check-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    manifest = {
        "started_at": now.isoformat(), "measurement": "candidate-feasibility-only",
        "request_limit": len(plan), "retries": 0, "max_response_bytes": 1_048_576,
        "timeout_seconds": 15, "paid_calls": False, "asset_operations": False,
        "planned_requests": plan,
    }
    with (run / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, max_requests=len(plan)) as client:
        for target in targets:
            try:
                observation = client.fetch(target.key, run)
            except PermissionError:
                with (run / f"{target.key}.skipped.json").open("x", encoding="utf-8") as stream:
                    json.dump({"key": target.key, "reason": "host_stop_or_budget", "agent_failure": False}, stream)
                print(f"{target.key}: SKIPPED host stop or request budget")
                continue
            print(f"{target.key}: HTTP={observation.http_status} outcome={observation.outcome} error={observation.error_kind}")
    print(f"evidence_directory={run}")


if __name__ == "__main__":
    main()
