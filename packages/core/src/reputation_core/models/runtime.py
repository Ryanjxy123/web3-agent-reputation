"""Public local deployment and controlled-agent wire contracts; no secrets or I/O."""

from typing import Literal

from pydantic import Field

from .base import Hash32, Model, NonzeroAddress, SafeText, UInt256
from .domain import ChainIdentity


class DeployedContract(Model):
    address: NonzeroAddress
    code_hash: Hash32
    transaction_hash: Hash32
    block_number: UInt256
    block_hash: Hash32


class LocalDeployment(Model):
    schema_version: Literal["local-deployment-v1"] = "local-deployment-v1"
    rpc_url: SafeText
    chain: ChainIdentity
    registry: DeployedContract
    record: DeployedContract
    anchor: DeployedContract
    admin: NonzeroAddress
    evaluator: NonzeroAddress
    platform_instance_id: Hash32
    confirmation_depth: int = Field(strict=True, ge=1, le=100, default=1)


class TaskResult(Model):
    chain_id: UInt256
    tx_hash: Hash32
    executor: NonzeroAddress
    record_hash: Hash32


class ControlledTaskView(Model):
    request_id: Hash32
    accepted: Literal[True] = True
    task_status: Literal["accepted", "running", "succeeded", "failed"]
    status_path: str = Field(pattern=r"^/tasks/0x[0-9a-f]{64}$")
    result: TaskResult | None = None
    reason_code: str | None = None
