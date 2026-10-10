import hashlib
import json

import pytest
from reputation_platform.infrastructure.network.safe_http import HttpObservation

from scripts.readonly_akashi_poc import PaymentRequired, Probe, payment_requested


@pytest.mark.parametrize("status", [200, 402])
async def test_probe_saves_actual_bytes_and_stops_on_payment(tmp_path, monkeypatch, status):
    body = b'{"public":"evidence"}'
    calls = []

    class Client:
        async def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return HttpObservation(status, body)

    monkeypatch.setattr(
        "scripts.readonly_akashi_poc.SafeHttpClient.readonly_poc", lambda: Client()
    )

    async def no_wait(_):
        pass

    monkeypatch.setattr("scripts.readonly_akashi_poc.asyncio.sleep", no_wait)
    probe = Probe(tmp_path / "new-run")
    if status == 402:
        with pytest.raises(PaymentRequired):
            await probe.request("proof", "GET", "https://anchor.akashi-notari.com", "/proof")
        with pytest.raises(RuntimeError, match="stopped"):
            await probe.request("again", "GET", "https://anchor.akashi-notari.com", "/health")
    else:
        await probe.request("proof", "GET", "https://anchor.akashi-notari.com", "/proof")
    observation = json.loads((probe.output / "observations.json").read_text(encoding="utf-8"))[0]
    assert len(calls) == 1
    assert observation["status"] == status
    if status == 402:
        assert observation["body_not_read"] is True
        assert "body_file" not in observation
    else:
        assert (probe.output / observation["body_file"]).read_bytes() == body
        assert observation["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert observation["finished_utc"] >= observation["started_utc"]


def test_probe_refuses_to_overwrite_evidence(tmp_path):
    with pytest.raises(FileExistsError):
        Probe(tmp_path)


def test_mcp_payment_offer_is_detected_but_tool_documentation_is_not():
    assert payment_requested({"result": {"structuredContent": {"x402Version": 2, "accepts": []}}})
    assert not payment_requested({"tools": [{"name": "anchor_hash", "description": "Paid with x402"}]})


@pytest.mark.parametrize("value", [
    {"error": {"code": "PAYMENT_REQUIRED", "message": "Payment required"}},
    {"code": "PAYMENT_REQUIRED"},
    {"result": {"isError": True, "content": [{"type": "text", "text": "Payment required"}]}},
])
def test_machine_or_mcp_error_payment_requirement_stops(value):
    assert payment_requested(value)


async def test_evidence_write_failure_terminates_probe(tmp_path, monkeypatch):
    class Client:
        async def request(self, *args, **kwargs):
            return HttpObservation(200, b'{"ok":true}')
    monkeypatch.setattr("scripts.readonly_akashi_poc.SafeHttpClient.readonly_poc", lambda: Client())
    async def no_wait(_):
        pass
    monkeypatch.setattr("scripts.readonly_akashi_poc.asyncio.sleep", no_wait)
    def failed_write(*_):
        raise OSError("disk full")
    monkeypatch.setattr("pathlib.Path.write_bytes", failed_write)
    probe = Probe(tmp_path / "failed")
    with pytest.raises(OSError, match="disk full"):
        await probe.request("health", "GET", "https://anchor.akashi-notari.com", "/health")


async def test_probe_budget_stops_before_transport(tmp_path):
    probe = Probe(tmp_path / "budget")
    try:
        probe.observations = [{}] * 64
        with pytest.raises(RuntimeError, match="budget"):
            await probe.request("extra", "GET", "https://anchor.akashi-notari.com", "/health")
    finally:
        await probe.client.close()
