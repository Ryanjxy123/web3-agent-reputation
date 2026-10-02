"""Real Anvil deployment and fixture ledger recovery. No platform DB substitute."""

import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex

import pytest
from fastapi.testclient import TestClient
from fixture_agents.service import Agent, create_app
from reputation_core.models import TaskEnvelope
from reputation_platform.application.local_deploy import deploy, local_web3, verify_deployment
from reputation_platform.application.local_seed import seed
from web3.types import RPCEndpoint

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.chain


@contextmanager
def anvil_node():
    executable = shutil.which("anvil")
    assert executable, "Anvil is required; chain integration must not be skipped"
    subprocess.run(
        [shutil.which("forge"), "build", "--root", str(ROOT / "contracts")],
        check=True,
        capture_output=True,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [executable, "--host", "127.0.0.1", "--port", str(port), "--chain-id", "31337", "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                web3 = local_web3(url)
                break
            except OSError:
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.1)
        yield url, web3
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def local_chain(tmp_path_factory):
    with anvil_node() as (url, web3):
        runtime = tmp_path_factory.mktemp("chain")
        deployment = deploy(ROOT, url, runtime)
        samples = seed(ROOT, deployment, runtime)
        yield runtime, deployment, samples, web3


def task(deployment, **updates):
    values = dict(
        request_id="0x" + token_hex(32),
        record_hash="0x" + token_hex(32),
        snapshot_hash="0x" + token_hex(32),
        chain_id="31337",
        chain_instance_id=deployment.chain.instance_hash,
        target_contract=deployment.record.address,
        deadline=(datetime.now(UTC) + timedelta(seconds=60))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    )
    return TaskEnvelope(**{**values, **updates})


def test_seed_twice_is_idempotent_and_roles_are_distinct(local_chain):
    runtime, deployment, samples, web3 = local_chain
    before = web3.eth.block_number
    assert deploy(ROOT, deployment.rpc_url, runtime) == deployment
    assert seed(ROOT, deployment, runtime) == samples
    assert web3.eth.block_number == before
    roles = [
        deployment.admin,
        deployment.evaluator,
        *(s[role] for s in samples.values() for role in ("owner", "executor")),
    ]
    assert len(set(roles)) == 6


def test_http_persists_intent_and_payload_idempotency(local_chain, tmp_path):
    runtime, deployment, _, _ = local_chain
    config = tmp_path / "agent.json"
    config.write_bytes((runtime / "fixture-a.json").read_bytes())
    with TestClient(create_app(config, run_worker=False)) as client:
        envelope = task(deployment)
        payload = envelope.model_dump(mode="json")
        headers = {"Idempotency-Key": envelope.request_id}
        first = client.post("/tasks", json=payload, headers=headers)
        assert first.status_code == 202 and first.json()["task_status"] == "accepted"
        assert first.json()["result"] is None
        assert client.post("/tasks", json=payload, headers=headers).json() == first.json()
        conflict = {**payload, "record_hash": "0x" + token_hex(32)}
        response = client.post("/tasks", json=conflict, headers=headers)
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        )
    restarted = Agent(config)
    assert restarted.status(envelope.request_id).task_status == "accepted"
    restarted.process(envelope.request_id)
    state = restarted.status(envelope.request_id)
    assert state.task_status == "succeeded"
    exists, digest = restarted.record.functions.getRecord(
        restarted.account.address, envelope.request_id
    ).call()
    assert exists and "0x" + bytes(digest).hex() == envelope.record_hash
    assert restarted.accept(envelope) == state


@pytest.mark.parametrize("boundary", ["after_sign", "after_broadcast"])
def test_crash_recovers_same_signed_transaction_without_duplicate_record(
    local_chain, tmp_path, boundary
):
    runtime, deployment, _, web3 = local_chain

    def crash():
        raise RuntimeError("SIMULATED_PROCESS_EXIT")

    ledger = tmp_path / "ledger.sqlite3"
    agent = Agent(runtime / "fixture-a.json", ledger, **{boundary: crash})
    envelope = task(deployment)
    agent.accept(envelope)
    with pytest.raises(RuntimeError, match="SIMULATED_PROCESS_EXIT"):
        agent.process(envelope.request_id)
    with agent.connect() as db:
        signed = db.execute("SELECT tx_hash,signed_raw,tx_nonce FROM tasks").fetchone()
        assert signed["signed_raw"] and signed["tx_hash"]
    restarted = Agent(runtime / "fixture-a.json", ledger)
    restarted.process(envelope.request_id)
    assert restarted.status(envelope.request_id).result.tx_hash == signed["tx_hash"]
    logs = restarted.record.events.RecordAnchored().get_logs(
        from_block=0,
        argument_filters={"executor": restarted.account.address, "requestId": envelope.request_id},
    )
    assert len(logs) == 1
    assert web3.eth.get_transaction_receipt(signed["tx_hash"])["status"] == 1


