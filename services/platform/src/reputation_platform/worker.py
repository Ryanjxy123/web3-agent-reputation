"""Execute operator-supported read-only evaluations under PostgreSQL fenced leases."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

from reputation_core.application import normalize_reference
from reputation_platform.db import LeaseLostError, Repository
from reputation_platform.settings import load_database_url

ROOT = Path(__file__).resolve().parents[4]
RUNTIME = ROOT / "runtime"


def retained_directory(value: str, prefix: str | None = None) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(RUNTIME.resolve()) or not path.is_dir() or path == RUNTIME.resolve():
        raise ValueError("Evaluation inputs must be retained runtime directories")
    if prefix and not path.name.startswith(prefix):
        raise ValueError("Unexpected child output directory")
    return path


def execute_child(command: list[str], log: Path, repo: Repository, job: dict, worker: str) -> Path:
    """Renew the lease while our own fixed collector/verifier process is running."""
    with log.open("x", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while True:
                try:
                    code = process.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    repo.renew_job(job["id"], worker, job["fencing_token"])
            repo.renew_job(job["id"], worker, job["fencing_token"])
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
            raise
    if code != 0:
        raise RuntimeError("Read-only evidence stage did not complete; its records have been retained")
    text = log.read_text(encoding="utf-8")
    sampler_prefixes = {"sample_availability.py": "availability-",
                        "sample_prediction_availability.py": "prediction-availability-"}
    sampler = Path(command[1]).name
    if sampler in sampler_prefixes:
        line = next(line for line in reversed(text.splitlines()) if line.startswith("evidence_directory="))
        return retained_directory(line.partition("=")[2], sampler_prefixes[sampler])
    return retained_directory(json.loads(text)["evidence_directory"], "evaluation-report-")


def job_log(profile: dict, job: dict) -> Path:
    directory = RUNTIME / "worker-jobs" / f"{job['id']}-{job['fencing_token']}"
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"job_id": job["id"], "fencing_token": job["fencing_token"],
                "policy_id": profile["policy_id"], "candidate_key": profile["candidate_key"],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Fresh availability sampling; reuse retained immutable historical task evidence",
                "profile": profile, "mainnet_writes": False, "model_calls": 0}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


def prediction_sources(repo: Repository, job: dict, worker: str, profile: dict, history_run: Path,
                       plan_run: Path) -> tuple[list[dict] | None, str, dict]:
    """Validate the fixed cohort and real file roots before issuing fresh public reads."""
    from reputation_core.prediction_chain import extract_task_anchors
    from reputation_platform.prediction_evidence import PredictionProfile
    from reputation_platform.prediction_report import RetainedEvidence, load_selection

    evidence = RetainedEvidence(ROOT)
    history_manifest = evidence.manifest(history_run)
    bundle_name = (history_run / "bundle.json").relative_to(ROOT).as_posix()
    references = [item for item in history_manifest.get("outputs", []) if item.get("path") == bundle_name]
    if len(references) != 1:
        return None, "历史证据包尚未完成归档，本次未发起新的公开采样。", {}
    evidence.remember(bundle_name, references[0]["sha256"])
    bundle = evidence.json(bundle_name)
    plan, tasks = bundle.get("plan", {}), bundle.get("tasks", [])
    slots = plan.get("slots", [])
    if (bundle.get("schema_version") != "prediction-evidence-bundle-v1"
        or plan.get("policy_version") != "prediction-history-v1" or plan.get("pilot_only") is not False
        or plan.get("eligibility_uses_outputs") is not False or plan.get("status") != "READY"
        or plan.get("qualified_market_count") != 14 or len(slots) != 14 or len(tasks) != 14
        or len({slot.get("market") for slot in slots if slot.get("market")}) != 14):
        return None, "保留的历史资料尚未固定十四个不同的合资格市场，暂不能开展完整评价；本次未新采样。", {}
    immutable_plan = bundle["plan_reference"]
    if json.loads(evidence.remember(immutable_plan["path"], immutable_plan["sha256"]).read_bytes()) != plan:
        raise ValueError("Prediction cohort differs from its original durable plan")
    profile_paths = [item["path"] for item in history_manifest["inputs"]
                     if Path(item["path"]).parent == Path("configs/pilots") and item["path"].endswith(".json")]
    if len(profile_paths) != 1:
        raise ValueError("Prediction history requires one immutable operator profile")
    historical_profile = PredictionProfile.load(evidence.remember(profile_paths[0]))
    if (historical_profile.__dict__ != bundle["profile"]
        or historical_profile.candidate_key != profile["candidate_key"]
        or normalize_reference(profile["registration_reference"]) != historical_profile.registration_reference):
        raise ValueError("Prediction history identity differs from the queued evaluation")
    load_selection(evidence, plan_run, historical_profile)
    for item in bundle["inputs"]:
        evidence.remember(item["path"], item["sha256"])
    outputs = []
    for index, (slot, task) in enumerate(zip(slots, tasks), 1):
        expected_purpose = "functional" if index <= 7 else "behavioral"
        if (slot.get("slot") != index or slot.get("purpose") != expected_purpose or not slot.get("request_id")
            or slot.get("market") in plan["excluded_pilot_markets"]
            or any(task.get(key) != slot.get(key) for key in ("slot", "purpose", "request_id", "market", "task_key"))):
            raise ValueError("Prediction task differs from the fixed disjoint cohort")
        if not task.get("output") or not task.get("chain_evidence") or not task.get("chain_verification", {}).get("output_digest"):
            return None, f"已固定的第{index}条历史交付尚缺原始文件或可核对的链上摘要；本次未新采样。", {}
        chain = evidence.tree(task["chain_evidence"])
        anchors = extract_task_anchors(chain, mech=historical_profile.mech, request_id=task["request_id"],
                                       confirmation_head=historical_profile.confirmation_head)
        digest = task["chain_verification"]["output_digest"]
        if digest != anchors["output_digest"]:
            raise ValueError("Stored prediction output root differs from its actual delivery event")
        output = task["output"]
        evidence.content(output, digest, str(int(task["request_id"], 16)))
        outputs.append({"request_id": task["request_id"], "root_digest": digest,
                        "response_file": output["response_file"], "sha256": output["sha256"]})
        if index % 4 == 0:
            repo.renew_job(job["id"], worker, job["fencing_token"])
    return outputs, "十四个固定历史文件与链上交付摘要已核对。", evidence.inputs


def evaluate_prediction(repo: Repository, job: dict, worker: str, profile: dict, proxy: str) -> None:
    inputs = {key: retained_directory(profile[key]) for key in ("history_run", "plan_run")}
    optional = {key: retained_directory(profile[key]) for key in ("translation_run", "identity_run") if profile.get(key)}
    log_dir = job_log(profile, job)
    outputs, reason, source_hashes = prediction_sources(repo, job, worker, profile,
                                                       inputs["history_run"], inputs["plan_run"])
    (log_dir / "preflight.json").write_text(json.dumps({"ready_for_fresh_sampling": outputs is not None,
        "reason": reason, "public_requests": 0, "model_calls": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    if outputs is None:
        repo.finalize_job(job["id"], worker, job["fencing_token"], status="NEEDS_INFO",
                          candidate_key=profile["candidate_key"], message=reason)
        return
    source_file = log_dir / "prediction-availability-sources.json"
    source_file.write_text(json.dumps({"candidate_key": profile["candidate_key"], "outputs": outputs,
        "inputs": [{"path": path, "sha256": digest} for path, digest in sorted(source_hashes.items())]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "COLLECTING",
        "正在测量本次公开历史交付文件的访问体验；这次不调用实时推理或发起新预测。", candidate_key=profile["candidate_key"])
    availability = execute_child([sys.executable, str(ROOT / "scripts/sample_prediction_availability.py"),
        "--sources", str(source_file), "--execute-public-readonly", "--proxy", proxy],
        log_dir / "availability.log", repo, job, worker)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "VERIFYING",
        "本次文件访问已保存，正在独立重建历史问题的概率表现、最终结算与链上交付归属。")
    command = [sys.executable, str(ROOT / "scripts/build_prediction_report.py"),
        "--history-run", str(inputs["history_run"]), "--plan-run", str(inputs["plan_run"]),
        "--availability-run", str(availability)]
    for key, directory in optional.items():
        command.extend(["--" + key.replace("_", "-"), str(directory)])
    report = execute_child(command, log_dir / "report.log", repo, job, worker)
    status = json.loads((report / "report.json").read_bytes())["scores"]["status"]
    if status not in ("COMPLETE", "PARTIAL", "NOT_EVALUATED"):
        raise ValueError("Unknown evidence-derived report status")
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "REPORTING",
        "独立核验已结束，正在保存报告与本次历史版本。")
    message = ("本次历史预测范围已完成三维评分。详细报告说明概率信用、独立结算、交付依据和未覆盖范围。"
               if status == "COMPLETE" else
               "本次证据处理已结束，已发布部分评价报告；尚未满足完整三维评分要求，不计算综合分，具体缺项见报告。")
    repo.finalize_job(job["id"], worker, job["fencing_token"], status="COMPLETE", message=message,
                      candidate_key=profile["candidate_key"], report_directory=report)


def evaluate(repo: Repository, job: dict, worker: str, profiles: list[dict], *, enabled: bool, proxy: str | None) -> None:
    canonical = normalize_reference(job["reference"])
    if canonical is None:
        repo.finalize_job(job["id"], worker, job["fencing_token"], status="UNSUPPORTED",
            message="暂不能识别这份注册资料。请提供完整链号、注册合约与 Agent 编号，或 8004scan 的 Agent 页面链接。")
        return
    matches = [profile for profile in profiles if normalize_reference(profile["registration_reference"]) == canonical]
    if not matches:
        repo.finalize_job(job["id"], worker, job["fencing_token"], status="NEEDS_INFO",
            message="这份注册标识已保留，当前还缺可核验的服务资料与已适配方案，暂不能评价。已有对象的报告仍可浏览。")
        return
    if len(matches) != 1:
        raise ValueError("Operator profile identity is ambiguous")
    profile = matches[0]
    if not enabled:
        repo.finalize_job(job["id"], worker, job["fencing_token"], status="NEEDS_INFO",
            candidate_key=profile["candidate_key"],
            message="当前暂未启用新的公开采样，本次没有产生新分数；已有报告和历史仍可查看。")
        return
    if not proxy:
        raise ValueError("An enabled evaluation requires an explicit operator proxy")
    if profile["policy_id"] == "prediction-history-v1":
        evaluate_prediction(repo, job, worker, profile, proxy)
        return
    if profile["policy_id"] != "liquidity-history-v1":
        raise ValueError("An enabled evaluation requires the supported policy and explicit operator proxy")
    inputs = {key: retained_directory(profile[key]) for key in ("history_run", "context_run", "plan_run")}
    rpc_runs = [retained_directory(value) for value in profile["rpc_runs"]]
    log_dir = job_log(profile, job)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "COLLECTING",
        "正在采集本次记录入口的实际访问结果，随后独立核验已公布的历史任务。", candidate_key=profile["candidate_key"])
    availability = execute_child([sys.executable, str(ROOT / "scripts/sample_availability.py"),
        "--execute-public-readonly", "--proxy", proxy], log_dir / "availability.log", repo, job, worker)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "VERIFYING",
        "本次访问采样已保存，正在核对历史交易、公布结果和证据来源。")
    command = [sys.executable, str(ROOT / "scripts/build_liquidity_report.py"),
        "--history-run", str(inputs["history_run"]), "--rpc-runs", *map(str, rpc_runs),
        "--context-run", str(inputs["context_run"]), "--availability-run", str(availability),
        "--plan-run", str(inputs["plan_run"])]
    report = execute_child(command, log_dir / "report.log", repo, job, worker)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "REPORTING", "独立核验已结束，正在保存详细报告与本次历史版本。")
    repo.finalize_job(job["id"], worker, job["fencing_token"], status="COMPLETE",
        message="本次评价已完成。报告说明实际样本、得分依据及未覆盖范围。",
        candidate_key=profile["candidate_key"], report_directory=report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Handle at most one queued job")
    parser.add_argument("--profiles", type=Path, default=RUNTIME / "platform-config/profiles.json")
    parser.add_argument("--enable-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    args = parser.parse_args()
    if args.enable_public_readonly and not args.proxy:
        parser.error("Read-only execution requires an explicit --proxy")
    profiles = json.loads(args.profiles.read_text(encoding="utf-8")) if args.profiles.is_file() else []
    repo = Repository(load_database_url())
    worker = "worker-" + secrets.token_hex(12)
    while True:
        job = repo.claim_job(worker)
        if job is None:
            if args.once:
                return
            time.sleep(2)
            continue
        try:
            evaluate(repo, job, worker, profiles, enabled=args.enable_public_readonly, proxy=args.proxy)
        except LeaseLostError:
            print("Lease changed; the obsolete worker did not publish a result", flush=True)
        except Exception as error:
            # Exception messages may contain private connection settings; record the class only.
            print(f"job={job['id']}; platform_error={type(error).__name__}", flush=True)
            try:
                repo.finalize_job(job["id"], worker, job["fencing_token"], status="FAILED",
                    message="平台本次未能完成证据处理，原始记录已保留。这不代表 Agent 的业务失败，已有报告仍可查看。")
            except LeaseLostError:
                pass
        if args.once:
            return


if __name__ == "__main__":
    main()
