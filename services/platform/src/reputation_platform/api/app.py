"""Authenticated operator routes; identity reads and writes use application services."""

import hmac
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from reputation_core.models import (
    AcceptedEvaluation,
    AcceptedJob,
    AccessGrantCreate,
    AgentCreate,
    AgentSnapshot,
    AgentView,
    ApiError,
    BindingChallengeRequest,
    BindingChallengeView,
    BindingVerifyRequest,
    ClaimReview,
    ClaimsConfirm,
    ErrorDetail,
    EvaluationCreate,
    EvaluationRun,
    ExecutorBinding,
    GrantView,
    JobView,
    LocalDeployment,
    Observation,
    ReasonRequest,
    RecordVerificationResult,
    RefreshRequest,
    ReportView,
    RunPlan,
)
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from reputation_platform.application.anchor import AnchorService
from reputation_platform.application.errors import ApplicationError as ApiProblem
from reputation_platform.application.evaluations import EvaluationService
from reputation_platform.application.identity import IdentityService
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.connection import engine
from reputation_platform.infrastructure.db.tables import agents, audit_logs, jobs

SCHEMA_HEAD = "6aa7efd8cbc4"


def create_app(
    db: Engine | None = None,
    operator_token: str | None = None,
    deployment: LocalDeployment | None = None,
) -> FastAPI:
    token = operator_token or os.environ.get("OPERATOR_TOKEN")
    if not token or len(token) < 32:
        raise RuntimeError("OPERATOR_TOKEN must contain at least 32 characters")
    database = db or engine()
    identity = IdentityService(database, deployment)
    evaluations = EvaluationService(database, identity)
    verification = VerificationService(database, identity)
    reporting = ReportService(database, identity)
    anchoring = AnchorService(database, identity)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if db is None:
            database.dispose()

    app = FastAPI(title="Web3 Agent Reputation", version="1.0.0", lifespan=lifespan)
    app.state.db = database
    app.state.identity = identity
    app.state.evaluations = evaluations

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response

    def error_response(request: Request, status: int, code: str, message: str, retryable=False):
        error = ApiError(
            error=ErrorDetail(
                code=code, message=message, request_id=request.state.request_id, retryable=retryable
            )
        )
        return JSONResponse(error.model_dump(mode="json"), status_code=status)

    @app.exception_handler(ApiProblem)
    async def problem(request: Request, exc: ApiProblem):
        return error_response(request, exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        return error_response(
            request, 422, "SCHEMA_ERROR", "Request does not match the API schema."
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request: Request, exc: SQLAlchemyError):
        return error_response(
            request, 503, "DATABASE_UNAVAILABLE", "Database operation unavailable.", True
        )

    def operator(
        auth: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    ) -> str:
        supplied = auth.credentials if auth else ""
        if (
            not auth
            or auth.scheme.lower() != "bearer"
            or not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))
        ):
            raise ApiProblem(401, "AUTH_REQUIRED", "Operator authentication required.")
        return "local-operator"

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with database.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        if revision != SCHEMA_HEAD:
            raise ApiProblem(503, "MIGRATION_REQUIRED", "Database schema is not current.", True)
        return {"status": "ok", "database": "ready", "schema_revision": revision}

    @app.post(
        "/api/v1/agents",
        response_model=AgentView,
        responses={201: {"model": AgentView}, 401: {"model": ApiError}, 422: {"model": ApiError}},
    )
    def add_agent(body: AgentCreate, response: Response, actor: str = Depends(operator)):
        ref = body.agent_ref.model_dump()
        with database.begin() as connection:
            new_id = connection.execute(
                insert(agents)
                .values(**ref, source_type=identity.source_type(body.agent_ref))
                .on_conflict_do_nothing(
                    index_elements=["namespace", "chain_id", "registry_address", "agent_id"]
                )
                .returning(agents.c.id)
            ).scalar_one_or_none()
            created = new_id is not None
            if new_id is None:
                new_id = connection.execute(
                    select(agents.c.id).where(
                        *(getattr(agents.c, key) == value for key, value in ref.items())
                    )
                ).scalar_one()
            connection.execute(
                insert(audit_logs).values(
                    actor=actor,
                    action="agent.create" if created else "agent.lookup",
                    target=new_id,
                    body={"agent_ref": ref},
                )
            )
        # Registry reads/confirmation happen separately; registration is never evaluation.
        response.status_code = 201 if created else 200
        return identity.agent(new_id)

    @app.get("/api/v1/agents/{agent_id}", response_model=AgentView)
    def get_agent(agent_id: UUID):
        return identity.agent(agent_id)

    @app.post("/api/v1/agents/{agent_id}/refresh", response_model=AcceptedJob, status_code=202)
    def refresh(agent_id: UUID, body: RefreshRequest, actor: str = Depends(operator)):
        return identity.refresh(agent_id, body, actor)

    @app.get("/api/v1/snapshots/{snapshot_id}", response_model=AgentSnapshot)
    def get_snapshot(snapshot_id: UUID):
        return identity.snapshot(snapshot_id)

    @app.post("/api/v1/snapshots/{snapshot_id}/claims/confirm", response_model=ClaimReview)
    def confirm_claims(snapshot_id: UUID, body: ClaimsConfirm, actor: str = Depends(operator)):
        return identity.confirm(snapshot_id, body, actor)

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/bindings/challenge", response_model=BindingChallengeView
    )
    def binding_challenge(
        snapshot_id: UUID, body: BindingChallengeRequest, actor: str = Depends(operator)
    ):
        return identity.challenge(snapshot_id, body, actor)

    @app.post("/api/v1/snapshots/{snapshot_id}/bindings/verify", response_model=ExecutorBinding)
    def binding_verify(
        snapshot_id: UUID, body: BindingVerifyRequest, actor: str = Depends(operator)
    ):
        return identity.verify(snapshot_id, body, actor)

    @app.get("/api/v1/snapshots/{snapshot_id}/bindings", response_model=list[ExecutorBinding])
    def get_bindings(snapshot_id: UUID):
        return identity.proofs(snapshot_id)

    @app.get("/api/v1/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: UUID, actor: str = Depends(operator)):
        with database.connect() as connection:
            row = (
                connection.execute(
                    select(jobs.c.id, jobs.c.state, jobs.c.last_error, jobs.c.payload).where(
                        jobs.c.id == job_id
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Job does not exist.")
        return {
            "id": str(row["id"]),
            "state": row["state"],
            "reason_code": row["last_error"],
            "snapshot_id": row["payload"].get("snapshot_id"),
        }

    @app.post("/api/v1/access-grants", response_model=GrantView, status_code=201)
    def create_grant(body: AccessGrantCreate, actor: str = Depends(operator)):
        return evaluations.create_grant(body, actor)

    @app.get("/api/v1/access-grants/{grant_id}", response_model=GrantView)
    def get_grant(grant_id: UUID, actor: str = Depends(operator)):
        return evaluations.grant(grant_id)

    @app.post("/api/v1/access-grants/{grant_id}/revoke", response_model=GrantView)
    def revoke_grant(grant_id: UUID, body: ReasonRequest, actor: str = Depends(operator)):
        return evaluations.revoke(grant_id, body.reason, actor)

    @app.post("/api/v1/evaluations", response_model=AcceptedEvaluation, status_code=202)
    def create_evaluation(
        body: EvaluationCreate,
        idempotency_key: str = Header(default=""),
        actor: str = Depends(operator),
    ):
        return evaluations.create(body, idempotency_key, actor)

    @app.get("/api/v1/evaluations/{run_id}", response_model=EvaluationRun)
    def get_evaluation(run_id: UUID):
        return evaluations.view(run_id)

    @app.get("/api/v1/evaluations/{run_id}/observations", response_model=list[Observation])
    def get_observations(run_id: UUID):
        return evaluations.observations(run_id)

    @app.get("/api/v1/evaluations/{run_id}/plan", response_model=RunPlan)
    def get_plan(run_id: UUID):
        return evaluations.row(run_id)["plan"]

    @app.get("/api/v1/evaluations/{run_id}/verification", response_model=RecordVerificationResult)
    def get_verification(run_id: UUID):
        return verification.result(run_id)

    @app.post("/api/v1/evaluations/{run_id}/report", response_model=AcceptedJob, status_code=202)
    def request_report(run_id: UUID, actor: str = Depends(operator)):
        return reporting.request(run_id, actor)

    @app.get("/api/v1/evaluations/{run_id}/report", response_model=ReportView)
    def get_run_report(run_id: UUID):
        return reporting.for_run(run_id)

    @app.get("/api/v1/reports/{report_id}", response_model=ReportView)
    def get_report(report_id: UUID):
        return reporting.view(report_id)

    @app.post("/api/v1/reports/{report_id}/anchor", response_model=AcceptedJob, status_code=202)
    def anchor_report(report_id: UUID, actor: str = Depends(operator)):
        return anchoring.request(report_id, actor)

    @app.post("/api/v1/evaluations/{run_id}/anchor", response_model=AcceptedJob, status_code=202)
    def anchor_run(run_id: UUID, actor: str = Depends(operator)):
        return anchoring.request(reporting.for_run(run_id).report_id, actor)

    @app.get(
        "/api/v1/reports/{report_id}/bundle",
        response_class=Response,
        responses={200: {"content": {"application/zip": {}}}},
    )
    def export_report(report_id: UUID):
        return Response(
            reporting.export(report_id),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="report-{report_id}.zip"'},
        )

    @app.post("/api/v1/evaluations/{run_id}/cancel", response_model=EvaluationRun)
    def cancel_evaluation(run_id: UUID, body: ReasonRequest, actor: str = Depends(operator)):
        return evaluations.cancel(run_id, body.reason, actor)

    return app
