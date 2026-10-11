"""Run five actual free Akashi queries through API, Worker, PostgreSQL and Bundle replay."""

import argparse
import asyncio
import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from reputation_core.evidence import canonical_bytes, strict_json
from reputation_platform.adapters.registries.erc8004 import AKASHI_REF, Erc8004RegistryReader
from reputation_platform.api.app import create_app
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.connection import database_url, engine
from reputation_platform.infrastructure.db.tables import jobs
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.operator_dns import operator_dot_resolver
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from reputation_verifier.bundle import verify_bundle
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def checked(response, status=200):
    if response.status_code != status:
        # API errors have static, sanitized messages; never print headers or credentials.
        raise RuntimeError(f"PUBLIC_API_{response.status_code}: {response.text}")
    return response.json()


def source_manifest():
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        .decode()
        .splitlines()
    )
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in names
        if name.endswith((".py", ".toml")) and not name.startswith("runtime/")
    }


def save_network_audit(output: Path):
    responses = []
    for path in sorted((output / "blobs").glob("*.bin")):
        saved = strict_json(path.read_bytes())
        if (
            isinstance(saved, dict)
            and "origin" in saved
            and ("response" in saved or "error" in saved)
        ):
            responses.append(saved)
    (output / "network-audit.json").write_bytes(canonical_bytes({"responses": responses}))
    return responses


