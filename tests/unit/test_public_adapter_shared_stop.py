"""A halted protocol session closes the shared run outlet before another protocol."""

import json
from uuid import uuid4

import httpx
import pytest
from reputation_core.models import Reason
from reputation_platform.adapters.akashi import PROTOCOLS, AkashiReadonlyAdapter
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient

from tests.unit.test_public_adapter import TX


@pytest.mark.parametrize("failure", ["payment", "unsafe", "timeout"])
async def test_mcp_halt_prevents_http_sockets_on_the_shared_client(tmp_path, monkeypatch, failure):
    from reputation_platform.infrastructure.network import safe_http
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.path == "/mcp"
        body = json.loads(request.content)
        method = body["method"]
        if failure == "timeout":
            raise httpx.ReadTimeout("offline timeout", request=request)
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25"}
        elif method == "notifications/initialized":
            return httpx.Response(202)
        elif method == "tools/list":
            annotations = {"readOnlyHint": failure != "unsafe"}
            if failure == "payment":
                annotations["paymentRequired"] = True
            result = {"tools": [{"name": "find_proof", "annotations": annotations}]}
        else:
            pytest.fail("Halted discovery reached a business tool")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    client = SafeHttpClient.public_readonly(
        enabled=True, transport=httpx.MockTransport(respond), resolver=lambda _: ["1.1.1.1"],
    )
    store = EvidenceStore(tmp_path)
    mcp, http = (AkashiReadonlyAdapter(protocol, client, store) for protocol in (PROTOCOLS[1], PROTOCOLS[0]))
    try:
        result = await mcp.query({"tx": TX}, uuid4())
        assert result.observation.reason_code == (
            Reason.SERVICE_TIMEOUT if failure == "timeout" else Reason.UNSUPPORTED_PROTOCOL
        )
        assert client.public_stop_reason is not None
        sockets = len(calls)
        blocked = await http.query({"tx": TX}, uuid4())
        assert not blocked.observation.accepted and len(calls) == sockets
        assert blocked.observation.reason_code == Reason.UNSUPPORTED_PROTOCOL
    finally:
        await client.close()
