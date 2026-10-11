"""Collect only the fixed historical Base proof through the formal safe outlet."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import httpx
from reputation_core.models import EvidenceRecord
from reputation_core.record_verifier import hex_data, quantity

from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.audited_readonly import (
    EvidencePersistenceError,
    audited_readonly_request,
)
from reputation_platform.infrastructure.network.safe_http import (
    AKASHI_PROOF_TX,
    PUBLIC_RPC_ORIGIN,
    NetworkPolicyError,
    SafeHttpClient,
    decode_public_json,
)

if TYPE_CHECKING:
    from reputation_core.models.public_evaluation import PublicReadonlyCaseSlot

PROTOCOL = "akashi-business-readonly-v1"


async def collect_public_task(
    client: SafeHttpClient, store: EvidenceStore, slot: "PublicReadonlyCaseSlot",
    *, records: list[EvidenceRecord] | None = None,
    register_record: Callable[[EvidenceRecord], Awaitable[EvidenceRecord]] | None = None,
) -> tuple[EvidenceRecord, ...]:
    """Retain partial reads as UNKNOWN evidence; never follow a service-supplied tx."""
    if not client.is_public_readonly:
        raise NetworkPolicyError("PUBLIC_READONLY_REQUIRED")
    if "tx" not in slot.task.query:
        return ()
    if slot.task.query != {"tx": AKASHI_PROOF_TX}:
        raise NetworkPolicyError("PUBLIC_TRANSACTION_NOT_ALLOWED")
    if records is None:
        records = []
    identifier = 0

    async def rpc(method, params):
        nonlocal identifier
        identifier += 1
        response = await audited_readonly_request(
            client, store, protocol=PROTOCOL, capability_id="verify_record",
            method="POST", origin=PUBLIC_RPC_ORIGIN, path="/",
            payload={"jsonrpc": "2.0", "id": identifier, "method": method, "params": params},
            records=records, register_record=register_record,
        )
        if response.status != 200 or response.audit.get("payment_required"):
            raise NetworkPolicyError("PUBLIC_BUSINESS_RPC_UNAVAILABLE")
        value = decode_public_json(response)
        if (set(value) != {"jsonrpc", "id", "result"} or value["jsonrpc"] != "2.0"
                or type(value["id"]) is not int or value["id"] != identifier):
            raise NetworkPolicyError("INVALID_RPC_ENVELOPE")
        return value["result"]

    tag = hex(int(slot.task.read_block_number))
    try:
        await rpc("eth_chainId", [])
        await rpc("eth_getBlockByNumber", ["0x0", False])
        await rpc("eth_getBlockByNumber", [tag, False])
        await rpc("eth_getTransactionByHash", [AKASHI_PROOF_TX])
        receipt = await rpc("eth_getTransactionReceipt", [AKASHI_PROOF_TX])
        if not isinstance(receipt, dict):
            raise ValueError("PUBLIC_RECEIPT_UNAVAILABLE")
        block_hash = hex_data(receipt["blockHash"], 32)
        block_tag = hex(quantity(receipt["blockNumber"]))
        await rpc("eth_getBlockByHash", [block_hash, False])
        await rpc("eth_getBlockByNumber", [block_tag, False])
        # The head is a frozen read, and is checked again after the receipt reads.
        await rpc("eth_getBlockByNumber", [tag, False])
    except EvidencePersistenceError:
        raise
    except (httpx.HTTPError, TimeoutError, NetworkPolicyError, ValueError, TypeError, KeyError):
        records.append(store.prepare_json(
            {"protocol": PROTOCOL, "capability_id": "verify_record",
             "query": slot.task.query, "read_block_number": slot.task.read_block_number,
             "read_block_hash": slot.task.read_block_hash, "reason_code": "PLATFORM_RPC_ERROR"},
            "public-business-collection-error", timestamp(), "public-http",
        ))
    return tuple(records)