def test_two_threads_reserve_distinct_nonces(local_chain, tmp_path):
    runtime, deployment, _, _ = local_chain
    agent = Agent(runtime / "fixture-a.json", tmp_path / "ledger.sqlite3")
    tasks = [task(deployment), task(deployment)]
    for envelope in tasks:
        agent.accept(envelope)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(agent.process, [value.request_id for value in tasks]))
    assert all(agent.status(value.request_id).task_status == "succeeded" for value in tasks)
    with agent.connect() as db:
        assert db.execute("SELECT COUNT(DISTINCT tx_nonce) FROM tasks").fetchone()[0] == 2


def test_d_returns_a_real_successful_but_unrelated_transaction(local_chain, tmp_path):
    runtime, deployment, _, web3 = local_chain
    agent = Agent(runtime / "fixture-d.json", tmp_path / "ledger.sqlite3")
    envelope = task(deployment)
    agent.accept(envelope)
    agent.process(envelope.request_id)
    result = agent.status(envelope.request_id).result
    receipt = web3.eth.get_transaction_receipt(result.tx_hash)
    assert receipt["status"] == 1
    event = agent.record.events.RecordAnchored().process_receipt(receipt)[0]["args"]
    assert "0x" + bytes(event["requestId"]).hex() != envelope.request_id
    assert "0x" + bytes(event["recordHash"]).hex() != envelope.record_hash
    exists, _ = agent.record.functions.getRecord(agent.account.address, envelope.request_id).call()
    assert not exists
    assert "mode" not in agent.metadata and "private_key" not in agent.metadata


def test_invalid_targets_and_expired_deadlines_are_rejected(local_chain, tmp_path):
    runtime, deployment, _, _ = local_chain
    config = tmp_path / "agent.json"
    config.write_bytes((runtime / "fixture-a.json").read_bytes())
    with TestClient(create_app(config, run_worker=False)) as client:
        for updates, expected in [
            ({"chain_id": "1"}, 403),
            ({"target_contract": deployment.anchor.address}, 403),
            ({"deadline": "2000-01-01T00:00:00.000Z"}, 422),
        ]:
            envelope = task(deployment, **updates)
            response = client.post(
                "/tasks",
                json=envelope.model_dump(mode="json"),
                headers={"Idempotency-Key": envelope.request_id},
            )
            assert response.status_code == expected


def test_chain_instance_change_is_not_silently_reused(local_chain):
    runtime, deployment, _, web3 = local_chain
    snapshot = web3.provider.make_request(RPCEndpoint("evm_snapshot"), [])["result"]
    try:
        # Same chain id/genesis, erased registry code: configuration must fail closed.
        web3.provider.make_request(
            RPCEndpoint("anvil_setCode"), [deployment.registry.address, "0x"]
        )
        with pytest.raises(ValueError, match="CHAIN_INSTANCE_MISMATCH"):
            verify_deployment(web3, deployment, ROOT)
        with pytest.raises(ValueError, match="CHAIN_INSTANCE_MISMATCH"):
            deploy(ROOT, deployment.rpc_url, runtime)
    finally:
        assert web3.provider.make_request(RPCEndpoint("evm_revert"), [snapshot])["result"]


def test_real_anvil_reset_rejects_completed_and_partial_setup(tmp_path):
    with anvil_node() as (url, web3):
        deployment = deploy(ROOT, url, tmp_path)
        response = web3.provider.make_request(RPCEndpoint("anvil_reset"), [])
        assert "error" not in response
        with pytest.raises(ValueError, match="CHAIN_INSTANCE_MISMATCH"):
            deploy(ROOT, url, tmp_path)
        # Simulate the same setup interrupted before publishing its final config.
        (tmp_path / "deployment.json").rename(tmp_path / "prior-deployment.json")
        with pytest.raises(ValueError, match="CHAIN_INSTANCE_MISMATCH"):
            deploy(ROOT, url, tmp_path)
        assert (tmp_path / "prior-deployment.json").is_file()
        assert deployment.chain.chain_id == "31337"
