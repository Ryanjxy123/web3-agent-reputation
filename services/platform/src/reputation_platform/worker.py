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
    if command[1].endswith("sample_availability.py"):
        line = next(line for line in reversed(text.splitlines()) if line.startswith("evidence_directory="))
        return retained_directory(line.partition("=")[2], "availability-")
    return retained_directory(json.loads(text)["evidence_directory"], "evaluation-report-")


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
    if not proxy or profile["policy_id"] != "liquidity-history-v1":
        raise ValueError("An enabled evaluation requires the supported policy and explicit operator proxy")
    inputs = {key: retained_directory(profile[key]) for key in ("history_run", "context_run", "plan_run")}
    rpc_runs = [retained_directory(value) for value in profile["rpc_runs"]]
    log_dir = RUNTIME / "worker-jobs" / f"{job['id']}-{job['fencing_token']}"
    log_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"job_id": job["id"], "fencing_token": job["fencing_token"],
                "policy_id": profile["policy_id"], "candidate_key": profile["candidate_key"],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Fresh availability sampling; reuse retained immutable historical task evidence",
                "profile": profile, "mainnet_writes": False, "model_calls": 0}
    (log_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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
