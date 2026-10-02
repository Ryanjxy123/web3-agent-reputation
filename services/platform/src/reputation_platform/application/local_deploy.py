"""Explicit local-only deployment/seed with a durable signed transaction journal."""

import json
import os
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import requests
from eth_account import Account
from reputation_core.evidence import hash_bytes, hash_json
from reputation_core.models import ChainIdentity, DeployedContract, LocalDeployment
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import RPCEndpoint

CONTRACTS = ("DemoAgentRegistry", "DemoRecordRegistry", "EvaluationAnchor")
ROLES = ("admin", "evaluator", "owner-a", "executor-a", "owner-d", "executor-d")


def local_web3(url: str) -> Web3:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "anvil"}
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("LOCAL_RPC_REQUIRED")
    session = requests.Session()
    session.trust_env = False
    web3 = Web3(Web3.HTTPProvider(url, session=session, request_kwargs={"timeout": 5}))
    if web3.eth.chain_id != 31337 or "anvil" not in web3.client_version.lower():
        raise ValueError("LOCAL_ANVIL_REQUIRED")
    return web3


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def contract_abi(root: Path, name: str) -> list:
    if name not in CONTRACTS:
        raise ValueError("UNSUPPORTED_CONTRACT")
    return json.loads((root / "contracts/abi" / f"{name}.json").read_text(encoding="utf-8"))


def verify_deployment(web3: Web3, deployment: LocalDeployment, root: Path) -> None:
    if str(web3.eth.chain_id) != deployment.chain.chain_id:
        raise ValueError("CHAIN_INSTANCE_MISMATCH")
    if web3.eth.get_block(0)["hash"].to_0x_hex() != deployment.chain.genesis_hash:
        raise ValueError("CHAIN_INSTANCE_MISMATCH")
    for contract in (deployment.registry, deployment.record, deployment.anchor):
        code = web3.eth.get_code(Web3.to_checksum_address(contract.address))
        if not code or hash_bytes(bytes(code)) != contract.code_hash:
            raise ValueError("CHAIN_INSTANCE_MISMATCH")
    registry = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.registry.address),
        abi=contract_abi(root, "DemoAgentRegistry"),
    )
    instance = registry.functions.deploymentInstanceId().call()
    if "0x" + bytes(instance).hex() != deployment.chain.deployment_instance_id:
        raise ValueError("CHAIN_INSTANCE_MISMATCH")


class SetupJournal:
    """Development setup outbox, not the platform's PostgreSQL job queue."""

    def __init__(self, path: Path, web3: Web3):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.web3 = path, web3
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations (name TEXT PRIMARY KEY, raw BLOB NOT NULL, tx_hash TEXT NOT NULL)"
            )
        os.chmod(path, 0o600)

    def transact(self, name: str, key: str, operation):
        account = Account.from_key(key)
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT raw, tx_hash FROM operations WHERE name=?", (name,)).fetchone()
            if row is None:
                transaction = operation.build_transaction(
                    {
                        "from": account.address,
                        "chainId": 31337,
                        "nonce": self.web3.eth.get_transaction_count(account.address, "pending"),
                        "gas": 5_000_000,
                        "gasPrice": self.web3.eth.gas_price,
                    }
                )
                signed = account.sign_transaction(transaction)
                row = (bytes(signed.raw_transaction), signed.hash.to_0x_hex())
                db.execute("INSERT INTO operations VALUES (?, ?, ?)", (name, *row))
        # A restart uses these exact bytes. Never allocate a second nonce for this operation.
        raw, tx_hash = row
        try:
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            try:
                self.web3.eth.get_transaction(tx_hash)
            except TransactionNotFound:
                self.web3.eth.send_raw_transaction(raw)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt["status"] != 1:
            raise RuntimeError("SETUP_TRANSACTION_REVERTED")
        return receipt


