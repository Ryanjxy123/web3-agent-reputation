"""Automatic intake and scoped reports from registered, retained service evidence."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets

from reputation_core import MeasurementPurpose, ProbeObservation, Verdict
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import SERVICE_CONTRACT_POLICY_VERSION
from reputation_platform.evaluation_report import render_evaluation_report
from reputation_platform.settings import PROJECT_ROOT


def _save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def verify_generic_report_sources(root: Path, report: EvaluationReport, hashes: dict[str, str]) -> str:
    """Recheck identity and actual protocol observations, rather than copied PASS values."""
    from reputation_platform.protocol_evaluation import availability_verdict, descriptor_remote, VERSIONS, _result, _tools
    from reputation_platform.registration_discovery import verify_registration_proof

    proofs = [name for name in hashes if Path(name).name == "registration-proof.json"]
    if len(proofs) != 1:
        raise ValueError("A generic report requires one retained registration proof")
    identity = verify_registration_proof(root, proofs[0], report.registration_reference)
    if report.scores.status == "COMPLETE" and not identity["registration_verified"]:
        raise ValueError("A complete report requires chain-verified registration")
    endpoints = {item["endpoint"] for item in identity["services"]
                 if str(item.get("name", "")).casefold() == "mcp" and item.get("endpoint")}
    def retained(name: str) -> bytes:
        path = (root / name).resolve()
        if (not path.is_relative_to(root.resolve()) or name not in hashes
            or hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]):
            raise ValueError("Protocol evidence is absent from the verified input manifest")
        return path.read_bytes()

    def background(name: str):
        obs = ProbeObservation.model_validate_json(retained(name))
        request = json.loads(retained(name.removesuffix('.observation.json') + '.request-plan.json'))
        if (obs.purpose != MeasurementPurpose.BACKGROUND or not obs.body_complete or obs.error_kind
            or request['key'] != obs.request_key or request['url'] != obs.url or request['method'] != obs.method
            or request['json'] != (json.loads(obs.request_json) if obs.request_json else None)):
            raise ValueError("Protocol discovery differs from its original background request")
        raw = retained((Path(name).parent / obs.response_file).as_posix())
        if hashlib.sha256(raw).hexdigest() != obs.response_sha256:
            raise ValueError("Protocol discovery response differs from its retained observation")
        return obs, raw, request

    for name in hashes:
        if name.endswith('-document.observation.json'):
            obs = ProbeObservation.model_validate_json(retained(name))
            if obs.url in endpoints and obs.http_status == 200 and obs.method == 'GET' and obs.body_complete and not obs.error_kind:
                _, raw, _ = background(name)
                remote = descriptor_remote(json.loads(raw))
                if remote:
                    endpoints.add(remote)

    plans, observed_files, stopped_urls = {}, set(), set()
    for explanation in report.samples:
        sample = explanation.sample
        if sample.purpose != MeasurementPurpose.AVAILABILITY:
            raise ValueError("This generic adapter has not yet supplied business-task verification")
        plan_names = [name for name in sample.evidence if name.endswith('-availability-plan.json')]
        if len(plan_names) != 1:
            raise ValueError("Every availability slot requires its original sampling plan")
        plan_name = plan_names[0]
        if plan_name not in plans:
            plan = json.loads(retained(plan_name))
            prefix = plan_name.removesuffix('-availability-plan.json')
            discovery = []
            for name in hashes:
                if name.startswith(prefix + '-service-') and name.endswith('-tools.observation.json'):
                    obs = ProbeObservation.model_validate_json(retained(name))
                    if (obs.url == plan['url'] and obs.method == 'POST'
                        and obs.purpose == MeasurementPurpose.BACKGROUND
                        and obs.http_status == 200 and obs.body_complete and not obs.error_kind
                        and obs.observed_at <= datetime.fromisoformat(plan['created_at'])):
                        obs, raw, request_plan = background(name)
                        request = json.loads(obs.request_json)
                        _tools(_result(raw, request['id']))
                        stem = name.removesuffix('tools.observation.json')
                        initialized, _, _ = background(stem + 'initialized.observation.json')
                        initial, initial_raw, _ = background(stem + 'initialize.observation.json')
                        initial_request = json.loads(initial.request_json)
                        negotiated = _result(initial_raw, initial_request['id'])
                        server = negotiated.get('serverInfo', {})
                        if (request.get('method') == 'tools/list'
                            and initial_request.get('method') == 'initialize'
                            and initial.http_status == 200 and initialized.http_status in (202, 204)
                            and json.loads(initialized.request_json) == {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
                            and initial.url == initialized.url == obs.url and initial.method == initialized.method == 'POST'
                            and initial.observed_at <= initialized.observed_at <= obs.observed_at
                            and negotiated.get('protocolVersion') in VERSIONS
                            and isinstance(negotiated.get('capabilities', {}).get('tools'), dict)
                            and all(isinstance(server.get(field), str) and server[field] for field in ('name', 'version'))
                            and request_plan['headers'] == plan['headers']
                            and request_plan['headers'].get('MCP-Protocol-Version') == negotiated['protocolVersion']):
                            discovery.append(name)
            if (plan.get('policy_version') != SERVICE_CONTRACT_POLICY_VERSION
                or plan.get('purpose') != 'availability' or plan.get('method') != 'POST'
                or plan.get('url') not in endpoints or plan.get('interval_seconds') != 30
                or len(plan.get('slots', [])) != 10 or not discovery
                or hashes.get(plan['policy']['path']) != plan['policy']['sha256']):
                raise ValueError("Availability plan lacks registered, confirmed protocol provenance")
            for index, slot in enumerate(plan['slots']):
                if (slot['offset_seconds'] != index * 30
                    or slot['json'] != {'jsonrpc': '2.0', 'id': slot['key'], 'method': 'tools/list', 'params': {}}):
                    raise ValueError("Availability slots differ from the fixed sampling policy")
            plans[plan_name] = plan
        plan = plans[plan_name]
        slots = [slot for slot in plan['slots'] if slot['key'] == sample.sample_id]
        if len(slots) != 1 or sample.task_key != 'availability:' + sample.sample_id:
            raise ValueError("Availability sample differs from its planned slot")
        slot = slots[0]
        paths = [name.replace("\\", "/") for name in sample.evidence
                 if name.endswith(".observation.json")]
        if not paths:
            skips = [name for name in sample.evidence if name.endswith('.skip.json')]
            skip = json.loads(retained(skips[0])) if len(skips) == 1 else {}
            if (len(skips) != 1 or Path(skips[0]).name != sample.sample_id + '.skip.json'
                or skip.get('request_sent') is not False
                or (plan['url'] not in stopped_urls and skip.get('reason') != 'host_stopped')
                or sample.verdict != Verdict.UNKNOWN or sample.elapsed_ms is not None
                or explanation.observed_at is not None):
                raise ValueError("Unsent availability slots must retain their skip and remain UNKNOWN")
            continue
        if len(paths) != 1 or paths[0] in observed_files:
            raise ValueError("Every availability slot requires its own retained observation")
        observed_files.add(paths[0])
        observation_path = (root / paths[0]).resolve()
        observation = ProbeObservation.model_validate_json(retained(paths[0]))
        request_plan = json.loads(retained(paths[0].removesuffix('.observation.json') + '.request-plan.json'))
        if (observation.purpose != MeasurementPurpose.AVAILABILITY or observation.url != plan['url']
            or observation.request_key != slot['key']
            or observation.method != plan['method'] or json.loads(observation.request_json) != slot['json']
            or request_plan['key'] != slot['key'] or request_plan['json'] != slot['json']
            or request_plan['method'] != plan['method'] or request_plan['measurement_purpose'] != 'availability'
            or request_plan['headers'] != plan['headers'] or request_plan['url'] != plan['url']
            or observation.observed_at < datetime.fromisoformat(plan['created_at']) + timedelta(seconds=slot['offset_seconds'])):
            raise ValueError("Observation is not this Agent's declared protocol availability sample")
        raw = b""
        if observation.response_file:
            response = (observation_path.parent / observation.response_file).resolve()
            name = response.relative_to(root).as_posix()
            if (response.parent != observation_path.parent or name not in hashes
                or hashlib.sha256(response.read_bytes()).hexdigest() != observation.response_sha256):
                raise ValueError("Protocol response changed or escaped its original observation")
            raw = response.read_bytes()
        verdict, _ = availability_verdict(observation.model_dump(mode="json"), raw)
        if observation.http_status in (401, 402, 403, 429):
            stopped_urls.add(plan['url'])
        if (verdict != sample.verdict or observation.elapsed_ms != sample.elapsed_ms
            or observation.observed_at != explanation.observed_at
            or observation.observed_at > report.generated_at):
            raise ValueError("Protocol sample differs from its actual retained response")
    for name, plan in plans.items():
        actual = [item.sample.sample_id for item in report.samples if name in item.sample.evidence]
        if actual != [slot['key'] for slot in plan['slots']]:
            raise ValueError("The report must preserve every planned availability slot in order")
    return identity["canonical"]


def evaluate_generic(repo, job: dict, worker: str, canonical: str, proxy: str,
                     *, root: Path = PROJECT_ROOT) -> None:
    from reputation_platform.protocol_evaluation import collect_protocol_evaluation
    from reputation_platform.registration_discovery import (
        DiscoveryEvidence, discover_registration, verify_registration_proof,
    )

    started = datetime.now(timezone.utc)
    run = root / "runtime" / f"generic-evaluation-{started:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    _save(run / "intake-intent.json", {
        "started_at": started.isoformat(), "registration_reference": canonical,
        "policy_version": SERVICE_CONTRACT_POLICY_VERSION, "job_id": job["id"],
        "scope": "Registered documents, protocol discovery and applicable evidence-backed evaluation",
        "business_calls": False, "mainnet_writes": False, "retries": 0,
    })
    evidence = DiscoveryEvidence(root, run, proxy, enabled=True,
        heartbeat=lambda: repo.renew_job(job["id"], worker, job["fencing_token"]))
    registration = discover_registration(canonical, evidence)
    try:
        identity = verify_registration_proof(root, registration["proof_path"], canonical)
    except ValueError:
        repo.finalize_job(job["id"], worker, job["fencing_token"], status="NEEDS_INFO",
            message="已尝试自动读取注册资料，尚未取得能与这份身份对应的有效来源。本次未产生分数，采集记录已保留。")
        return
    if not identity.get("registration_verified") and not identity.get("directory_verified"):
        raise ValueError("No authenticated source supports the submitted identity")
    existing = next((agent for agent in repo.list_agents() if agent.registration_reference == canonical), None)
    key = existing.key if existing else registration["candidate_key"]
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "COLLECTING",
        "注册资料已自动取得，正在按已声明的接口发现功能和可评价项目。", candidate_key=key)
    capabilities, samples, limitations = collect_protocol_evaluation(registration, evidence)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "VERIFYING",
        "正在核对实际协议响应、逐功能证据及未覆盖项目；资料发现不直接作为业务通过。")
    _save(run / "registration-summary.json", registration)
    finished = datetime.now(timezone.utc)
    inputs = dict(evidence.inputs)
    for name in ("configs/generic-rpc.json", "docs/adr/0010-service-contract-policy.md"):
        inputs[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    for path in run.iterdir():
        if path.is_file():
            inputs[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = EvaluationReport(
        policy_version=SERVICE_CONTRACT_POLICY_VERSION, candidate_key=key,
        name=registration["name"], registration_reference=canonical, generated_at=finished,
        scope="公开注册资料与已声明协议接口：自动发现、访问体验及逐功能证据覆盖",
        scope_exclusions=["仅协议发现不代表具体业务已正确完成", "未实际调用的功能及未绑定的交易不作通过判断"],
        evaluation_window=f"{started.isoformat()} 至 {finished.isoformat()}",
        approach="由注册身份自动采集资料，按协议复用发现与核验规则；分别记录已有证据和缺项，无需逐对象开发。",
        samples=samples, capabilities=capabilities,
        source_references=sorted(inputs),
        limitations=list(dict.fromkeys([*registration["limitations"], *limitations,
            "当前通用接入已支持注册与协议发现；具体业务调用和任务交易核验尚待适用证据适配器接入。"])),
    )
    _save(run / "report.json", report.model_dump(mode="json"))
    with (run / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(render_evaluation_report(report))
    _save(run / "manifest.json", {
        "schema_version": "generic-report-manifest-v1", "started_at": started.isoformat(),
        "completed_at": finished.isoformat(), "policy_version": SERVICE_CONTRACT_POLICY_VERSION,
        "inputs": [{"path": name, "sha256": digest} for name, digest in sorted(inputs.items())],
        "outputs": [{"path": (run / name).relative_to(root).as_posix(),
            "sha256": hashlib.sha256((run / name).read_bytes()).hexdigest()}
            for name in ("report.json", "report.html")],
        "model_calls": 0, "mainnet_writes": False,
    })
    verify_generic_report_sources(root, report, inputs)
    repo.set_job_stage(job["id"], worker, job["fencing_token"], "REPORTING",
        "自动检查已完成，正在发布报告；每项功能的实际覆盖和缺项会分别说明。")
    repo.finalize_job(job["id"], worker, job["fencing_token"], status="COMPLETE",
        candidate_key=key, report_directory=run,
        message="本次自动接入已完成。报告列出已取得的注册与接口证据、实际采样和逐功能缺项；证据不足的维度不计算分数。")
