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
    if (
        config.chain != slot.expected.execution_chain
        or config.record.address != slot.task.target_contract
    ):
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
        read("record_code", "eth_getCode", [config.record.address, block_tag])
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
