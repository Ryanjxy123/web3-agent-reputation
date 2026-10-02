"""Deterministic JSON and Ethereum Keccak commitments over saved bytes."""
import json
from typing import Any

import rfc8785
from eth_hash.auto import keccak


def canonical_bytes(value: Any) -> bytes:
    return rfc8785.dumps(value)


def hash_bytes(data: bytes) -> str:
    return "0x" + keccak(data).hex()


def hash_json(value: Any) -> str:
    return hash_bytes(canonical_bytes(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def strict_json(data: bytes) -> Any:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    value = json.loads(
        data.decode("utf-8", errors="strict"),
        object_pairs_hook=_pairs,
        parse_constant=_invalid_constant,
    )
    canonical_bytes(value)  # Reject invalid Unicode and integers outside JCS exact range.
    return value
