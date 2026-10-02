"""Explicit protocol IDs, never dynamic imports from agent-supplied metadata."""
from types import MappingProxyType

CAPABILITIES = MappingProxyType({
    "get_tx_status@1": "read",
    "verify_record@1": "read",
    "anchor_record@1": "write",
})
PROTOCOLS = ("controlled-http-v1",)
REGISTRIES = ("demo-registry-v1", "erc8004-v1")


def require_protocol(protocol: str) -> str:
    if protocol not in PROTOCOLS:
        raise ValueError("UNSUPPORTED_PROTOCOL")
    return protocol
