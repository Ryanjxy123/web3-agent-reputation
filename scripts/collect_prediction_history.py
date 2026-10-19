"""Collect retained Gnosis prediction history; default prints the bounded plan only."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core.admission import ProbeObservation
from reputation_platform.prediction_evidence import (
    EvidenceStore, PredictionProfile, collect_history, create_run, file_reference,
    runtime_directory,
)


def retained_hint(directory: Path, request_id: str | None) -> dict:
    directory = runtime_directory(directory)
    for observed in directory.glob("*.observation.json"):
        observation = ProbeObservation.model_validate_json(observed.read_bytes())
        if not observation.response_file or observation.http_status != 200 or observation.error_kind or not observation.body_complete:
            continue
        raw_path = (directory / observation.response_file).resolve()
        if not raw_path.is_relative_to(directory):
            raise ValueError("Index evidence escaped its retained directory")
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != observation.response_sha256:
            raise ValueError("Retained index hash differs")
        payload = json.loads(raw)
        deliveries = payload.get("data", {}).get("delivers", [])
        for hint in deliveries:
            if request_id is None or hint.get("requestId") == request_id:
                if observation.url != "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis" or observation.method != "POST":
                    raise ValueError("Pilot hint must come from the official retained read-only delivery index")
                hint["index_evidence"] = [file_reference(observed), file_reference(raw_path)]
                return hint
    raise ValueError("No requested pilot hint exists in the authenticated retained index")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("configs/pilots/olas-predict-2182-v1.json"))
    parser.add_argument("--reuse-runs", type=Path, nargs="*", default=[])
    parser.add_argument("--pilot-index-run", type=Path, help="One already viewed task; background only, never formal sampling")
    parser.add_argument("--pilot-request-id")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--parallel-reads", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--offline", action="store_true", help="Build solely from retained evidence, with zero HTTP")
    args = parser.parse_args()
    profile_path = (ROOT / args.profile).resolve()
    if not profile_path.is_relative_to(ROOT / "configs/pilots"):
        raise ValueError("Operator profile must be an explicit file under configs/pilots")
    profile = PredictionProfile.load(profile_path)
    if args.execute_public_readonly and (not args.proxy or args.offline):
        raise ValueError("Public reads require --proxy and cannot be combined with --offline")
    if not args.execute_public_readonly and not args.offline:
        print(json.dumps({"mode": "DRY_PLAN", "profile": profile.__dict__, "rpc": "https://rpc.gnosischain.com",
            "phases": ["current identity", "input/CAR plus market qualification without outputs", "durable fourteen-slot plan",
                       "selected output/CAR and historical chain checks"],
            "max_history_records": profile.history_max_deliveries, "retries": 0,
            "pilot_only": args.pilot_index_run is not None, "network_requests": 0}, ensure_ascii=False, indent=2))
        return
    hint = retained_hint(args.pilot_index_run, args.pilot_request_id) if args.pilot_index_run else None
    reuse = [runtime_directory(path) for path in args.reuse_runs]
    if args.pilot_index_run:
        reuse.append(runtime_directory(args.pilot_index_run))
    run = create_run(profile, profile_path)
    store = EvidenceStore(run, reuse, enabled=args.execute_public_readonly, proxy=args.proxy, parallel_reads=args.parallel_reads)
    try:
        bundle = collect_history(store, profile, pilot_hint=hint)
        outcome = {"status": bundle["plan"]["status"], "qualified_markets": bundle["plan"]["qualified_market_count"],
                   "tasks": len(bundle["tasks"]), "new_requests": store.sent, "pilot_only": hint is not None}
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        outcome = {"status": "UNKNOWN", "reason": str(error), "new_requests": store.sent, "pilot_only": hint is not None}
        store.save("incomplete.json", outcome)
    finally:
        store.close()
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    # manifest was persisted before HTTP; completion adds authenticated reused sources and final artifacts.
    manifest.update(completed_at=datetime.now(timezone.utc).isoformat(), outcome=outcome,
                    inputs=manifest["inputs"] + list(store.inputs.values()),
                    outputs=[file_reference(path) for path in sorted(run.glob("*.json")) if path != manifest_path])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run": run.relative_to(ROOT).as_posix(), **outcome}, ensure_ascii=False))
    if outcome["status"] == "UNKNOWN":
        sys.exit(1)


if __name__ == "__main__":
    main()
