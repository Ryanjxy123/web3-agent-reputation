"""Strict JSON primitives shared by every process."""
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field


def lower_address(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def uint256(value: str) -> str:
    if int(value) >= 2**256:
        raise ValueError("outside uint256 range")
    return value


def utc_timestamp(value: str) -> str:
    # Pattern fixes wire precision; parsing also rejects impossible calendar dates.
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def nonzero(value: str) -> str:
    if int(value[2:], 16) == 0:
        raise ValueError("zero value is not allowed")
    return value


Address = Annotated[str, BeforeValidator(lower_address), Field(pattern=r"^0x[0-9a-f]{40}$")]
NonzeroAddress = Annotated[Address, AfterValidator(nonzero)]
Hash32 = Annotated[str, Field(pattern=r"^0x[0-9a-f]{64}$")]
Challenge = Annotated[Hash32, AfterValidator(nonzero)]
UInt256 = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,77})$"), AfterValidator(uint256)]
Timestamp = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"),
    AfterValidator(utc_timestamp),
]
Count = Annotated[int, Field(strict=True, ge=0, le=2**53-1)]
BasisPoints = Annotated[int, Field(strict=True, ge=0, le=10000)]
Version = Annotated[str, Field(min_length=1, max_length=100)]
SafeText = Annotated[str, Field(min_length=1, max_length=2000)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
