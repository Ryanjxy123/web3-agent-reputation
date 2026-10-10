"""Faults come from the real fixture protocol or Anvil execution, never scoring labels."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from fixture_agents.service import Agent, create_app
from web3 import Web3

from tests.integration.test_fixture_agents import local_chain, task

__all__ = ["local_chain"]
pytestmark = pytest.mark.chain


def configured(local_chain, tmp_path, mode, **changes):
    runtime, _, _, _ = local_chain
    value = json.loads((runtime / "fixture-a.json").read_bytes())
    value.update(mode=mode, **changes)
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps(value), encoding="utf-8")
    return config


def test_intermittent_http_fault_is_stable_across_retries_and_restart(local_chain, tmp_path):
    _, deployment, _, web3 = local_chain
    config = configured(local_chain, tmp_path, "intermittent")
    rejected = task(deployment, request_id="0x" + f"{1:064x}")
    accepted = task(deployment, request_id="0x" + f"{3:064x}")
    before = web3.eth.block_number
    for _ in range(2):
        with TestClient(create_app(config, run_worker=False)) as client:
            assert client.get("/health").status_code == 200
            metadata = client.get("/capabilities").json()
            assert "mode" not in metadata and "fault_seed" not in metadata
            for _ in range(2):
                response = client.post(
                    "/tasks", json=rejected.model_dump(mode="json"),
                    headers={"Idempotency-Key": rejected.request_id},
                )
                assert response.status_code == 503
                assert response.json() == {
                    "accepted": False, "error": {"code": "FIXTURE_SERVICE_UNAVAILABLE"},
                }
                assert client.get("/tasks/" + rejected.request_id).status_code == 503
            response = client.post(
                "/tasks", json=accepted.model_dump(mode="json"),
                headers={"Idempotency-Key": accepted.request_id},
            )
            assert response.status_code == 202 and response.json()["task_status"] == "accepted"
            assert client.get("/tasks/" + accepted.request_id).json() == response.json()
    agent = Agent(config)
    with agent.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    assert web3.eth.block_number == before
    agent.process(accepted.request_id)
    assert agent.status(accepted.request_id).task_status == "succeeded"


@pytest.mark.parametrize("capability", ["anchor_record", "get_tx_status", "verify_record"])
def test_declared_but_unsupported_is_accepted_then_fails_without_chain_write(
    local_chain, tmp_path, capability,
):
    _, deployment, samples, web3 = local_chain
    config = configured(local_chain, tmp_path, "unsupported")
    values = {"capability_id": capability}
    if capability != "anchor_record":
        values.update(
            read_block_number=str(web3.eth.block_number),
            read_block_hash=web3.eth.get_block("latest")["hash"].to_0x_hex(),
        )
        if capability == "get_tx_status":
            values.update(query_tx_hash=deployment.record.transaction_hash, record_hash=None,
                          target_contract=None)
        else:
            values.update(record_executor=samples["a"]["executor"],
                          record_request_id="0x" + "99" * 32)
    envelope = task(deployment, **values)
    before = web3.eth.block_number
    with TestClient(create_app(config, run_worker=False)) as client:
        assert capability in client.get("/capabilities").json()["capabilities"]
        response = client.post(
            "/tasks", json=envelope.model_dump(mode="json"),
            headers={"Idempotency-Key": envelope.request_id},
        )
        assert response.status_code == 202 and response.json()["accepted"]
    agent = Agent(config)
    agent.process(envelope.request_id)
    state = agent.status(envelope.request_id)
    assert state.task_status == "failed" and state.result is None
    assert state.reason_code == "CAPABILITY_EXPLICITLY_UNSUPPORTED"
    assert agent.accept(envelope) == state
    assert web3.eth.block_number == before
    with agent.connect() as db:
        assert db.execute("SELECT signed_raw FROM tasks").fetchone()[0] is None


def test_wrong_executor_signs_real_record_but_claims_declared_identity(local_chain, tmp_path):
    runtime, deployment, samples, web3 = local_chain
    other = json.loads((runtime / "fixture-d.json").read_bytes())
    config = configured(local_chain, tmp_path, "wrong_executor", private_key=other["private_key"])
    agent = Agent(config)
    envelope = task(deployment)
    agent.accept(envelope)
    agent.process(envelope.request_id)
    result = agent.status(envelope.request_id).result
    receipt = web3.eth.get_transaction_receipt(result.tx_hash)
    assert receipt["status"] == 1
    assert result.executor == samples["a"]["executor"]
    assert web3.eth.get_transaction(result.tx_hash)["from"].lower() == samples["d"]["executor"]
    event = agent.record.events.RecordAnchored().process_receipt(receipt)[0]["args"]
    assert event["executor"].lower() == samples["d"]["executor"]
    assert "0x" + bytes(event["requestId"]).hex() == envelope.request_id
    assert "0x" + bytes(event["recordHash"]).hex() == envelope.record_hash
    assert not agent.record.functions.getRecord(
        Web3.to_checksum_address(samples["a"]["executor"]), envelope.request_id,
    ).call()[0]
    with agent.connect() as db:
        assert db.execute("SELECT signed_raw FROM tasks").fetchone()[0]
    assert Agent(config).status(envelope.request_id).result == result


@pytest.mark.parametrize("mode", ["normal", "intermittent", "timeout", "unsupported", "replay"])
def test_executor_mismatch_is_only_allowed_in_explicit_fault_mode(local_chain, tmp_path, mode):
    runtime, _, _, _ = local_chain
    other = json.loads((runtime / "fixture-d.json").read_bytes())
    config = configured(local_chain, tmp_path, mode, private_key=other["private_key"])
    with pytest.raises(ValueError, match="EXECUTOR_CONFIG_MISMATCH"):
        Agent(config)


@pytest.mark.parametrize("address_format", ["lower", "checksum"])
def test_wrong_executor_mode_requires_an_actual_mismatch(local_chain, tmp_path, address_format):
    config = configured(local_chain, tmp_path, "wrong_executor")
    if address_format == "checksum":
        value = json.loads(config.read_bytes())
        value["metadata"]["declared_executor"] = Web3.to_checksum_address(
            value["metadata"]["declared_executor"]
        )
        config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="EXECUTOR_FAULT_REQUIRES_DISTINCT_KEY"):
        Agent(config)


@pytest.mark.parametrize("address", ["invalid", "0x" + "00" * 20])
def test_wrong_executor_mode_rejects_invalid_or_zero_declarations(local_chain, tmp_path, address):
    config = configured(local_chain, tmp_path, "wrong_executor")
    value = json.loads(config.read_bytes())
    value["metadata"]["declared_executor"] = address
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="EXECUTOR_CONFIG_MISMATCH"):
        Agent(config)


def test_unsupported_mode_reconciles_an_already_signed_task(local_chain, tmp_path):
    _, deployment, _, web3 = local_chain
    config = configured(local_chain, tmp_path, "normal")
    def crash():
        raise RuntimeError("SIMULATED_PROCESS_EXIT")
    agent = Agent(config, after_sign=crash)
    envelope = task(deployment)
    agent.accept(envelope)
    with pytest.raises(RuntimeError, match="SIMULATED_PROCESS_EXIT"):
        agent.process(envelope.request_id)
    with agent.connect() as db:
        signed_hash = db.execute("SELECT tx_hash FROM tasks").fetchone()[0]
    value = json.loads(config.read_bytes())
    value["mode"] = "unsupported"
    config.write_text(json.dumps(value), encoding="utf-8")
    restarted = Agent(config)
    restarted.process(envelope.request_id)
    result = restarted.status(envelope.request_id)
    assert result.task_status == "succeeded" and result.result.tx_hash == signed_hash
    assert web3.eth.get_transaction_receipt(signed_hash)["status"] == 1
    assert len(restarted.record.events.RecordAnchored().get_logs(
        from_block=0,
        argument_filters={"executor": restarted.account.address, "requestId": envelope.request_id},
    )) == 1


def test_wrong_executor_cannot_enable_a_public_rpc(local_chain, tmp_path):
    runtime, _, _, _ = local_chain
    other = json.loads((runtime / "fixture-d.json").read_bytes())
    config = configured(local_chain, tmp_path, "wrong_executor", private_key=other["private_key"])
    value = json.loads(config.read_bytes())
    value["deployment"]["rpc_url"] = "https://public.example:443"
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="LOCAL_RPC_REQUIRED"):
        Agent(config)


def test_timeout_delays_business_route_without_blocking_health_or_dropping_ledger(
    local_chain, tmp_path,
):
    _, deployment, _, _ = local_chain
    config = configured(local_chain, tmp_path, "timeout", delay_seconds=0.15)
    with TestClient(create_app(config, run_worker=False)) as client:
        agent = client.app.state.agent
        async def observe():
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.03):
                    await agent.http_behavior("0x" + "01" * 32)
        asyncio.run(observe())
        assert client.get("/health").status_code == 200
        envelope = task(deployment)
        started = time.monotonic()
        response = client.post(
            "/tasks", json=envelope.model_dump(mode="json"),
            headers={"Idempotency-Key": envelope.request_id},
        )
        assert response.status_code == 202
        assert time.monotonic() - started >= 0.15
    recovered = Agent(config)
    assert recovered.status(envelope.request_id).task_status == "accepted"
    recovered.process(envelope.request_id)
    assert recovered.status(envelope.request_id).task_status == "succeeded"
