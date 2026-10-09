"""Public local deployment and controlled-agent wire contracts; no secrets or I/O."""

from typing import Literal, Self

from pydantic import Field, model_serializer, model_validator

from .base import Hash32, Model, NonzeroAddress, SafeText, UInt256
from .domain import Capability, ChainIdentity


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
    capability_id: Capability = "anchor_record"
    tx_hash: Hash32 | None = None
    executor: NonzeroAddress | None = None
    record_hash: Hash32 | None = None
    tx_status: Literal["SUCCESS", "REVERTED", "PENDING", "NOT_FOUND"] | None = None
    record_exists: bool | None = Field(default=None, strict=True)
    record_matches: bool | None = Field(default=None, strict=True)
    record_request_id: Hash32 | None = None
    record_executor: NonzeroAddress | None = None
    read_block_number: UInt256 | None = None
    read_block_hash: Hash32 | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.capability_id == "anchor_record":
            for name in (
                "capability_id",
                "tx_status",
                "record_exists",
                "record_matches",
                "record_request_id",
                "record_executor",
                "read_block_number",
                "read_block_hash",
            ):
                value.pop(name, None)
        return value

    @model_validator(mode="after")
    def capability_output(self) -> Self:
        if self.capability_id == "anchor_record":
            if any(value is None for value in (self.tx_hash, self.executor, self.record_hash)):
                raise ValueError("anchor_record result requires transaction, executor and hash")
            if any(
                value is not None
                for value in (
                    self.tx_status,
                    self.record_exists,
                    self.record_matches,
                    self.record_request_id,
                    self.record_executor,
                    self.read_block_number,
                    self.read_block_hash,
                )
            ):
                raise ValueError("anchor_record result cannot contain query output")
        else:
            if self.read_block_number is None or self.read_block_hash is None:
                raise ValueError("read result requires block number and hash")
            if self.capability_id == "get_tx_status":
                if (
                    self.tx_hash is None
                    or self.tx_status is None
                    or any(
                        value is not None
                        for value in (
                            self.executor,
                            self.record_hash,
                            self.record_exists,
                            self.record_matches,
                            self.record_request_id,
                            self.record_executor,
                        )
                    )
                ):
                    raise ValueError("get_tx_status requires transaction hash and status only")
            elif (
                any(
                    value is None
                    for value in (
                        self.record_exists,
                        self.record_matches,
                        self.record_hash,
                        self.record_request_id,
                        self.record_executor,
                    )
                )
                or self.tx_hash is not None
                or self.tx_status is not None
                or self.executor is not None
            ):
                raise ValueError("verify_record requires record observation only")
        return self


class ControlledTaskView(Model):
    request_id: Hash32
    accepted: Literal[True] = True
    task_status: Literal["accepted", "running", "succeeded", "failed"]
    status_path: str = Field(pattern=r"^/tasks/0x[0-9a-f]{64}$")
    result: TaskResult | None = None
    reason_code: str | None = None
