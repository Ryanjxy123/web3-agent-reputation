"""Controlled HTTP v1 with an independent durable SQLite ledger and signed outbox."""

import asyncio
import json
import logging
import os
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests
from eth_account import Account
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json
from reputation_core.models import ControlledTaskView, LocalDeployment, TaskEnvelope, TaskResult
from web3 import Web3
from web3.exceptions import TransactionNotFound, Web3Exception
from web3.types import Nonce, TxParams

LOG = logging.getLogger(__name__)


class TaskRejected(ValueError):
    def __init__(self, code: str, status: int = 422):
        self.code, self.status = code, status


class Agent:
    def __init__(
        self,
        config: Path,
        ledger: Path | None = None,
        after_sign: Callable | None = None,
        after_broadcast: Callable | None = None,
    ):
        value = json.loads(config.read_bytes())
        self.deployment = LocalDeployment.model_validate(value["deployment"])
        self.metadata, self.mode = value["metadata"], value["mode"]
        if self.mode not in {"normal", "replay"}:
            raise ValueError("UNSUPPORTED_FIXTURE_MODE")
        self.account = Account.from_key(value["private_key"])
        self.replay_tx_hash = value["replay_tx_hash"]
        if self.metadata["declared_executor"] != self.account.address.lower():
            raise ValueError("EXECUTOR_CONFIG_MISMATCH")
        if self.mode == "replay" and not self.replay_tx_hash:
            raise ValueError("REPLAY_TRANSACTION_REQUIRED")
        self.after_sign, self.after_broadcast = after_sign, after_broadcast
        self.ledger = ledger or config.with_suffix(".sqlite3")
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        parsed = urlsplit(self.deployment.rpc_url)
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
        self.web3 = Web3(
            Web3.HTTPProvider(
                self.deployment.rpc_url, session=session, request_kwargs={"timeout": 5}
            )
        )
        self.registry = self.web3.eth.contract(
            address=Web3.to_checksum_address(self.deployment.registry.address),
            abi=value["registry_abi"],
        )
        self.record = self.web3.eth.contract(
            address=Web3.to_checksum_address(self.deployment.record.address),
            abi=value["record_abi"],
        )
        self.verify_chain()
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                accepted_at TEXT NOT NULL, status TEXT NOT NULL, tx_nonce INTEGER UNIQUE,
                signed_raw BLOB, tx_hash TEXT, result TEXT, reason TEXT)""")
        os.chmod(self.ledger, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.ledger, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def verify_chain(self) -> None:
        expected = self.deployment.chain
        if (
            expected.chain_id != "31337"
            or self.web3.eth.chain_id != 31337
            or "anvil" not in self.web3.client_version.lower()
        ):
            raise TaskRejected("CHAIN_INSTANCE_MISMATCH", 503)
        if self.web3.eth.get_block(0)["hash"].to_0x_hex() != expected.genesis_hash:
            raise TaskRejected("CHAIN_INSTANCE_MISMATCH", 503)
        for ref in (self.deployment.registry, self.deployment.record):
            code = self.web3.eth.get_code(Web3.to_checksum_address(ref.address))
            if not code or hash_bytes(bytes(code)) != ref.code_hash:
                raise TaskRejected("CHAIN_INSTANCE_MISMATCH", 503)
        if (
            "0x" + bytes(self.registry.functions.deploymentInstanceId().call()).hex()
            != expected.deployment_instance_id
        ):
            raise TaskRejected("CHAIN_INSTANCE_MISMATCH", 503)

    def accept(self, task: TaskEnvelope) -> ControlledTaskView:
        payload = task.model_dump(mode="json")
        payload_hash = hash_json(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT payload_hash FROM tasks WHERE request_id=?", (task.request_id,)
            ).fetchone()
            if prior is not None:
                if prior["payload_hash"] != payload_hash:
                    raise TaskRejected("IDEMPOTENCY_CONFLICT", 409)
            else:
                if (
                    task.chain_id != self.deployment.chain.chain_id
                    or task.chain_instance_id != self.deployment.chain.instance_hash
                    or task.target_contract != self.deployment.record.address
                ):
                    raise TaskRejected("TARGET_NOT_ALLOWED", 403)
                remaining = (
                    datetime.fromisoformat(task.deadline) - datetime.now(UTC)
                ).total_seconds()
                if not 0 < remaining <= 65:
                    raise TaskRejected("INVALID_DEADLINE")
                self.verify_chain()
                db.execute(
                    "INSERT INTO tasks (request_id,payload_hash,payload,accepted_at,status) VALUES (?,?,?,?,?)",
                    (
                        task.request_id,
                        payload_hash,
                        canonical_bytes(payload).decode(),
                        datetime.now(UTC).isoformat(),
                        "accepted",
                    ),
                )
        return self.status(task.request_id)

    def status(self, request_id: str) -> ControlledTaskView:
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise TaskRejected("TASK_NOT_FOUND", 404)
        return ControlledTaskView(
            request_id=request_id,
            task_status=row["status"],
            status_path="/tasks/" + request_id,
            result=TaskResult.model_validate_json(row["result"]) if row["result"] else None,
            reason_code=row["reason"],
        )

    def pending(self) -> list[str]:
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT request_id FROM tasks WHERE status IN ('accepted','running') ORDER BY accepted_at LIMIT 10"
                )
            ]

    def process(self, request_id: str) -> None:
        self.verify_chain()
        newly_signed = False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["status"] not in {"accepted", "running"}:
                return
            task = TaskEnvelope.model_validate_json(row["payload"])
            if self.mode == "replay":
                receipt = self.web3.eth.get_transaction_receipt(self.replay_tx_hash)
                if receipt["status"] != 1:
                    raise RuntimeError("REPLAY_FIXTURE_NOT_SUCCESSFUL")
                tx_hash = self.replay_tx_hash
                raw = None
            elif row["signed_raw"] is not None:
                raw, tx_hash = row["signed_raw"], row["tx_hash"]
            else:
                if datetime.now(UTC) > datetime.fromisoformat(task.deadline):
                    db.execute(
                        "UPDATE tasks SET status='failed',reason='TASK_DEADLINE_EXCEEDED' WHERE request_id=?",
                        (request_id,),
                    )
                    return
                reserved = db.execute("SELECT MAX(tx_nonce) FROM tasks").fetchone()[0]
                nonce = max(
                    self.web3.eth.get_transaction_count(self.account.address, "pending"),
                    (reserved + 1) if reserved is not None else 0,
                )
                parameters: TxParams = {
                    "from": self.account.address,
                    "chainId": 31337,
                    "nonce": Nonce(int(nonce)),
                    "gas": 150_000,
                    "gasPrice": self.web3.eth.gas_price,
                }
                transaction = self.record.functions.anchorRecord(
                    task.request_id, task.record_hash
                ).build_transaction(parameters)
                signed = self.account.sign_transaction(transaction)
                raw, tx_hash = bytes(signed.raw_transaction), signed.hash.to_0x_hex()
                db.execute(
                    "UPDATE tasks SET status='running',tx_nonce=?,signed_raw=?,tx_hash=? WHERE request_id=?",
                    (nonce, raw, tx_hash, request_id),
                )
                newly_signed = True
        if newly_signed and self.after_sign:
            self.after_sign()
        if raw is not None:
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                try:
                    self.web3.eth.get_transaction(tx_hash)
                except TransactionNotFound:
                    self.web3.eth.send_raw_transaction(raw)
                if self.after_broadcast:
                    self.after_broadcast()
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)
        result = TaskResult(
            chain_id="31337",
            tx_hash=tx_hash,
            executor=self.account.address.lower(),
            record_hash=task.record_hash,
        )
        with self.connect() as db:
            db.execute(
                "UPDATE tasks SET status=?,result=?,reason=? WHERE request_id=?",
                (
                    "succeeded" if receipt["status"] == 1 else "failed",
                    result.model_dump_json(),
                    None if receipt["status"] == 1 else "TRANSACTION_REVERTED",
                    request_id,
                ),
            )


def create_app(config_path: Path | None = None, *, run_worker: bool = True) -> FastAPI:
    config = config_path or Path(os.environ["FIXTURE_CONFIG"])
    agent = Agent(config)

    async def consume():
        while True:
            for request_id in await asyncio.to_thread(agent.pending):
                try:
                    await asyncio.to_thread(agent.process, request_id)
                except (requests.RequestException, Web3Exception, OSError, TaskRejected):
                    LOG.warning("Fixture task %s awaits RPC reconciliation.", request_id)
            await asyncio.sleep(0.5)

    @asynccontextmanager
    async def lifespan(app):
        work = asyncio.create_task(consume()) if run_worker else None
        app.state.consumer = work
        try:
            yield
        finally:
            if work:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)

    app = FastAPI(title="Controlled demo Agent", lifespan=lifespan)
    app.state.agent = agent

    @app.exception_handler(TaskRejected)
    async def rejection(request, error: TaskRejected):
        return JSONResponse(
            {"accepted": False, "error": {"code": error.code}}, status_code=error.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request, error):
        return JSONResponse({"accepted": False, "error": {"code": "SCHEMA_ERROR"}}, status_code=422)

    @app.get("/health")
    def health():
        work = getattr(app.state, "consumer", None)
        if work and work.done():
            raise HTTPException(503, detail="FIXTURE_WORKER_UNAVAILABLE")
        return {"status": "ok", "protocol": "controlled-http-v1"}

    @app.get("/capabilities")
    def capabilities():
        return agent.metadata

    @app.post("/tasks", response_model=ControlledTaskView, status_code=202)
    def submit(task: TaskEnvelope, idempotency_key: str | None = Header(default=None)):
        if idempotency_key != task.request_id:
            raise HTTPException(400, detail="IDEMPOTENCY_KEY_REQUIRED")
        return agent.accept(task)

    @app.get("/tasks/{request_id}", response_model=ControlledTaskView)
    def status(request_id: str):
        return agent.status(request_id)

    return app
