"""Crash-safe local EvaluationAnchor publisher."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from eth_account import Account
from reputation_core.evidence import hash_json
from reputation_core.models import AcceptedJob, AnchorReceipt, AnchorStatus
from sqlalchemy import insert, select, text, update
from web3 import Web3
from web3.exceptions import TransactionNotFound

from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, enqueue
from reputation_platform.infrastructure.db.tables import anchor_jobs, anchor_receipts, signer_nonces

from .errors import ApplicationError
from .identity import IdentityService
from .local_deploy import contract_abi, local_web3, verify_deployment
from .reports import ReportService


class AnchorService:
    def __init__(self, database, identity: IdentityService | None = None):
        self.db = database
        self.identity = identity or IdentityService(database)
        self.reports = ReportService(database, self.identity)

    def request(self, report_id: UUID, actor: str) -> AcceptedJob:
        report = self.reports.view(report_id)
        publication = report.manifest.publication
        with self.db.begin() as connection:
            row = connection.execute(
                select(anchor_jobs.c.id).where(anchor_jobs.c.report_fk == report_id)
            ).scalar_one_or_none()
            if row is None:
                row = uuid4()
                connection.execute(
                    insert(anchor_jobs).values(
                        id=row,
                        report_fk=report_id,
                        chain_instance=publication.chain.instance_hash,
                        contract=publication.contract,
                        publisher=publication.publisher,
                        report_hash=report.report_hash,
                        state=AnchorStatus.QUEUED.value,
                    )
                )
            job_id = enqueue(connection, "anchor", f"anchor:{report_id}", {"report_id": str(report_id)}, None)
            self.identity.audit(
                connection,
                actor,
                "anchor.request",
                report_id,
                {"job_id": str(job_id), "anchor_job_id": str(row)},
            )
        return AcceptedJob(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}")

    def _secret(self) -> str:
        configured = os.environ.get("PUBLISHER_SECRET_PATH")
        if configured is None:
            deployment = Path(os.environ.get("LOCAL_CHAIN_CONFIG", self.identity.root / "runtime/local-chain/deployment.json"))
            configured = str(deployment.with_name("publisher-secret.json"))
        path = Path(configured)
        try:
            value = json.loads(path.read_bytes())["private_key"]
            account = Account.from_key(value)
        except (OSError, KeyError, TypeError, ValueError):
            raise ApplicationError(503, "PUBLISHER_NOT_CONFIGURED", "A local publisher key is required.", True) from None
        return account.key.hex()

    def _signed(self, report, row, web3: Web3, contract, account):
        previous, _ = contract.functions.head(
            Web3.to_checksum_address(report.manifest.publication.publisher),
            bytes.fromhex(report.core.agent_key_hash[2:]),
        ).call()
        observed_previous = "0x" + bytes(previous).hex()
        if observed_previous != report.core.previous_report_hash:
            raise ApplicationError(409, "PREVIOUS_REPORT_UNPUBLISHED", "The committed previous report is not the chain head.")
        nonce = web3.eth.get_transaction_count(account.address, "pending")
        with self.db.begin() as connection:
            lock = int(hash_json(account.address)[2:18], 16)
            if lock >= 2**63:
                lock -= 2**64
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            locked = connection.execute(
                select(signer_nonces.c.next_nonce)
                .where(signer_nonces.c.chain_instance == report.manifest.publication.chain.instance_hash, signer_nonces.c.address == account.address.lower())
                .with_for_update()
            ).scalar_one_or_none()
            if locked is None:
                locked = nonce
                connection.execute(insert(signer_nonces).values(
                    chain_instance=report.manifest.publication.chain.instance_hash,
                    address=account.address.lower(),
                    next_nonce=locked + 1,
                ))
            else:
                locked = max(locked, nonce)
                connection.execute(update(signer_nonces).where(
                    signer_nonces.c.chain_instance == report.manifest.publication.chain.instance_hash,
                    signer_nonces.c.address == account.address.lower(),
                ).values(next_nonce=locked + 1))
            transaction = contract.functions.anchorReport(
                bytes.fromhex(report.core.agent_key_hash[2:]),
                bytes.fromhex(report.report_hash[2:]),
                bytes.fromhex(report.core.policy_hash[2:]),
                bytes.fromhex(report.core.previous_report_hash[2:]),
            ).build_transaction({
                "from": account.address,
                "chainId": int(report.manifest.publication.chain.chain_id),
                "nonce": locked,
                "gas": 300_000,
                "gasPrice": web3.eth.gas_price,
            })
            signed = account.sign_transaction(transaction)
            raw = "0x" + bytes(signed.raw_transaction).hex()
            tx_hash = signed.hash.to_0x_hex()
            connection.execute(update(anchor_jobs).where(anchor_jobs.c.id == row["id"]).values(
                nonce=locked, signed_tx_hash=tx_hash, signed_transaction=raw, state=AnchorStatus.SIGNED.value,
            ))
            return raw, tx_hash

    async def publish(self, lease: Lease, queue: JobQueue) -> None:
        report_id = UUID(lease.payload["report_id"])
        report = self.reports.view(report_id)
        deployment = self.identity.deployment()
        web3 = local_web3(deployment.rpc_url)
        verify_deployment(web3, deployment, self.identity.root)
        account = Account.from_key(self._secret())
        if account.address.lower() != report.manifest.publication.publisher.lower() or account.address.lower() != deployment.evaluator.lower():
            raise ApplicationError(503, "PUBLISHER_IDENTITY_MISMATCH", "Publisher key does not match the committed evaluator.")
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(report.manifest.publication.contract),
            abi=contract_abi(self.identity.root, "EvaluationAnchor"),
        )
        with self.db.connect() as connection:
            row = connection.execute(select(anchor_jobs).where(anchor_jobs.c.report_fk == report_id)).mappings().first()
        if row is None:
            raise ApplicationError(404, "ANCHOR_NOT_REQUESTED", "No anchor outbox entry exists.")
        if row["state"] == AnchorStatus.CONFIRMED.value:
            return
        raw, tx_hash = row["signed_transaction"], row["signed_tx_hash"]
        if not raw or not tx_hash:
            raw, tx_hash = await asyncio.to_thread(self._signed, report, row, web3, contract, account)
        try:
            receipt = web3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            try:
                web3.eth.send_raw_transaction(raw)
            except Exception:
                try:
                    web3.eth.get_transaction(tx_hash)
                except TransactionNotFound as exc:
                    raise ApplicationError(503, "DISPATCH_UNCERTAIN", "Anchor broadcast outcome is uncertain.", True) from exc
            with self.db.begin() as connection:
                connection.execute(update(anchor_jobs).where(anchor_jobs.c.id == row["id"]).values(state=AnchorStatus.BROADCAST.value))
            try:
                receipt = await asyncio.to_thread(web3.eth.wait_for_transaction_receipt, tx_hash, 20)
            except Exception as exc:
                raise ApplicationError(503, "PENDING_FINALITY", "Anchor receipt is not final yet.", True) from exc
        if int(receipt["status"]) != 1:
            with self.db.begin() as connection:
                connection.execute(update(anchor_jobs).where(anchor_jobs.c.id == row["id"]).values(state=AnchorStatus.FAILED.value))
            raise ApplicationError(409, "TX_REVERTED", "Anchor transaction reverted.")
        exists, policy, previous, sequence = contract.functions.lookup(
            Web3.to_checksum_address(report.manifest.publication.publisher),
            bytes.fromhex(report.core.agent_key_hash[2:]),
            bytes.fromhex(report.report_hash[2:]),
        ).call()
        if not exists or "0x" + bytes(policy).hex() != report.core.policy_hash or "0x" + bytes(previous).hex() != report.core.previous_report_hash:
            raise ApplicationError(409, "ANCHOR_RECORD_MISMATCH", "On-chain anchor record does not match the report.")
        confirmations = web3.eth.block_number - int(receipt["blockNumber"]) + 1
        if confirmations < deployment.confirmation_depth:
            raise ApplicationError(503, "PENDING_FINALITY", "Anchor confirmation depth is not satisfied.", True)
        body = AnchorReceipt(
            report_hash=report.report_hash,
            status=AnchorStatus.CONFIRMED,
            trusted_chain_key="local-demo",
            chain_instance_id=deployment.chain.instance_hash,
            contract=report.manifest.publication.contract,
            publisher=report.manifest.publication.publisher,
            tx_hash=tx_hash,
            sequence=int(sequence),
            block_number=str(receipt["blockNumber"]),
            block_hash=receipt["blockHash"].to_0x_hex(),
            confirmations=confirmations,
        )
        def save(connection):
            if connection.execute(select(anchor_receipts.c.id).where(anchor_receipts.c.anchor_job_fk == row["id"]).limit(1)).first():
                return
            connection.execute(insert(anchor_receipts).values(anchor_job_fk=row["id"], body=body.model_dump(mode="json")))
            connection.execute(update(anchor_jobs).where(anchor_jobs.c.id == row["id"]).values(state=AnchorStatus.CONFIRMED.value))
        await asyncio.to_thread(queue.fenced, lease, save)