def deploy(root: Path, rpc_url: str, runtime: Path | None = None) -> LocalDeployment:
    runtime = runtime or root / "runtime/local-chain"
    runtime.mkdir(parents=True, exist_ok=True)
    config_path = runtime / "deployment.json"
    web3 = local_web3(rpc_url)
    metadata: dict = web3.provider.make_request(RPCEndpoint("anvil_metadata"), []).get("result", {})
    node_instance = metadata.get("instanceId")
    if not node_instance:
        raise ValueError("ANVIL_INSTANCE_UNAVAILABLE")
    if config_path.exists():
        deployment = LocalDeployment.model_validate_json(config_path.read_bytes())
        verify_deployment(web3, deployment, root)
        return deployment
    keys_path = runtime / "setup-secrets.json"
    if keys_path.exists():
        secret = json.loads(keys_path.read_bytes())
        if secret["genesis_hash"] != web3.eth.get_block(0)["hash"].to_0x_hex():
            raise ValueError("CHAIN_INSTANCE_MISMATCH")
        if secret.get("node_instance_id") != node_instance:
            raise ValueError("CHAIN_INSTANCE_MISMATCH")
    else:
        secret = {
            "keys": {role: Account.create().key.to_0x_hex() for role in ROLES},
            "instance": "0x" + secrets.token_hex(32),
            "platform_instance": "0x" + secrets.token_hex(32),
            "node_instance_id": node_instance,
            "genesis_hash": web3.eth.get_block(0)["hash"].to_0x_hex(),
        }
        write_json(keys_path, secret)
    for key in secret["keys"].values():
        response = web3.provider.make_request(
            RPCEndpoint("anvil_setBalance"), [Account.from_key(key).address, hex(100 * 10**18)]
        )
        if "error" in response:
            raise RuntimeError("LOCAL_FUNDING_FAILED")
    journal = SetupJournal(runtime / "setup-outbox.sqlite3", web3)
    deployments = {}
    for name in CONTRACTS:
        artifact = json.loads(
            (root / "contracts/out" / f"{name}.sol" / f"{name}.json").read_bytes()
        )
        factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
        args = (secret["instance"],) if name == "DemoAgentRegistry" else ()
        receipt = journal.transact(
            "deploy:" + name, secret["keys"]["admin"], factory.constructor(*args)
        )
        address = receipt["contractAddress"]
        deployments[name] = DeployedContract(
            address=address.lower(),
            code_hash=hash_bytes(bytes(web3.eth.get_code(address))),
            transaction_hash=receipt["transactionHash"].to_0x_hex(),
            block_number=str(receipt["blockNumber"]),
            block_hash=receipt["blockHash"].to_0x_hex(),
        )
    identity = {
        "chain_id": "31337",
        "genesis_hash": secret["genesis_hash"],
        "deployment_instance_id": secret["instance"],
        "registry_code_hash": deployments["DemoAgentRegistry"].code_hash,
    }
    deployment = LocalDeployment(
        rpc_url=rpc_url,
        chain=ChainIdentity(**identity, instance_hash=hash_json(identity)),
        registry=deployments["DemoAgentRegistry"],
        record=deployments["DemoRecordRegistry"],
        anchor=deployments["EvaluationAnchor"],
        admin=Account.from_key(secret["keys"]["admin"]).address.lower(),
        evaluator=Account.from_key(secret["keys"]["evaluator"]).address.lower(),
        platform_instance_id=secret["platform_instance"],
    )
    anchor = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.anchor.address),
        abi=contract_abi(root, "EvaluationAnchor"),
    )
    journal.transact(
        "grant:evaluator",
        secret["keys"]["admin"],
        anchor.functions.setEvaluator(Web3.to_checksum_address(deployment.evaluator), True),
    )
    write_json(config_path, deployment.model_dump(mode="json"))
    # The publisher receives only its own key, separate from API and fixture executors.
    write_json(runtime / "publisher-secret.json", {"private_key": secret["keys"]["evaluator"]})
    return deployment