async def accept(output: Path, *, dns_over_tls: bool = False):
    if os.environ.get("PUBLIC_READONLY_ENABLED") != "1":
        raise RuntimeError("Set PUBLIC_READONLY_ENABLED=1 explicitly before running acceptance")
    token = os.environ.get("OPERATOR_TOKEN")
    if not token or len(token) < 32:
        raise RuntimeError("A configured local OPERATOR_TOKEN is required")
    configured = make_url(database_url())
    if configured.host not in {"127.0.0.1", "localhost", "::1", "postgres"}:
        raise RuntimeError("Acceptance creates a dedicated database on local PostgreSQL only")
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-manifest.json").write_bytes(canonical_bytes(source_manifest()))
    name = "reputation_public_" + uuid4().hex
    admin = create_engine(
        configured.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
    )
    database = None
    client = None
    original_url = os.environ.get("DATABASE_URL")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        (output / "run-context.json").write_bytes(
            canonical_bytes(
                {
                    "database_name": name,
                    "scope": "task10-local-isolated-acceptance",
                    "created_at": datetime.now(UTC).isoformat(),
                    "database_retained": True,
                }
            )
        )
        isolated_url = configured.set(database=name).render_as_string(hide_password=False)
        os.environ["DATABASE_URL"] = isolated_url
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        database = engine(isolated_url)
        resolver = operator_dot_resolver(output / "dns") if dns_over_tls else None

        def public_client(**kwargs):
            return SafeHttpClient.public_readonly(resolver=resolver, **kwargs)

        app = create_app(database, token)
        identity = app.state.identity
        identity.evidence = EvidenceStore(output)
        client = public_client(enabled=True)
        identity._public_reader = Erc8004RegistryReader(ROOT, client, identity.evidence)
        execution = ExecutionService(database, identity, client_factory=public_client)
        verification = VerificationService(database, identity, client_factory=public_client)
        reporting = ReportService(database, identity, client_factory=public_client)
        worker = Worker(
            database,
            {
                "ingest": identity.ingest,
                "evaluate": execution.execute,
                "verify": verification.verify,
                "report": reporting.freeze,
            },
        )
        headers = {"Authorization": "Bearer " + token}
        with TestClient(app) as api:
            checked(api.get("/health/ready"))
            added = api.post(
                "/api/v1/agents", json={"agent_ref": AKASHI_REF.model_dump()}, headers=headers
            )
            agent = checked(added, 201)
            refresh = checked(
                api.post(
                    f"/api/v1/agents/{agent['id']}/refresh",
                    json={},
                    headers=headers,
                ),
                202,
            )
            assert await worker.run_once(), "Public ingest was not queued"
            job = checked(api.get(f"/api/v1/jobs/{refresh['job_id']}", headers=headers))
            assert job["state"] == "SUCCEEDED" and job["snapshot_id"], job
            snapshot_id = job["snapshot_id"]
            snapshot = checked(api.get(f"/api/v1/snapshots/{snapshot_id}"))
            associations = [
                checked(
                    api.get(
                        f"/api/v1/snapshots/{snapshot_id}/readonly-association",
                        params={"protocol": protocol},
                    )
                )
                for protocol in ("akashi-http-readonly-v1", "akashi-mcp-readonly-v1")
            ]
            review = checked(
                api.post(
                    f"/api/v1/snapshots/{snapshot_id}/claims/confirm",
                    json={
                        "confirmed_claims": ["verify_record"],
                        "expected_review_version": 0,
                        "reason": "Operator-reviewed fixed free historical proof query; executor control UNKNOWN.",
                    },
                    headers=headers,
                )
            )
            expires = (
                (datetime.now(UTC) + timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            grants = [
                checked(
                    api.post(
                        "/api/v1/public-readonly/access-grants",
                        json={
                            "snapshot_id": snapshot_id,
                            "endpoint_id": endpoint,
                            "max_tasks": count,
                            "interval_ms": 1000,
                            "expires_at": expires,
                            "consent_ref": "task10-operator-authorized-free-readonly-acceptance",
                        },
                        headers=headers,
                    ),
                    201,
                )
                for endpoint, count in (("akashi-http", 4), ("akashi-mcp", 1))
            ]
            accepted = checked(
                api.post(
                    "/api/v1/public-readonly/evaluations",
                    json={
                        "snapshot_id": snapshot_id,
                        "review_version": review["review_version"],
                        "grant_ids": [view["grant"]["grant_id"] for view in grants],
                    },
                    headers={**headers, "Idempotency-Key": "task10-public-" + uuid4().hex},
                ),
                202,
            )
            run_id = accepted["run_id"]
            (output / "progress.json").write_bytes(
                canonical_bytes({"run_id": run_id, "stage": "QUEUED"})
            )
            for phase in ("evaluate", "verify", "report"):
                assert await worker.run_once(), f"Formal {phase} job was not queued"
                with database.connect() as connection:
                    state, error = connection.execute(
                        select(jobs.c.state, jobs.c.last_error).where(
                            jobs.c.kind == phase,
                            jobs.c.run_fk == UUID(run_id),
                        )
                    ).one()
                (output / "progress.json").write_bytes(
                    canonical_bytes(
                        {
                            "run_id": run_id,
                            "stage": phase,
                            "job_state": state,
                            "reason_code": error,
                        }
                    )
                )
                assert state == "SUCCEEDED", (phase, state, error)
                print("PUBLIC_WORKER_PHASE_COMPLETED:", phase, flush=True)
            run = checked(api.get(f"/api/v1/evaluations/{run_id}"))
            report = checked(api.get(f"/api/v1/evaluations/{run_id}/report"))
            archive = reporting.export(UUID(report["report_id"]))
            bundle = output / "public-readonly-bundle.zip"
            bundle.write_bytes(archive)
            replay = verify_bundle(str(bundle))
            observations = checked(api.get(f"/api/v1/evaluations/{run_id}/observations"))
            result = {
                "scope": "task10-formal-public-readonly-evaluation",
                "database_name": name,
                "snapshot": snapshot,
                "associations": associations,
                "review": review,
                "grants": grants,
                "run": run,
                "plan": checked(api.get(f"/api/v1/evaluations/{run_id}/plan")),
                "observations": observations,
                "verification": checked(api.get(f"/api/v1/evaluations/{run_id}/verification")),
                "report": report,
                "independent_verifier": replay,
                "payments": 0,
                "signatures": 0,
                "mainnet_writes": 0,
                "dns_source": "operator-fixed-dns-over-tls" if dns_over_tls else "system",
            }
            (output / "acceptance.json").write_bytes(canonical_bytes(result))
            core = report["core"]
            assert core["schema_version"] == "1.6.0"
            assert core["scores"]["evaluation_state"] == "PARTIAL"
            assert core["scores"]["overall_score_bp"] is None
            assert len(core["task_results"]) == 5 and core["task_counts"] == {
                "PASS": 4,
                "FAIL": 0,
                "UNKNOWN": 1,
                "NOT_APPLICABLE": 0,
            }, core["task_counts"]
            assert all(item["executor_outcome"] == "UNKNOWN" for item in associations)
            # Direct raw audit supplements deterministic Bundle replay with actual call inventory.
            responses = save_network_audit(output)
            assert not any(
                item.get("response", {}).get("audit", {}).get("payment_required")
                for item in responses
            )
            print(
                "PUBLIC_EVALUATION_SMOKE_PASS: 5 real queries; PARTIAL/overall=null; executor UNKNOWN; Bundle replay passed",
                flush=True,
            )
    finally:
        save_network_audit(output)
        if client is not None:
            await client.close()
        if database is not None:
            database.dispose()
        admin.dispose()
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        # Keep this uniquely created database and all evidence for recovery and review.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-readonly", action="store_true", required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory; refuses overwrite"
    )
    parser.add_argument(
        "--operator-dns-over-tls",
        action="store_true",
        help="Explicit fixed dns.google TLS resolver; retain DNS wire audit",
    )
    args = parser.parse_args()
    asyncio.run(accept(args.output.resolve(), dns_over_tls=args.operator_dns_over_tls))


if __name__ == "__main__":
    main()
