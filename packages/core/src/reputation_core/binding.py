"""Pure EIP-712 binding encoding/recovery; clocks and chain evidence are explicit inputs."""

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_keys.exceptions import BadSignature

from .evidence import hash_json
from .models import AgentRef, BindingMessage, Endpoint, ExecutorBinding


def agent_key_hash(ref: AgentRef) -> str:
    return hash_json(ref.model_dump(mode="json"))


def endpoint_hash(endpoint: Endpoint) -> str:
    # endpoint_id is a local label; commit the actual normalized protocol target.
    return hash_json(endpoint.model_dump(mode="json", exclude={"endpoint_id"}))


def typed_data(message: BindingMessage, chain_id: str, registry: str, salt: str, role: int) -> dict:
    if role not in {1, 2}:
        raise ValueError("INVALID_SIGNER_ROLE")
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
                {"name": "salt", "type": "bytes32"},
            ],
            "ExecutorBinding": [
                {"name": "agentKeyHash", "type": "bytes32"},
                {"name": "snapshotHash", "type": "bytes32"},
                {"name": "executor", "type": "address"},
                {"name": "endpointHash", "type": "bytes32"},
                {"name": "executionChainId", "type": "uint256"},
                {"name": "executionChainInstanceHash", "type": "bytes32"},
                {"name": "nonce", "type": "bytes32"},
                {"name": "issuedAt", "type": "uint64"},
                {"name": "deadline", "type": "uint64"},
                {"name": "signerRole", "type": "uint8"},
            ],
        },
        "primaryType": "ExecutorBinding",
        "domain": {
            "name": "Web3AgentReputationBinding",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": registry,
            "salt": salt,
        },
        "message": {
            "agentKeyHash": message.agent_key_hash,
            "snapshotHash": message.snapshot_hash,
            "executor": message.executor,
            "endpointHash": message.endpoint_hash,
            "executionChainId": message.execution_chain_id,
            "executionChainInstanceHash": message.execution_chain_instance_hash,
            "nonce": message.nonce,
            "issuedAt": message.issued_at,
            "deadline": message.deadline,
            "signerRole": role,
        },
    }


def signatures_match(proof: ExecutorBinding) -> bool:
    for role, signature, expected in (
        (1, proof.owner_signature, proof.owner),
        (2, proof.executor_signature, proof.message.executor),
    ):
        try:
            message = encode_typed_data(
                full_message=typed_data(
                    proof.message,
                    proof.domain_chain_id,
                    proof.domain_registry,
                    proof.domain_salt,
                    role,
                )
            )
            recovered = Account.recover_message(message, signature=signature)
        except (ValueError, TypeError, OverflowError, BadSignature):
            return False
        if recovered.lower() != expected:
            return False
    return True
