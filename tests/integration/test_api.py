from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reputation_platform.api.app import create_app
from reputation_platform.infrastructure.db.tables import agents, audit_logs
from sqlalchemy import insert, select

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
        listed = client.get("/api/v1/agents")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
        assert listed.json()["next_cursor"] is None
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


def test_controlled_identity_retains_its_source_label(db):
    with db.begin() as connection:
        identifier = connection.execute(
            insert(agents).values(**agent().model_dump(), source_type="controlled")
            .returning(agents.c.id)
        ).scalar_one()
    with TestClient(create_app(db, TOKEN)) as client:
        response = client.get(f"/api/v1/agents/{identifier}")
    assert response.status_code == 200
    assert response.json()["source_type"] == "controlled"


def test_agent_pages_are_bounded_and_have_no_overlap(db):
    with TestClient(create_app(db, TOKEN)) as client:
        for number in range(1, 4):
            ref = agent().model_dump() | {"agent_id": str(number)}
            assert client.post("/api/v1/agents", json={"agent_ref": ref}, headers={
                "Authorization": "Bearer " + TOKEN
            }).status_code == 201
        first = client.get("/api/v1/agents?limit=2").json()
        assert len(first["items"]) == 2 and first["next_cursor"] == first["items"][-1]["id"]
        second = client.get("/api/v1/agents", params={"limit": 2, "cursor": first["next_cursor"]}).json()
        assert len(second["items"]) == 1 and second["next_cursor"] is None
        assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
        assert client.get("/api/v1/agents?limit=101").status_code == 422
        assert client.get("/api/v1/agents?limit=0").status_code == 422
        assert client.get("/api/v1/agents", params={"cursor": str(uuid4())}).status_code == 404
