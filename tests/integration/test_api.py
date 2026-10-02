import pytest
from fastapi.testclient import TestClient
from reputation_platform.api.app import create_app
from reputation_platform.infrastructure.db.tables import audit_logs
from sqlalchemy import select

from tests.factories import agent

pytestmark = pytest.mark.postgres
TOKEN = "test-only-token-" + "x" * 40


def test_health_auth_and_unverified_registration(db):
    with TestClient(create_app(db, TOKEN)) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").status_code == 200
        body = {"agent_ref": agent().model_dump()}
        denied = client.post("/api/v1/agents", json=body)
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "AUTH_REQUIRED"
        assert "x-request-id" in denied.headers
        auth = {"Authorization": "Bearer " + TOKEN}
        created = client.post("/api/v1/agents", json=body, headers=auth)
        assert created.status_code == 201
        assert created.json()["status"] == "UNVERIFIED"
        repeated = client.post("/api/v1/agents", json=body, headers=auth)
        assert repeated.status_code == 200 and repeated.json()["id"] == created.json()["id"]
        result = client.get("/api/v1/agents/" + created.json()["id"])
        assert result.json()["agent_ref"]["agent_id"] == agent().agent_id
    with db.connect() as connection:
        assert len(connection.execute(select(audit_logs)).all()) == 2


def test_error_responses_do_not_echo_secrets_or_private_paths(db):
    with TestClient(create_app(db, TOKEN)) as client:
        response = client.post(
            "/api/v1/agents",
            headers={"Authorization": "Bearer " + TOKEN},
            json={"agent_ref": {"secret": TOKEN}},
        )
        assert response.status_code == 422
        assert TOKEN not in response.text
        assert "Traceback" not in response.text
        bad_token = client.post(
            "/api/v1/agents",
            json={"agent_ref": agent().model_dump()},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert bad_token.status_code == 401 and "wrong-secret" not in bad_token.text
        non_ascii_token = client.post(
            "/api/v1/agents", json={"agent_ref": agent().model_dump()},
            headers={b"Authorization": b"Bearer \xff"},
        )
        assert non_ascii_token.status_code == 401


def test_api_requires_generated_operator_token(db):
    with pytest.raises(RuntimeError, match="OPERATOR_TOKEN"):
        create_app(db, "short")
