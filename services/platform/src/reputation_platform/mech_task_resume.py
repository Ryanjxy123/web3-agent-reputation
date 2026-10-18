"""Fill absent files in a new review, preserving the original seven-task cohort."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from reputation_core.admission import Verdict
from reputation_core.prediction_chain import extract_task_anchors, verify_prediction_chain
from reputation_platform.mech_task_collection import _LeasedEvidenceStore
from reputation_platform.prediction_evidence import EvidenceUnavailable, collect_task, file_reference

POLICY = "docs/adr/0012-resume-frozen-task-evidence.md"
FIELDS = ("chain_evidence", "input", "output")


def _save(evidence, name: str, value: dict) -> dict:
    path = evidence.run / name
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    reference = file_reference(path, evidence.root)
    evidence.inputs[reference["path"]] = reference["sha256"]
    return reference


def resume_mech_source(reader, source, identity, evidence) -> Path | None:
    data = source["data"]
    if (data.get("schema_version") != "mech-task-evidence-bundle-v1"
        or identity["canonical"] != source["canonical"]
        or (evidence.root / source["bundle"]["path"]).resolve().parent == evidence.run.resolve()
        or any((evidence.run / name).exists() for name in ("mech-resume-plan.json", "mech-resume-issue.json"))):
        return None
    missing = [{"slot": task["slot"], "request_id": task.get("request_id"), "task_key": task.get("task_key"),
                "fields": [field for field in FIELDS if task.get(field) is None]}
               for task in source["tasks"] if any(task.get(field) is None for field in FIELDS)]
    if not missing:
        return None
    # Missing files may be collected; changed retained bytes must never be replaced.
    try:
        for name, digest in source["references"].items():
            reader.remember(name, digest)
    except (ValueError, OSError) as error:
        _save(evidence, "mech-resume-issue.json", {
            "status": "UNKNOWN", "reason": "原来源认证异常，未补采或替换原件：" + str(error),
            "source_bundle": source["bundle"], "retries": 0})
        return None
    policy_path = reader.remember(POLICY)
    resume_of = {key: deepcopy(source[key]) for key in ("bundle", "manifest", "plan")}
    resume_plan = _save(evidence, "mech-resume-plan.json", {
        "schema_version": "mech-resume-plan-v1", "policy_version": "service-contract-v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "policy": file_reference(policy_path, evidence.root),
        "source_bundle": resume_of["bundle"], "source_manifest": resume_of["manifest"],
        "source_plan": resume_of["plan"], "canonical": source["canonical"],
        "slots": deepcopy(source["slots"]), "missing_files": missing,
        "selection": "仅补原七个行为任务的None缺项；已有内容不替换，不换任务或参数。",
        "measurement_purpose": "background", "mainnet_writes": False, "paid_calls": False, "retries": 0})
    bundle = deepcopy(data)
    profile = SimpleNamespace(**bundle["profile"])
    tasks = {task["slot"]: task for task in bundle["tasks"] if task["purpose"] == "behavioral"}
    bound = sum((15 if "chain_evidence" in item["fields"] else 0)
                + 2 * sum(field in item["fields"] for field in ("input", "output")) for item in missing)
    store = _LeasedEvidenceStore(evidence.run, [(evidence.root / source["bundle"]["path"]).parent],
        enabled=evidence.enabled, proxy=evidence.proxy, max_requests=bound, parallel_reads=2,
        root=evidence.root, heartbeat=evidence.heartbeat)
    attempts = []
    try:
        for item in missing:
            task = tasks[item["slot"]]
            attempt = {**deepcopy(item), "recovered": [], "issues": []}
            attempts.append(attempt)
            if task.get("verdict") == "FAIL" or task.get("chain_verification", {}).get("verdict") == "FAIL":
                attempt["issues"].append("已有FAIL结论，不以补采替换已保留的矛盾。")
                continue
            if not task.get("request_id") or not task.get("hint"):
                attempt["issues"].append("原槽没有完整任务号或原索引线索；未猜参数或换槽。")
                continue
            try:
                if task["chain_evidence"] is None:
                    task["chain_evidence"] = collect_task(store, task["hint"], profile)
                    attempt["recovered"].append("chain_evidence")
                chain = reader.tree(task["chain_evidence"])
                verification = verify_prediction_chain(chain, mech=identity["mech"], service_id=identity["service_id"],
                    request_id=task["request_id"], confirmation_head=identity["confirmation_head"])
                if verification.verdict == Verdict.FAIL:
                    attempt["issues"].append("原始链上事实已显示履约矛盾，未通过补取文件改变该结论。")
                    continue
                anchors = extract_task_anchors(chain, mech=identity["mech"], request_id=task["request_id"],
                                               confirmation_head=identity["confirmation_head"])
                # Authenticate existing content before any missing-content request.
                for field, digest, filename in (
                    ("input", anchors["input_digest"], "metadata.json"),
                    ("output", anchors["output_digest"], str(int(task["request_id"], 16))),
                ):
                    if task[field] is not None:
                        reader.content(task[field], digest, filename)
            except (EvidenceUnavailable, ValueError, KeyError, TypeError, OSError) as error:
                attempt["issues"].append(str(error))
                continue
            for field, digest, filename in (
                ("input", anchors["input_digest"], "metadata.json"),
                ("output", anchors["output_digest"], str(int(task["request_id"], 16))),
            ):
                if field not in item["fields"]:
                    continue
                try:
                    task[field] = store.ipfs(f"mech-resume-{task['slot']:02d}-{field}", digest, filename)
                    attempt["recovered"].append(field)
                except (EvidenceUnavailable, ValueError, KeyError, TypeError, OSError) as error:
                    attempt["issues"].append(field + "：" + str(error))
        inputs = dict(reader.inputs)
        inputs.update({reference["path"]: reference["sha256"] for reference in store.inputs.values()})
        inputs[resume_plan["path"]] = resume_plan["sha256"]
        bundle.update(resume_of=resume_of, resume_plan=resume_plan, resume_attempts=attempts,
            inputs=[{"path": name, "sha256": digest} for name, digest in sorted(inputs.items())],
            new_request_count=store.sent, issues=[*data.get("issues", []), *store.issues])
        reference = store.save("mech-task-bundle.json", bundle)
        manifest = store.save("mech-source-manifest.json", {
            "schema_version": "mech-task-source-manifest-v1", "completed_at": datetime.now(timezone.utc).isoformat(),
            "inputs": bundle["inputs"], "outputs": [reference]})
        evidence.inputs.update(inputs)
        evidence.inputs.update({reference["path"]: reference["sha256"], manifest["path"]: manifest["sha256"]})
        return evidence.root / reference["path"]
    finally:
        evidence.inputs.update(reader.inputs)
        evidence.inputs.update({reference["path"]: reference["sha256"] for reference in store.inputs.values()})
        evidence.request_count += store.sent
        store.close()
