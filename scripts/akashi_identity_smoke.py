"""Explicit fixed-target public identity acceptance; never signs, scores or writes a chain."""

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from reputation_core.evidence import canonical_bytes, hash_json
from reputation_core.models import AgentSnapshot, Outcome
from reputation_core.public_identity import (
    AKASHI_HTTP_URL,
    AKASHI_MCP_URL,
    associate_readonly_identity,
)
from reputation_platform.adapters.registries.erc8004 import (
    AKASHI_REF,
    Erc8004RegistryReader,
    PublicRegistryReadResult,
)
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient

ROOT = Path(__file__).resolve().parents[1]


async def accept(output: Path, *, resolver=None) -> PublicRegistryReadResult:
    output.mkdir(parents=True, exist_ok=False)
    store = EvidenceStore(output)
    client = SafeHttpClient.public_readonly(enabled=True, resolver=resolver)
    try:
        result = await Erc8004RegistryReader(ROOT, client, store).read(AKASHI_REF)
        for record in result.evidence:
            store.read(record)
        snapshot = None
        associations = []
        if result.core is not None:
            snapshot = AgentSnapshot(
                snapshot_id=uuid4(), core=result.core, public_identity=result.identity,
                snapshot_hash=hash_json({
                    "core": result.core.model_dump(mode="json"),
                    "public_identity": result.identity.model_dump(mode="json"),
                }),
                evidence_refs=tuple(dict.fromkeys(record.evidence_id for record in result.evidence)),
            )
            associations = [
                associate_readonly_identity(
                    snapshot, target, protocol, openapi_raw=result.openapi_raw,
                    metadata_raw=result.metadata_raw,
                )
                for target, protocol in (
                    (AKASHI_HTTP_URL, "akashi-http-readonly-v1"),
                    (AKASHI_MCP_URL, "akashi-mcp-readonly-v1"),
                )
            ]
        passed = (
            snapshot is not None and snapshot.core.agent_ref == AKASHI_REF
            and snapshot.core.declared_executor is None
            and result.identity.registration_outcome == Outcome.PASS
            and result.identity.metadata_outcome == Outcome.PASS
            and len(associations) == 2
            and all(
                item.registration_outcome == Outcome.PASS and item.endpoint_outcome == Outcome.PASS
                and item.executor_outcome == Outcome.UNKNOWN and item.business_outcome == Outcome.UNKNOWN
                for item in associations
            )
        )
        (output / "acceptance.json").write_bytes(canonical_bytes({
            "scope": "task9-readonly-identity-only", "accepted": passed,
            "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
            "identity": result.identity.model_dump(mode="json"),
            "associations": [item.model_dump(mode="json") for item in associations],
            "evidence": [record.model_dump(mode="json") for record in result.evidence],
        }))
        if not passed:
            raise RuntimeError("PUBLIC_IDENTITY_ACCEPTANCE_NOT_CONFIRMED")
        print("PUBLIC_IDENTITY_SMOKE_PASS: registration/endpoint PASS; executor/business UNKNOWN",
              flush=True)
        return result
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-readonly", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New evidence directory; refuses overwriting prior runs")
    args = parser.parse_args()
    asyncio.run(accept(args.output))


if __name__ == "__main__":
    main()
