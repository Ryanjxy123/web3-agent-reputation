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
from urllib.parse import quote

import psycopg
from psycopg.conninfo import conninfo_to_dict

from reputation_platform.db import LeaseLostError, Repository
from reputation_core.chain_view import _asset, _transfers
from reputation_core.swap import decode_batch
from reputation_platform.unsigned_swap_protocol import decode_unsigned_swap, UnsupportedUnsignedSwap
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

        # Only the two selected publications are inserted; parents stay evidence attachments.
        restored = restore_package(ROOT, ROOT / 'data/public-reports-transaction-v3.tar.gz', True, False)
        require(restored['reports'] == 2 and {item['canonical'] for item in restored['mapping']} == {
            CANONICAL, 'eip155:8453:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:54947'},
            'The current publications must contain the two independently registered identities')
        report_id = next(item['imported_report_id'] for item in restored['mapping'] if item['canonical'] == CANONICAL)
        status, agents = request(port, 'GET', '/api/agents')
        require(status == 200 and {agent['key'] for agent in agents} == {'mangoswap-26345', 'hydrex-routing-54947'},
                'The imported directory must contain exactly the two current publications')
        status, report = request(port, 'GET', '/api/reports/' + report_id)
        require(status == 200 and report['policy_version'] == 'transaction-agent-evidence-v3'
                and report['shared_assessment']['result']['task_count'] == 34
                and report['scores']['overall'] is not None,
                'The real API must return the verified single-score, 34-task publication')
        hydrex_id = next(item['imported_report_id'] for item in restored['mapping'] if item['canonical'] != CANONICAL)
        status, hydrex = request(port, 'GET', '/api/reports/' + hydrex_id)
        require(status == 200 and hydrex['shared_assessment']['result']['task_count'] == 2
                and hydrex['scores']['overall'] == 100, 'The standalone source must replay the two-task Hydrex scope')
        status, chain = request(port, 'GET', '/api/reports/' + hydrex_id + '/chain-evidence')
        default_swaps = [item for item in chain.get('actions', []) if item['action'] == 'swap']
        require(status == 200 and len(default_swaps) == 1,
                'The new publication must explain its real asset exchange')
        origin_paths = [path for path in hydrex['source_references'] if Path(path).name == 'unsigned-swap-report-origin.json']
        require(len(origin_paths) == 1, 'The unsigned publication must retain its unique source origin')
        origin = json.loads((ROOT / origin_paths[0]).read_bytes())
        source = json.loads((ROOT / origin['source']).read_bytes())
        actual_samples = {item['sample']['task_key']: item['sample'] for item in hydrex['samples']
                          if item['sample']['purpose'] == 'behavioral' and item['sample']['verdict'] == 'PASS'}
        require(set(actual_samples) == {item['task_key'] for item in source['tasks'] if item.get('execution')},
                'Only retained actual executions may supply behavioral samples')
        for task in source['tasks']:
            status, scoped = request(port, 'GET', '/api/reports/' + hydrex_id + '/chain-evidence?task_key=' + quote(task['task_key'], safe=''))
            require(status == 200, 'Task-scoped chain evidence must be readable')
            execution = task.get('execution')
            if execution is None:
                require(scoped['actions'] == [], 'A quote or simulation must not acquire transaction actions')
                continue
            swaps = [item for item in scoped['actions'] if item['action'] == 'swap']
            require(len(swaps) == 1, 'Batch reads and approvals must not multiply the real exchange count')
            swap = swaps[0]
            tx_hash, payer = execution['transaction_hash'].lower(), execution['payer'].lower()
            require(swap['transaction_hash'].lower() == tx_hash and swap['executor'].lower() == payer
                    and swap['sample_id'] == actual_samples[task['task_key']]['sample_id'] and swap['verdict'] == 'PASS'
                    and default_swaps[0]['transaction_hash'].lower() == tx_hash,
                    'The displayed exchange must bind the actual transaction, buyer and behavioral sample')
            records = [json.loads((ROOT / path).read_bytes()).get('result') for path in swap['evidence']]
            transaction = next(item for item in records if isinstance(item, dict) and item.get('hash', '').lower() == tx_hash and 'input' in item)
            receipt = next(item for item in records if isinstance(item, dict) and item.get('transactionHash', '').lower() == tx_hash)
            require(swap['chain_id'] == int(transaction['chainId'], 16) and swap['block_number'] == int(receipt['blockNumber'], 16),
                    'The exchange must retain its chain instance and actual receipt block')
            routes = []
            for call in decode_batch(transaction['input']):
                try:
                    routes.append(decode_unsigned_swap({'to': call['target'], 'data': call['data'], 'value': call['value']}, chain_id=swap['chain_id']))
                except UnsupportedUnsignedSwap:
                    continue
            require(len(routes) == 1 and int(receipt['status'], 16) == 1, 'The retained receipt must confirm the supported swap route')
            route, transfers = routes[0], _transfers(receipt)
            paid = sum(amount for token, sender, _, amount in transfers if token == route['token_in'] and sender == payer)
            received = sum(amount for token, _, recipient, amount in transfers if token == route['token_out'] and recipient == route['recipient'])
            require(paid == route['amount_in'] and received >= route['minimum_out']
                    and all(part in swap['summary'] for part in (
                        '实际支付 ' + _asset(swap['chain_id'], route['token_in'], paid),
                        '实收 ' + _asset(swap['chain_id'], route['token_out'], received),
                        '最低到账为 ' + _asset(swap['chain_id'], route['token_out'], route['minimum_out']))),
                    'Swap text must explain the retained actual payment, receipt and decoded minimum output')
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
            "agents": 2, "reports": 2, "report_policy": "transaction-agent-evidence-v3",
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
