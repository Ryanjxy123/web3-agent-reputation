"""M0 authenticated registration and health; later routes reuse these boundaries."""

import hmac
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from reputation_core.models import AgentCreate, AgentView, ApiError, ErrorDetail, JobView
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from reputation_platform.infrastructure.db.connection import engine
from reputation_platform.infrastructure.db.tables import agents, audit_logs, jobs

SCHEMA_HEAD = "6aa7efd8cbc4"


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def create_app(db: Engine | None = None, operator_token: str | None = None) -> FastAPI:
    token = operator_token or os.environ.get("OPERATOR_TOKEN")
    if not token or len(token) < 32:
        raise RuntimeError("OPERATOR_TOKEN must contain at least 32 characters")
    database = db or engine()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if db is None:
            database.dispose()

    app = FastAPI(title="Web3 Agent Reputation", version="1.0.0", lifespan=lifespan)
    app.state.db = database

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

    def operator(auth: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))) -> str:
        supplied = auth.credentials if auth else ""
        if (
            not auth
            or auth.scheme.lower() != "bearer"
            or not hmac.compare_digest(supplied, token)
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

    @app.post("/api/v1/agents", response_model=AgentView, responses={201: {"model": AgentView}, 401: {"model": ApiError}, 422: {"model": ApiError}})
    def add_agent(body: AgentCreate, response: Response, actor: str = Depends(operator)):
        ref = body.agent_ref.model_dump()
        with database.begin() as connection:
            new_id = connection.execute(
                insert(agents)
                .values(**ref, source_type="public_registry")
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
        return AgentView(id=new_id, agent_ref=body.agent_ref, source_type="public_registry")

    @app.get("/api/v1/agents/{agent_id}", response_model=AgentView)
    def get_agent(agent_id: UUID):
        with database.connect() as connection:
            row = (
                connection.execute(select(agents).where(agents.c.id == agent_id)).mappings().first()
            )
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Agent does not exist.")
        return {
            "id": str(row["id"]),
            "agent_ref": {
                key: row[key] for key in ("namespace", "chain_id", "registry_address", "agent_id")
            },
            "source_type": row["source_type"],
            "status": "UNVERIFIED",
        }

    @app.get("/api/v1/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: UUID, actor: str = Depends(operator)):
        with database.connect() as connection:
            row = (
                connection.execute(
                    select(jobs.c.id, jobs.c.state, jobs.c.last_error).where(jobs.c.id == job_id)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Job does not exist.")
        return {"id": str(row["id"]), "state": row["state"], "reason_code": row["last_error"]}

    return app
