"""Idempotent local A/D identities and a real unrelated successful D transaction."""

import base64
import json
import os
import secrets
from pathlib import Path

from eth_account import Account
from reputation_core.evidence import canonical_bytes
from reputation_core.models import LocalDeployment
from web3 import Web3

from reputation_platform.configuration import controlled_fixture_ports

from .local_deploy import SetupJournal, contract_abi, local_web3, verify_deployment, write_json


def seed(
    root: Path,
    deployment: LocalDeployment,
    runtime: Path | None = None,
    hosts: tuple[str, str] = ("127.0.0.1", "127.0.0.1"),
) -> dict:
    hosts = (
        os.environ.get("FIXTURE_HOST_A", hosts[0]),
        os.environ.get("FIXTURE_HOST_D", hosts[1]),
    )
    ports = controlled_fixture_ports()
    runtime = runtime or root / "runtime/local-chain"
    web3 = local_web3(deployment.rpc_url)
    verify_deployment(web3, deployment, root)
    secret = json.loads((runtime / "setup-secrets.json").read_bytes())
    journal = SetupJournal(runtime / "setup-outbox.sqlite3", web3)
    registry = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.registry.address),
        abi=contract_abi(root, "DemoAgentRegistry"),
    )
    record = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.record.address),
        abi=contract_abi(root, "DemoRecordRegistry"),
    )
    state_path = runtime / "seed-intent.json"
    if state_path.exists():
        intent = json.loads(state_path.read_bytes())
        if (
            intent["chain_instance"] != deployment.chain.instance_hash
            or intent["hosts"] != list(hosts)
            or intent.get("ports", [9101, 9102]) != list(ports)
        ):
            raise ValueError("SEED_INTENT_CONFLICT")
    else:
        intent = {
            "chain_instance": deployment.chain.instance_hash,
            "hosts": list(hosts),
            "ports": list(ports),
            "replay_request": "0x" + secrets.token_hex(32),
            "replay_record": "0x" + secrets.token_hex(32),
        }
        write_json(state_path, intent)
    result = {}
    for sample, host, port in (("a", hosts[0], ports[0]), ("d", hosts[1], ports[1])):
        if host not in {"127.0.0.1", f"fixture-{sample}"}:
            raise ValueError("CONTROLLED_HOST_REQUIRED")
        owner_key, executor_key = (
            secret["keys"][f"owner-{sample}"],
            secret["keys"][f"executor-{sample}"],
        )
        owner, executor = (
            Account.from_key(owner_key).address,
            Account.from_key(executor_key).address,
        )
        endpoint = {
            "endpoint_id": f"fixture-{sample}",
            "scheme": "http",
            "host": host,
            "port": port,
            "path": "/tasks",
            "method": "POST",
            "protocol": "controlled-http-v1",
        }
        metadata = {
            "name": f"Controlled Agent {sample.upper()}",
            "description": "Provides transaction status, record verification and synthetic anchoring.",
            "capabilities": ["get_tx_status", "verify_record", "anchor_record"],
            "declared_executor": executor.lower(),
            "endpoints": [endpoint],
        }
        prior_fixture = runtime / f"fixture-{sample}.json"
        if prior_fixture.exists():
            metadata = json.loads(prior_fixture.read_bytes())["metadata"]
        uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode(
            "ascii"
        )
        receipt = journal.transact(
            f"register:{sample}", owner_key, registry.functions.register(uri)
        )
        registered = registry.events.AgentRegistered().process_receipt(receipt)
        agent_id = int(registered[0]["args"]["agentId"])
        journal.transact(
            f"executor:{sample}",
            owner_key,
            registry.functions.setDeclaredExecutor(agent_id, executor),
        )
        if (
            registry.functions.ownerOf(agent_id).call() != owner
            or registry.functions.agentURI(agent_id).call() != uri
            or registry.functions.declaredExecutorOf(agent_id).call() != executor
        ):
            raise ValueError("SEEDED_IDENTITY_CHANGED")
        replay_tx = None
        if sample == "d":
            replay = journal.transact(
                "replay:d",
                executor_key,
                record.functions.anchorRecord(intent["replay_request"], intent["replay_record"]),
            )
            replay_tx = replay["transactionHash"].to_0x_hex()
        # API/platform config never receives mode, private key or fixture ledger path.
        result[sample] = {
            "agent_ref": {
                "namespace": "eip155",
                "chain_id": "31337",
                "registry_address": deployment.registry.address,
                "agent_id": str(agent_id),
            },
            "owner": owner.lower(),
            "executor": executor.lower(),
            "metadata": metadata,
        }
        fixture = {
            "deployment": deployment.model_dump(mode="json"),
            "metadata": metadata,
            "private_key": executor_key,
            "mode": "normal" if sample == "a" else "replay",
            "replay_tx_hash": replay_tx,
            "registry_abi": contract_abi(root, "DemoAgentRegistry"),
            "record_abi": contract_abi(root, "DemoRecordRegistry"),
        }
        write_json(runtime / f"fixture-{sample}.json", fixture)
    write_json(runtime / "samples.json", result)
    return result
