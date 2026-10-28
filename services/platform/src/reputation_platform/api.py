"""Local HTTP application over evidence-backed reports and queued evaluations."""

from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
import psycopg

from reputation_core.application import (
    AgentDetail, AgentSummary, EvaluationJob, EvaluationSubmission, HealthStatus,
)
from reputation_core.reporting import EvaluationReport
from reputation_core.chain_review import AgentChainEvidence
from reputation_core.chain_view import ReportChainEvidence
from reputation_platform.db import EvidenceIntegrityError, Repository
from reputation_platform.settings import PROJECT_ROOT, load_database_url
from reputation_platform.runtime_status import RuntimeStatus, unavailable_runtime


def create_app(repository: Repository | None = None) -> FastAPI:
    repo = repository if repository is not None else Repository(load_database_url())
    app = FastAPI(title="Web3 Agent 声誉评价平台", version="0.1.0")
    app.state.repository = repo

    @app.exception_handler(psycopg.Error)
    async def database_unavailable(request: Request, error: psycopg.Error):
        return JSONResponse(status_code=503, content={"detail": "本地数据库暂不可用。"})

    @app.exception_handler(EvidenceIntegrityError)
    async def evidence_changed(request: Request, error: EvidenceIntegrityError):
        return JSONResponse(status_code=409, content={"detail": "保留证据未通过完整性校验。"})

    @app.get("/api/health", response_model=HealthStatus)
    def health():
        if not repo.health():
            raise HTTPException(status_code=503, detail="本地数据库暂不可用。")
        return HealthStatus(status="ok", database="ready")

    @app.get("/api/agents", response_model=list[AgentSummary])
    def list_agents():
        return repo.list_agents()

    @app.get('/api/runtime', response_model=RuntimeStatus)
    def runtime():
        try:
            return repo.runtime_status()
        except psycopg.Error:
            return unavailable_runtime()

    @app.get("/api/agents/{key}", response_model=AgentDetail)
    def get_agent(key: str):
        agent = repo.get_agent(key)
        if agent is None:
            raise HTTPException(status_code=404, detail="没有找到该 Agent。")
        return agent

    @app.get("/api/reports/{report_id}", response_model=EvaluationReport)
    def get_report(report_id: UUID):
        report = repo.get_report(str(report_id))
        if report is None:
            raise HTTPException(status_code=404, detail="没有找到该报告。")
        return report

    @app.get('/api/reports/{report_id}/chain-evidence', response_model=ReportChainEvidence)
    def report_chain_evidence(report_id: UUID, task_key: str | None = Query(default=None, min_length=1, max_length=200)):
        view = repo.report_chain_evidence(str(report_id), task_key)
        if view is None:
            raise HTTPException(status_code=404, detail='没有找到该报告。')
        return view

    @app.get('/api/agents/{key}/chain-evidence', response_model=AgentChainEvidence | None)
    def agent_chain_evidence(key: str):
        if repo.get_agent(key) is None:
            raise HTTPException(status_code=404, detail='没有找到该Agent。')
        return repo.agent_chain_evidence(key)

    @app.get('/api/agents/{key}/chain-evidence/file', response_class=FileResponse)
    def agent_chain_file(key: str, path: str = Query(min_length=1)):
        evidence = repo.agent_chain_evidence_file(key, path)
        if evidence is None:
            raise HTTPException(status_code=404, detail='该Agent快照没有引用此证据。')
        return FileResponse(evidence, media_type='application/octet-stream', filename=evidence.name)

    @app.get("/api/reports/{report_id}/evidence", response_class=FileResponse)
    def get_evidence(report_id: UUID, path: str = Query(min_length=1)):
        evidence = repo.evidence_file(str(report_id), path)
        if evidence is None:
            raise HTTPException(status_code=404, detail="该报告没有引用此证据。")
        return FileResponse(evidence, media_type="application/octet-stream", filename=evidence.name)

    @app.post("/api/evaluations", response_model=EvaluationJob, status_code=status.HTTP_202_ACCEPTED)
    def submit_evaluation(submission: EvaluationSubmission):
        if not submission.reference.strip():
            raise HTTPException(status_code=422, detail="请输入 Agent 的公开注册标识。")
        return repo.create_job(submission.reference)

    @app.get("/api/jobs/{job_id}", response_model=EvaluationJob)
    def get_job(job_id: UUID):
        job = repo.get_job(str(job_id))
        if job is None:
            raise HTTPException(status_code=404, detail="没有找到该评价任务。")
        return job

    dist = PROJECT_ROOT / "apps/web/dist"
    if (dist / "index.html").is_file():
        @app.get("/{path:path}", include_in_schema=False)
        def web(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="没有找到该接口。")
            requested = (dist / path).resolve()
            if not requested.is_relative_to(dist.resolve()):
                raise HTTPException(status_code=404)
            if requested.is_file():
                return FileResponse(requested)
            if Path(path).suffix:
                raise HTTPException(status_code=404)
            return FileResponse(dist / "index.html")

    return app
