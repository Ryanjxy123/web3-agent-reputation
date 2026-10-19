"""Collect the ten availability-only samples frozen by liquidity-history-v1."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core import MeasurementPurpose, ProbeObservation, Verdict
from reputation_core.scoring import POLICY_VERSION, ScoredSample
from reputation_platform.public_targets import PUBLIC_TARGETS
from reputation_platform.safe_http import SafeHttpClient

POLICY_FILE = ROOT / "docs/adr/0004-liquidity-history-policy.md"
CONFIG_FILE = ROOT / "configs/pilots/brain-defi-liquidity-v1.json"
STOP_STATUSES = {401, 402, 403, 429}


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def classify(observation: ProbeObservation, run: Path) -> tuple[Verdict, str]:
    if observation.error_kind not in (None, "http_status_not_success"):
        return Verdict.UNKNOWN, observation.error_kind
    if not observation.body_complete:
        return Verdict.UNKNOWN, "Response processing was incomplete"
    status = observation.http_status
    if status is not None and 500 <= status <= 599:
        return Verdict.FAIL, "The public record endpoint returned HTTP 5xx"
    if status != 200:
        return Verdict.UNKNOWN, "HTTP status is outside the frozen decisive criterion"
    try:
        value = json.loads((run / observation.response_file).read_bytes())
    except (ValueError, TypeError):
        return Verdict.FAIL, "HTTP 200 response was not valid JSON"
    if not isinstance(value, dict) or not isinstance(value.get("history"), list) or not isinstance(value.get("last"), dict):
        return Verdict.FAIL, "HTTP 200 response lacked the expected history/last structure"
    return Verdict.PASS, "HTTP 200 with the expected public execution-record structure"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Explicit operator-configured proxy required for execution")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires an explicit --proxy")
    policy_bytes, config_bytes = POLICY_FILE.read_bytes(), CONFIG_FILE.read_bytes()
    config = json.loads(config_bytes)
    if (config["policy_version"], config["availability_target_key"], config["availability_count"],
        config["availability_interval_seconds"]) != (POLICY_VERSION, "brain-agent", 10, 30):
        raise ValueError("Availability configuration must match the frozen ten-slot, thirty-second plan")
    base = next(target for target in PUBLIC_TARGETS if target.key == "brain-agent")
    if base.url != config["history_source_url"]:
        raise ValueError("Pilot history URL differs from the static operator target")
    targets = tuple(replace(base, key=f"availability-{slot:03d}", purpose=MeasurementPurpose.AVAILABILITY)
                    for slot in range(1, 11))
    now = datetime.now(timezone.utc)
    run_id = f"availability-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    slots = [{"slot": slot, "target_key": target.key, "scheduled_offset_seconds": (slot - 1) * 30,
              "sample_id": f"{run_id}:{slot:03d}", "task_key": f"availability:{run_id}:{slot:03d}"}
             for slot, target in enumerate(targets, 1)]
    plan = {"run_id": run_id, "policy_version": POLICY_VERSION,
            "execution_enabled": args.execute_public_readonly, "purpose": "availability",
            "evidence_use": "availability only; not functional or behavioral scoring samples",
            "created_at": now.isoformat(), "url": base.url, "method": base.method,
            "request_limit": 10, "retries": 0, "interval_seconds": 30,
            "max_response_bytes": 1_048_576, "timeout_seconds": 15,
            "schedule_origin": "monotonic clock after client creation", "slots": slots,
            "policy": {"path": POLICY_FILE.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(policy_bytes).hexdigest()},
            "config": {"path": CONFIG_FILE.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(config_bytes).hexdigest()}}
    print(json.dumps(plan, indent=2))
    if not args.execute_public_readonly:
        return
    run = ROOT / "runtime" / run_id
    run.mkdir(parents=True)
    write_json(run / "manifest.json", plan)
    samples, host_stopped = [], False
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, max_requests=10) as client:
        origin = time.monotonic()
        for slot, target in zip(slots, targets):
            offset = slot["scheduled_offset_seconds"]
            if host_stopped:
                observed_at = datetime.now(timezone.utc).isoformat()
                skipped = {"request_key": target.key, "purpose": "availability", "observed_at": observed_at,
                           "request_sent": False, "reason": "host stopped after 401/402/403/429"}
                write_json(run / f"{target.key}.skip.json", skipped)
                verdict, reason, elapsed_ms, lag = Verdict.UNKNOWN, skipped["reason"], None, None
                evidence = [f"{target.key}.skip.json"]
            else:
                while (remaining := origin + offset - time.monotonic()) > 0:
                    time.sleep(min(30.0, remaining))
                lag = round(max(0.0, time.monotonic() - origin - offset) * 1000, 2)
                observation = client.fetch(target.key, run)
                observed_at = observation.observed_at.isoformat()
                verdict, reason = classify(observation, run)
                elapsed_ms = observation.elapsed_ms
                evidence = [f"{target.key}.observation.json"]
                if observation.response_file:
                    evidence.append(observation.response_file)
                host_stopped = observation.http_status in STOP_STATUSES
            sample = ScoredSample(
                sample_id=slot["sample_id"], task_key=slot["task_key"],
                purpose=MeasurementPurpose.AVAILABILITY, verdict=verdict, elapsed_ms=elapsed_ms,
                reason=reason, evidence=[(run / name).relative_to(ROOT).as_posix() for name in evidence],
            )
            payload = sample.model_dump(mode="json")
            write_json(run / f"{target.key}.sample.json", {
                "sample": payload, "observed_at": observed_at, "request_attempted": lag is not None,
                "scheduled_offset_seconds": offset, "start_lag_ms": lag,
            })
            samples.append(payload)
            print(f"{target.key}: {verdict.value}; elapsed_ms={elapsed_ms}; {reason}", flush=True)
    write_json(run / "samples.json", samples)
    print(f"evidence_directory={run}", flush=True)


if __name__ == "__main__":
    main()
