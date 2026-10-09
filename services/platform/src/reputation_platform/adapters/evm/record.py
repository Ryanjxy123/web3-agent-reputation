"""Locate a previously dispatched request without broadcasting any transaction."""

import json
from pathlib import Path

from reputation_core.models import CaseSlot, LocalDeployment
from requests.exceptions import RequestException
from web3 import Web3
from web3.exceptions import Web3Exception

from reputation_platform.application.errors import ApplicationError
from reputation_platform.application.local_deploy import contract_abi, local_web3, verify_deployment


def reconcile_record(root: Path, config: LocalDeployment, slot: CaseSlot) -> dict:
    if config.chain != slot.expected.execution_chain or slot.task.target_contract is None:
        raise ApplicationError(
            409, "CHAIN_INSTANCE_CHANGED", "Execution chain configuration changed."
        )
    try:
        web3 = local_web3(config.rpc_url)
        verify_deployment(web3, config, root)
        block = web3.eth.get_block("latest")
        registry = web3.eth.contract(
            address=Web3.to_checksum_address(slot.task.target_contract),
            abi=contract_abi(root, "DemoRecordRegistry"),
        )
        exists, digest = registry.functions.getRecord(
            Web3.to_checksum_address(slot.expected.executor), slot.task.request_id
        ).call(block_identifier=block["number"])
        logs = (
            registry.events.RecordAnchored().get_logs(
                from_block=int(slot.expected.pre_dispatch_block),
                to_block=block["number"],
                argument_filters={
                    "executor": Web3.to_checksum_address(slot.expected.executor),
                    "requestId": bytes.fromhex(slot.task.request_id[2:]),
                },
            )
            if exists
            else []
        )
        if web3.eth.get_block(block["number"])["hash"] != block["hash"]:
            raise ApplicationError(503, "PLATFORM_RPC_ERROR", "Reconciliation block changed.", True)
        return {
            "chain_instance": config.chain.instance_hash,
            "contract": slot.task.target_contract,
            "executor": slot.expected.executor,
            "request_id": slot.task.request_id,
            "exists": exists,
            "record_hash": "0x" + bytes(digest).hex(),
            "block_number": str(block["number"]),
            "block_hash": block["hash"].to_0x_hex(),
            "logs": [json.loads(Web3.to_json(dict(log))) for log in logs],
            "candidate_tx_hash": logs[0]["transactionHash"].to_0x_hex() if len(logs) == 1 else None,
        }
    except ApplicationError:
        raise
    except (RequestException, Web3Exception, OSError):
        raise ApplicationError(
            503, "PLATFORM_RPC_ERROR", "Trusted RPC reconciliation is unavailable.", True
        ) from None
    except ValueError:
        raise ApplicationError(
            409, "CHAIN_INSTANCE_CHANGED", "Execution chain instance changed."
        ) from None
