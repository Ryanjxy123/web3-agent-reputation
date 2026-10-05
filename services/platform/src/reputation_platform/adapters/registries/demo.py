"""Read one canonical block from the operator-configured local registry only."""

import base64
import binascii
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, ValidationError
from reputation_core.evidence import hash_json, strict_json
from reputation_core.models import AgentRef, Endpoint, LocalDeployment, SnapshotCore
from reputation_core.models.base import Model, NonzeroAddress, SafeText
from requests.exceptions import RequestException
from web3 import Web3
from web3.exceptions import ContractLogicError, Web3Exception

from reputation_platform.application.errors import ApplicationError
from reputation_platform.application.local_deploy import contract_abi, local_web3, verify_deployment
from reputation_platform.configuration import controlled_fixture_ports


class DemoMetadata(Model):
    name: SafeText
    description: SafeText
    capabilities: tuple[SafeText, ...] = Field(min_length=1, max_length=10)
    declared_executor: NonzeroAddress
    endpoints: tuple[Endpoint, ...] = Field(min_length=1, max_length=10)


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DemoRegistryReader:
    def __init__(self, root: Path, deployment: LocalDeployment):
        self.root, self.deployment = root, deployment

    def read(self, ref: AgentRef) -> tuple[SnapshotCore, dict]:
        deployment = self.deployment
        if (
            ref.chain_id != deployment.chain.chain_id
            or ref.registry_address != deployment.registry.address
        ):
            raise ApplicationError(
                409, "UNSUPPORTED_REGISTRY", "Only the configured demo registry can be read."
            )
        try:
            web3 = local_web3(deployment.rpc_url)
            verify_deployment(web3, deployment, self.root)
            block = web3.eth.get_block("latest")
            number, block_hash = block["number"], block["hash"].to_0x_hex()
            registry = web3.eth.contract(
                address=Web3.to_checksum_address(ref.registry_address),
                abi=contract_abi(self.root, "DemoAgentRegistry"),
            )
            instance = registry.functions.deploymentInstanceId().call(block_identifier=number)
            if "0x" + bytes(instance).hex() != deployment.chain.deployment_instance_id:
                raise ValueError("CHAIN_INSTANCE_MISMATCH")
            identifier = int(ref.agent_id)
            owner = registry.functions.ownerOf(identifier).call(block_identifier=number).lower()
            uri = registry.functions.agentURI(identifier).call(block_identifier=number)
            revision = registry.functions.revisionOf(identifier).call(block_identifier=number)
            executor = (
                registry.functions.declaredExecutorOf(identifier)
                .call(block_identifier=number)
                .lower()
            )
            owner_code = web3.eth.get_code(Web3.to_checksum_address(owner), number).to_0x_hex()
            executor_code = web3.eth.get_code(
                Web3.to_checksum_address(executor), number
            ).to_0x_hex()
            if web3.eth.get_block(number)["hash"].to_0x_hex() != block_hash:
                raise ApplicationError(503, "REORG_DETECTED", "Registry read block changed.", True)
        except ApplicationError:
            raise
        except ContractLogicError:
            raise ApplicationError(
                404, "REGISTRY_AGENT_NOT_FOUND", "Registry identity is unavailable."
            ) from None
        except (RequestException, Web3Exception, OSError):
            raise ApplicationError(
                503, "PLATFORM_RPC_ERROR", "Trusted RPC is unavailable.", True
            ) from None
        except ValueError:
            raise ApplicationError(
                409, "CHAIN_INSTANCE_MISMATCH", "Configured chain identity changed."
            ) from None
        try:
            prefix = "data:application/json;base64,"
            if not uri.startswith(prefix) or len(uri) > 2000:
                raise ValueError("unsupported metadata URI")
            data = strict_json(base64.b64decode(uri[len(prefix) :], validate=True))
            metadata = DemoMetadata.model_validate(data)
            if metadata.declared_executor != executor:
                raise ValueError("executor declaration differs")
            ids = [endpoint.endpoint_id for endpoint in metadata.endpoints]
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate endpoint")
            allowed_ports = set(controlled_fixture_ports())
            for endpoint in metadata.endpoints:
                if (
                    endpoint.scheme != "http"
                    or endpoint.host not in {"127.0.0.1", "fixture-a", "fixture-d"}
                    or endpoint.port not in allowed_ports
                    or endpoint.path != "/tasks"
                ):
                    raise ValueError("uncontrolled endpoint")
        except (ValueError, TypeError, ValidationError, binascii.Error, RecursionError):
            raise ApplicationError(
                422, "UNSUPPORTED_METADATA", "Metadata does not match the controlled demo schema."
            ) from None
        normalized = metadata.model_dump(mode="json")
        core = SnapshotCore(
            agent_ref=ref,
            source_type="controlled",
            owner=owner,
            declared_executor=executor,
            agent_uri=uri,
            registry_revision=revision,
            metadata_hash=hash_json(normalized),
            normalized_metadata=normalized,
            endpoints=metadata.endpoints,
            read_block_number=str(number),
            read_block_hash=block_hash,
            captured_at=timestamp(),
            registry_chain=deployment.chain,
        )
        return core, {
            "snapshot_core": core.model_dump(mode="json"),
            "owner_code": owner_code,
            "executor_code": executor_code,
            "read_method": "eth_call_at_block_number",
        }
