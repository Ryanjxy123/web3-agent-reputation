"""Explicit low-frequency live acceptance of the formal adapter, without scoring or RPC."""

import argparse
import asyncio
import hashlib
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from reputation_core.evidence import canonical_bytes
from reputation_platform.adapters.akashi import PROTOCOLS, AkashiReadonlyAdapter
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient

TX = "0xd01d3e019906321b7d410538aebb696dec806df1099756ec85ac7b2da91df7fc"


async def accept(output: Path, *, resolver=None) -> None:
    output.mkdir(parents=True, exist_ok=False)
    client = SafeHttpClient.public_readonly(enabled=True, resolver=resolver)
    store = EvidenceStore(output)
    results: list[dict[str, Any]] = []
    try:
        for protocol in PROTOCOLS:
            adapter = AkashiReadonlyAdapter(protocol, client, store)
            queries = [{"tx": TX}]
            if protocol == PROTOCOLS[0]:
                queries += [{"tx": TX}, {"hash": hashlib.sha256(secrets.token_bytes(32)).hexdigest()},
                            {"hash": "not-a-sha256"}]
            for query in queries:
                result = await adapter.query(query, uuid4())
                results.append({
                    "protocol": protocol, "capability": adapter.capability_id, "query": query,
                    "observation": result.observation.model_dump(mode="json"),
                    "normalized": result.normalized,
                    "evidence": [record.model_dump(mode="json") for record in result.evidence],
                })
                # This command records transport/normalization, never a business PASS or score.
                (output / "acceptance.json").write_bytes(canonical_bytes({
                    "scope": "task8-formal-adapter-only", "results": results,
                    "identity_verified": False, "business_verified": False,
                }))
                print(protocol, result.observation.http_status,
                      result.observation.reason_code or "RESPONSE_NORMALIZED", flush=True)
                if any(record for record in result.evidence if b'"payment_required":true'
                       in store.read(record)):
                    raise RuntimeError("PAYMENT_STOP")
        positives = [r["normalized"] for r in results if r["query"] == {"tx": TX}]
        if len(positives) != 3 or positives[0] is None or positives.count(positives[0]) != 3:
            raise RuntimeError("LIVE_PROTOCOL_EQUIVALENCE_NOT_CONFIRMED")
        if results[-2]["observation"]["http_status"] != 400:
            raise RuntimeError("LIVE_INVALID_INPUT_REJECTION_NOT_CONFIRMED")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-readonly", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(accept(args.output))


if __name__ == "__main__":
    main()
