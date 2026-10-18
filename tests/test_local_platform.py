"""One real PostgreSQL/API acceptance case; never targets the user database."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from threading import Barrier
import unittest
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.conninfo import conninfo_to_dict

from reputation_platform.api import create_app
from reputation_platform.db import LeaseLostError, Repository
from reputation_platform.settings import PROJECT_ROOT


class LocalPlatformIntegrationTests(unittest.TestCase):
    def test_real_report_integrity_leases_and_http(self) -> None:
        configuration = os.environ.get("REPUTATION_TEST_DATABASE_URL_FILE")
        if not configuration or not Path(configuration).is_file():
            raise RuntimeError("NOT_RUN: set REPUTATION_TEST_DATABASE_URL_FILE to the isolated verification database file")
        dsn = Path(configuration).read_text(encoding="utf-8").strip()
        try:
            database_name = conninfo_to_dict(dsn).get("dbname")
        except psycopg.Error:
            raise RuntimeError("NOT_RUN: invalid private verification database configuration") from None
        if database_name != "reputation_verification":
            raise RuntimeError("NOT_RUN: this acceptance case only permits reputation_verification")

        repository = Repository(dsn)
        with psycopg.connect(dsn) as connection:
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0], "reputation_verification")
        repository.initialize()
        with psycopg.connect(dsn) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM evaluation_jobs").fetchone()[0], 0,
                             "Use the dedicated fresh verification database; this case never deletes existing jobs")

        report_directory = PROJECT_ROOT / "runtime/evaluation-report-20261018T053613Z-fe5237bc"
        original = json.loads((report_directory / "report.json").read_bytes())
        self.assertEqual(repository.import_candidates(
            PROJECT_ROOT / "runtime/admission-report-20261017T182038Z-f504c54e"), 5)
        imported = repository.import_report(report_directory)
        self.assertEqual(imported.scores.model_dump(mode="json"), original["scores"])
        self.assertEqual(len(repository.list_agents()), 5)
        candidate_key = imported.candidate_key
        baseline = repository.get_agent(candidate_key)
        self.assertIsNotNone(baseline)
        self.assertTrue(baseline.agent.registration_reference.startswith("eip155:56:"))

        for statement in (
            "UPDATE reports SET source_directory=source_directory WHERE id=%s",
            "DELETE FROM reports WHERE id=%s",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(psycopg.Error) as rejected:
                    with psycopg.connect(dsn) as connection:
                        connection.execute(statement, (UUID(imported.id),))
                self.assertEqual(rejected.exception.sqlstate, "55000")
        self.assertEqual(repository.get_report(imported.id).scope, original["scope"])

        reference = baseline.agent.registration_reference
        job = repository.create_job(reference)
        equivalent = repository.create_job(reference.removeprefix("eip155:"))
        self.assertEqual(job.id, equivalent.id)
        barrier = Barrier(3)

        def claim(index: int):
            barrier.wait(timeout=10)
            return repository.claim_job(f"verification-worker-{index}")

        with ThreadPoolExecutor(max_workers=3) as pool:
            claims = list(pool.map(claim, range(3)))
        acquired = [result for result in claims if result is not None]
        self.assertEqual(len(acquired), 1)
        previous = acquired[0]
        self.assertEqual(previous["id"], job.id)
        repository.set_job_stage(job.id, previous["lease_owner"], previous["fencing_token"],
                                 "VERIFYING", "独立验收：核对租约与资料不足路径。", candidate_key=candidate_key)
        with psycopg.connect(dsn) as connection:
            connection.execute("UPDATE evaluation_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                               (UUID(job.id),))
        reclaimed = repository.claim_job("verification-recovery")
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed["id"], job.id)
        self.assertEqual(reclaimed["fencing_token"], previous["fencing_token"] + 1)
        with self.assertRaises(LeaseLostError):
            repository.renew_job(job.id, previous["lease_owner"], previous["fencing_token"])
        with self.assertRaises(LeaseLostError):
            repository.finalize_job(job.id, previous["lease_owner"], previous["fencing_token"],
                                    status="NEEDS_INFO", message="过期 worker 不得提交。")
        finished = repository.finalize_job(job.id, reclaimed["lease_owner"], reclaimed["fencing_token"],
            status="NEEDS_INFO", message="本用例不采集外网资料，保留已有报告与分数。", candidate_key=candidate_key)
        self.assertEqual(finished.status, "NEEDS_INFO")
        self.assertIsNone(finished.report_id)
        self.assertEqual(repository.get_agent(candidate_key).agent, baseline.agent)

        with TestClient(create_app(repository)) as client:
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json(), {"status": "ok", "database": "ready"})
            agents = client.get("/api/agents")
            self.assertEqual(agents.status_code, 200)
            self.assertEqual(len(agents.json()), 5)
            detail = client.get(f"/api/agents/{quote(candidate_key, safe='')}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["agent"]["latest_report"]["id"], imported.id)
            report_response = client.get(f"/api/reports/{imported.id}")
            self.assertEqual(report_response.status_code, 200)
            self.assertEqual(report_response.json()["scope"], original["scope"])
            self.assertEqual(report_response.json()["scores"], original["scores"])
            self.assertEqual(client.get(f"/api/jobs/{job.id}").json()["status"], "NEEDS_INFO")

            for path in ("/api/reports/not-a-uuid", "/api/jobs/not-a-uuid"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 422)
            for path in (f"/api/reports/{uuid4()}", f"/api/jobs/{uuid4()}", "/api/unknown-route"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.post("/api/evaluations", json={}).status_code, 422)

            evidence = next(path for path in original["source_references"]
                            if path.startswith("runtime/") and path.endswith(".response.bin"))
            downloaded = client.get(f"/api/reports/{imported.id}/evidence", params={"path": evidence})
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.headers["content-type"], "application/octet-stream")
            self.assertTrue(downloaded.headers["content-disposition"].startswith("attachment;"))
            self.assertEqual(hashlib.sha256(downloaded.content).hexdigest(),
                             hashlib.sha256((PROJECT_ROOT / evidence).read_bytes()).hexdigest())
            for forbidden in ("runtime/platform-config/database-test-url.txt", "../../AGENTS.md",
                              (report_directory / "report.json").relative_to(PROJECT_ROOT).as_posix()):
                with self.subTest(path=forbidden):
                    response = client.get(f"/api/reports/{imported.id}/evidence", params={"path": forbidden})
                    self.assertEqual(response.status_code, 404)

            unknown_reference = reference.rsplit(":", 1)[0] + ":" + str(uuid4().int)
            submitted = client.post("/api/evaluations", json={"reference": unknown_reference})
            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(submitted.json()["status"], "QUEUED")
            self.assertIsNone(submitted.json()["report_id"])
            self.assertEqual(repository.get_agent(candidate_key).agent, baseline.agent)


if __name__ == "__main__":
    unittest.main()
