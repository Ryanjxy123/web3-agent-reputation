"""Additional read-only ERC-8004 provenance, separate from executor binding."""

from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from .base import Hash32, Model, SafeText, Version
from .enums import Outcome, Reason

PublicReadonlyProtocol = Literal["akashi-http-readonly-v1", "akashi-mcp-readonly-v1"]
IdentityOutcome = Literal[Outcome.PASS, Outcome.FAIL, Outcome.UNKNOWN]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PublicServiceDeclaration(Model):
    name: SafeText
    endpoint: SafeText
    version: Version | None = None


class PublicRegistrationMetadata(Model):
    type: Literal["https://eips.ethereum.org/EIPS/eip-8004#registration-v1"]
    name: SafeText
    description: SafeText | None = None
    services: tuple[PublicServiceDeclaration, ...] = Field(max_length=20)
    registration_agent_key: SafeText
    x402_support: StrictBool | None = None
    active: StrictBool | None = None
    supported_trust: tuple[SafeText, ...] = Field(max_length=20)


class PublicIdentityRead(Model):
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_standard: Literal["erc8004-v1"] = "erc8004-v1"
    abi_sha256: Sha256
    registry_code_hash: Hash32 | None
    rpc_source: Annotated[str, Field(pattern=r"^[a-zA-Z0-9._:-]{1,200}$")]
    source_hashes: tuple[Hash32, ...] = Field(min_length=1, max_length=64)
    metadata_bytes_hash: Hash32 | None
    openapi_bytes_hash: Hash32 | None = None
    metadata: PublicRegistrationMetadata | None
    registration_outcome: IdentityOutcome
    registration_reason: Reason | None
    metadata_outcome: Literal[Outcome.PASS, Outcome.UNKNOWN]
    metadata_reason: Reason | None

    @model_validator(mode="after")
    def states(self) -> Self:
        for outcome, reason in (
            (self.registration_outcome, self.registration_reason),
            (self.metadata_outcome, self.metadata_reason),
        ):
            if (outcome == Outcome.PASS) != (reason is None):
                raise ValueError("unverified public identity requires a reason")
        if self.metadata_outcome == Outcome.PASS and (
            self.metadata is None or self.metadata_bytes_hash is None
        ):
            raise ValueError("parsed metadata requires its original bytes commitment")
        if self.registration_outcome == Outcome.PASS and self.registry_code_hash is None:
            raise ValueError("verified registration requires the registry code commitment")
        if self.metadata_outcome == Outcome.UNKNOWN and self.metadata is not None:
            raise ValueError("unverified metadata cannot supply trusted declarations")
        if len(set(self.source_hashes)) != len(self.source_hashes):
            raise ValueError("duplicate public identity source hash")
        return self


class ReadonlyIdentityAssociation(Model):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_hash: Hash32
    identity_hash: Hash32 | None
    target_url: SafeText
    protocol: PublicReadonlyProtocol
    openapi_bytes_hash: Hash32 | None = None
    registration_outcome: IdentityOutcome
    registration_reason: Reason | None
    endpoint_outcome: IdentityOutcome
    endpoint_reason: Reason | None
    executor_outcome: Literal[Outcome.UNKNOWN] = Outcome.UNKNOWN
    executor_reason: Literal[Reason.BINDING_UNVERIFIED] = Reason.BINDING_UNVERIFIED
    business_outcome: Literal[Outcome.UNKNOWN] = Outcome.UNKNOWN
    business_reason: Literal[Reason.INSUFFICIENT_SAMPLES] = Reason.INSUFFICIENT_SAMPLES

    @model_validator(mode="after")
    def states(self) -> Self:
        for outcome, reason in (
            (self.registration_outcome, self.registration_reason),
            (self.endpoint_outcome, self.endpoint_reason),
        ):
            if (outcome == Outcome.PASS) != (reason is None):
                raise ValueError("unverified identity association requires a reason")
        if self.endpoint_outcome == Outcome.PASS and (
            self.registration_outcome != Outcome.PASS or self.identity_hash is None
        ):
            raise ValueError("endpoint association requires verified registration provenance")
        return self
