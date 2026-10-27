"""One clean-checkout smoke using real PostgreSQL, HTTP and a public-off worker."""

import http.client
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Barrier
import time
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict

from reputation_platform.db import LeaseLostError, Repository
from public_reports import restore_package


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "eip155:1:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:26345"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def request(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
                           headers={"Content-Type": "application/json"} if body is not None else {})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def main() -> int:
    dsn = os.environ.get("REPUTATION_DATABASE_URL")
    require(bool(dsn), "Set the isolated CI database through REPUTATION_DATABASE_URL")
    connection_options = conninfo_to_dict(dsn)
    require(connection_options.get("dbname") == "reputation_ci"
            and connection_options.get("host") in {"127.0.0.1", "localhost"},
            "This smoke only permits a loopback reputation_ci database")
    require(not (ROOT / "runtime/platform-config/profiles.json").exists(),
            "Use a clean checkout without private worker profiles")
    with psycopg.connect(dsn) as connection:
        require(connection.info.server_version == 170011, "PostgreSQL 17.11 is required")
        require(connection.execute("SELECT to_regclass('public.agents')").fetchone()[0] is None,
                "The CI database must be fresh; existing data will not be reset")
    repository = Repository(dsn)
    repository.initialize()
    require(repository.list_agents() == [], "The initialized directory must be empty")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "reputation_platform.api:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            require(server.poll() is None, "The smoke API process exited during startup")
            try:
                status, health = request(port, "GET", "/api/health")
                if status == 200:
                    require(health == {"status": "ok", "database": "ready"}, "Unexpected API health payload")
                    break
            except (OSError, http.client.HTTPException):
                pass
            require(time.monotonic() < deadline, "The smoke API was not ready within 15 seconds")
            time.sleep(0.25)
        status, agents = request(port, "GET", "/api/agents")
        require(status == 200 and agents == [], "A clean API must return an empty directory")
        status, _ = request(port, "POST", "/api/evaluations", {"reference": "   "})
        require(status == 422, "A blank evaluation reference must be rejected with HTTP 422")
        status, created = request(port, "POST", "/api/evaluations", {"reference": CANONICAL})
        require(status == 202 and created["status"] == "QUEUED", "A canonical submission must queue with HTTP 202")
        job_id = str(UUID(created["id"]))
        subprocess.run([sys.executable, "-m", "reputation_platform.worker", "--once"],
                       cwd=ROOT, check=True, timeout=30)
        status, job = request(port, "GET", "/api/jobs/" + job_id)
        require(status == 200 and job["status"] == "NEEDS_INFO" and job["stage"] == "DONE"
                and job["report_id"] is None,
                "The default public-off worker must finish NEEDS_INFO without a report")
        status, agents = request(port, "GET", "/api/agents")
        require(status == 200 and agents == [], "Public-off submission must not invent an Agent record")
        with psycopg.connect(dsn) as connection:
            require(connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0,
                    "Public-off operation must not create a report")
            rows = connection.execute(
                "SELECT id,status,fencing_token,lease_owner,lease_until FROM evaluation_jobs"
            ).fetchall()
            require(len(rows) == 1 and str(rows[0][0]) == job_id and rows[0][1] == "NEEDS_INFO"
                    and rows[0][2] == 1 and rows[0][3] is None and rows[0][4] is None,
                    "Exactly one real worker claim must finish and release its lease")

        # Real competing connections, an expired lease and a rejected stale worker.
        queued = repository.create_job(CANONICAL)
        require(repository.create_job(CANONICAL.removeprefix('eip155:')).id == queued.id,
                "Equivalent active submissions must share one job")
        barrier = Barrier(3)

        def claim(index):
            barrier.wait(timeout=10)
            return repository.claim_job(f'ci-claim-{index}')

        with ThreadPoolExecutor(max_workers=3) as pool:
            claimed = [row for row in pool.map(claim, range(3)) if row is not None]
        require(len(claimed) == 1 and claimed[0]['id'] == queued.id,
                'Exactly one concurrent PostgreSQL claimant may acquire the job')
        previous = claimed[0]
        with psycopg.connect(dsn) as connection:
            connection.execute("UPDATE evaluation_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                               (UUID(queued.id),))
        recovered = repository.claim_job('ci-recovery')
        require(recovered is not None and recovered['id'] == queued.id
                and recovered['fencing_token'] == previous['fencing_token'] + 1,
                'An expired lease must be reclaimed with a new fencing token')
        for operation in (
            lambda: repository.renew_job(queued.id, previous['lease_owner'], previous['fencing_token']),
            lambda: repository.finalize_job(queued.id, previous['lease_owner'], previous['fencing_token'],
                                           status='NEEDS_INFO', message='Stale worker must not finish'),
        ):
            try:
                operation()
            except LeaseLostError:
                pass
            else:
                raise RuntimeError('The expired worker unexpectedly retained write access')
        repository.finalize_job(queued.id, recovered['lease_owner'], recovered['fencing_token'],
                                status='NEEDS_INFO', message='CI is public-off; no business execution')

        # Only the selected MangoSwap publication is inserted; parents stay evidence attachments.
        restored = restore_package(ROOT, ROOT / 'data/public-reports-single-score-v3.tar.gz', True, False)
        require(restored['reports'] == 1 and restored['mapping'][0]['canonical'] == CANONICAL,
                'The sole default publication must be the registered MangoSwap identity')
        report_id = restored['mapping'][0]['imported_report_id']
        status, agents = request(port, 'GET', '/api/agents')
        require(status == 200 and len(agents) == 1 and agents[0]['key'] == 'mangoswap-26345',
                'The imported directory must contain exactly one MangoSwap identity')
        status, report = request(port, 'GET', '/api/reports/' + report_id)
        require(status == 200 and report['policy_version'] == 'transaction-agent-evidence-v3'
                and report['shared_assessment']['result']['task_count'] == 34
                and report['scores']['overall'] is not None,
                'The real API must return the verified single-score, 34-task publication')
        for statement in ('UPDATE reports SET source_directory=source_directory WHERE id=%s',
                          'DELETE FROM reports WHERE id=%s'):
            try:
                with psycopg.connect(dsn) as connection:
                    connection.execute(statement, (UUID(report_id),))
            except psycopg.Error as error:
                require(error.sqlstate == '55000', 'Unexpected report immutability failure')
            else:
                raise RuntimeError('A published report was unexpectedly mutable')
        require(repository.get_report(report_id).policy_version == 'transaction-agent-evidence-v3',
                'Rejected writes must leave the publication intact')
        print(json.dumps({"status": "PASS", "database": "PostgreSQL 17.11", "http": "real loopback uvicorn",
            "invalid_submission": 422, "canonical_submission": 202, "job_status": "NEEDS_INFO",
            "concurrent_claimants": 3, "lease_recovery": True, "stale_worker_rejected": True,
            "agents": 1, "reports": 1, "report_policy": "transaction-agent-evidence-v3",
            "public_readonly_enabled": False, "model_calls": 0}))
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
