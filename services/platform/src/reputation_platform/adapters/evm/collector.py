"""Read independently through operator RPC; retain raw hex quantities, never Agent claims."""

from reputation_core.evidence import hash_bytes
from reputation_core.models import CaseSlot, EvmReadEvidence, LocalDeployment, Reason
from requests.exceptions import RequestException
from web3.exceptions import Web3Exception
from web3.types import RPCEndpoint

from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.application.local_deploy import local_web3


def collect_task(
    config: LocalDeployment,
    slot: CaseSlot,
    candidate: str | None,
    dispatch_block: str | None = None,
) -> EvmReadEvidence:
    results = {}
    error = None
    if slot.task.capability_id == "get_tx_status":
        candidate = slot.task.query_tx_hash
    if config.chain != slot.expected.execution_chain:
        return EvmReadEvidence(
            candidate_tx_hash=candidate,
            observed_at=timestamp(),
            results={},
            error_reason=Reason.CHAIN_INSTANCE_CHANGED,
        )
    try:
        web3 = local_web3(config.rpc_url)

        def read(label, method, params):
            reply = web3.provider.make_request(RPCEndpoint(method), params)
            if "error" in reply or "result" not in reply:
                raise ValueError("RPC_RESPONSE_UNAVAILABLE")
            results[label] = reply["result"]
            return reply["result"]

        read("chain_id", "eth_chainId", [])
        read("genesis", "eth_getBlockByNumber", ["0x0", False])
        head = read("head", "eth_getBlockByNumber", ["latest", False])
        block_tag = head["number"]
        read("registry_code", "eth_getCode", [config.registry.address, block_tag])
        if slot.task.target_contract is not None:
            read("record_code", "eth_getCode", [slot.task.target_contract, block_tag])
        read(
            "deployment_instance",
            "eth_call",
            [
                {"to": config.registry.address, "data": hash_bytes(b"deploymentInstanceId()")[:10]},
                block_tag,
            ],
        )
        read(
            "pre_dispatch_block",
            "eth_getBlockByNumber",
            [hex(int(slot.expected.pre_dispatch_block)), False],
        )
        if dispatch_block is not None:
            read("dispatch_block", "eth_getBlockByNumber", [hex(int(dispatch_block)), False])
        if slot.task.capability_id != "anchor_record":
            assert slot.task.read_block_number is not None
            read("read_block", "eth_getBlockByHash", [slot.task.read_block_hash, False])
            read(
                "read_canonical",
                "eth_getBlockByNumber",
                [hex(int(slot.task.read_block_number)), False],
            )
        if slot.task.capability_id == "verify_record":
            assert slot.task.read_block_number is not None
            assert slot.task.record_executor is not None and slot.task.record_request_id is not None
            read(
                "record_call",
                "eth_call",
                [
                    {
                        "to": slot.task.target_contract,
                        "data": hash_bytes(b"getRecord(address,bytes32)")[:10]
                        + slot.task.record_executor[2:].rjust(64, "0")
                        + slot.task.record_request_id[2:],
                    },
                    hex(int(slot.task.read_block_number)),
                ],
            )
            # A numbered eth_call must still refer to the same canonical block afterwards.
            read(
                "read_canonical",
                "eth_getBlockByNumber",
                [hex(int(slot.task.read_block_number)), False],
            )
        if candidate is not None:
            read("transaction", "eth_getTransactionByHash", [candidate])
            receipt = read("receipt", "eth_getTransactionReceipt", [candidate])
            if receipt is not None:
                read("receipt_block", "eth_getBlockByHash", [receipt["blockHash"], False])
                read("receipt_canonical", "eth_getBlockByNumber", [receipt["blockNumber"], False])
        # Re-read after receipt collection: confirmations use this fixed final head.
        read("head", "eth_getBlockByNumber", ["latest", False])
    except (RequestException, Web3Exception, OSError, KeyError, TypeError, ValueError):
        error = Reason.PLATFORM_RPC_ERROR
    return EvmReadEvidence(
        candidate_tx_hash=candidate, observed_at=timestamp(), results=results, error_reason=error
    )
