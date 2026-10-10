"""Explicit, bounded, free read-only Akashi investigation; never run by CI."""

import argparse
import asyncio
import hashlib
import json
import re
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eth_abi import decode
from eth_abi.exceptions import DecodingError
from reputation_core.evidence import strict_json
from reputation_core.record_verifier import hex_data, quantity
from reputation_platform.infrastructure.network.safe_http import POC_SOURCE_REF, SafeHttpClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AKASHI = "https://anchor.akashi-notari.com"
RAW = "https://raw.githubusercontent.com"
GITHUB = "https://api.github.com"
BASE_RPC = "https://mainnet.base.org"
REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
AGENT_ID = 98097
REGISTRATION_URI = AKASHI + "/.well-known/agent-registration.json"
SOURCE_FILES = {
    "constants-usdc": "contracts/registry/constants-usdc.json",
    "constants-eth": "contracts/registry/constants.json",
    "contract-usdc": "contracts/registry/contracts/VerifierRegistryUSDC.sol",
    "contract-eth": "contracts/registry/contracts/VerifierRegistry.sol",
    "worker-abi": "workers/anchor/src/abi.js",
    "worker-source": "workers/anchor/src/index.js",
    "worker-config": "workers/anchor/wrangler.toml",
    "register-script": "contracts/registry/scripts/register-agent.js",
}


class PaymentRequired(RuntimeError):
    pass


def payment_requested(value):
    if isinstance(value, dict):
        if "x402Version" in value and "accepts" in value:
            return True
        if value.get("code") in (402, "402", "payment_required", "PAYMENT_REQUIRED"):
            return True
        for name in ("error", "message"):
            text = value.get(name)
            if isinstance(text, str) and re.search(r"payment[ _-]+required", text, re.I):
                return True
        if value.get("isError") is True:
            content = value.get("content")
            for item in content if isinstance(content, list) else []:
                if (isinstance(item, dict) and isinstance(item.get("text"), str)
                        and re.search(r"payment[ _-]+required", item["text"], re.I)):
                    return True
        return any(payment_requested(child) for child in value.values())
    return isinstance(value, list) and any(payment_requested(child) for child in value)


class Probe:
    def __init__(self, output: Path):
        output.mkdir(parents=True, exist_ok=False)
        self.output = output
        self.client = SafeHttpClient.readonly_poc()
        self.observations: list[dict] = []
        self.stopped = False

    async def request(self, label, method, origin, path, *, payload=None, headers=None):
        if self.stopped or len(self.observations) >= 64:
            raise RuntimeError("PoC stopped or request budget exhausted")
        await asyncio.sleep(1)
        started = datetime.now(UTC).isoformat()
        timer = time.monotonic()
        entry = {
            "label": label, "method": method, "origin": origin, "path": path,
            "request_json": payload, "started_utc": started,
        }
        response = None
        try:
            response = await self.client.request(
                method, origin, path, json=payload, headers=headers
            )
        except Exception as exc:
            entry.update({"status": None, "error_type": type(exc).__name__, "error": str(exc)})
        else:
            entry.update({"status": response.status, "content_type": response.content_type})
            if response.status == 402:
                entry.update({"body_not_read": True, "reason": "PAYMENT_STOP"})
            else:
                name = f"{len(self.observations) + 1:03d}-{label}.body"
                (self.output / name).write_bytes(response.body)
                entry.update({
                    "body_file": name, "body_sha256": hashlib.sha256(response.body).hexdigest(),
                    "body_bytes": len(response.body),
                })
        finally:
            entry["elapsed_ms"] = round((time.monotonic() - timer) * 1000)
            entry["finished_utc"] = datetime.now(UTC).isoformat()
            self.observations.append(entry)
            (self.output / "observations.json").write_text(
                json.dumps(self.observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(f"{label}: status={entry['status']} elapsed_ms={entry['elapsed_ms']}", flush=True)
        if response is not None and response.status == 402:
            self.stopped = True
            raise PaymentRequired("HTTP 402: stopped without payment")
        if response is not None:
            try:
                payment = payment_requested(strict_json(response.body))
            except (ValueError, RecursionError):
                payment = False
            if payment:
                self.stopped = True
                raise PaymentRequired("Payment requirement: stopped without payment")
        return response


async def discover(probe: Probe):
    targets = [
        ("official-readme", RAW, f"/self-reality/verifier/{POC_SOURCE_REF}/README.md"),
        ("anchor-readme", RAW, f"/self-reality/verifier/{POC_SOURCE_REF}/workers/anchor/README.md"),
        ("official-head", GITHUB, "/repos/self-reality/verifier/commits/main"),
        ("official-tree", GITHUB, "/repos/self-reality/verifier/git/trees/main?recursive=1"),
        ("health", AKASHI, "/health"),
        ("openapi", AKASHI, "/openapi.json"),
        ("llms", AKASHI, "/llms.txt"),
        ("registration", AKASHI, "/.well-known/agent-registration.json"),
    ]
    responses = {}
    for label, origin, path in targets:
        responses[label] = await probe.request(label, "GET", origin, path)
    for label, name in SOURCE_FILES.items():
        responses[label] = await probe.request(
            label, "GET", RAW, f"/self-reality/verifier/{POC_SOURCE_REF}/{name}"
        )
    return responses


def response_json(response):
    if response is None or response.status != 200:
        return None
    try:
        return strict_json(response.body)
    except (ValueError, RecursionError):
        return None


async def rpc(probe, label, method, params):
    identifier = len(probe.observations) + 1
    response = await probe.request(label, "POST", BASE_RPC, "/", payload={
        "jsonrpc": "2.0", "id": identifier, "method": method, "params": params,
    })
    value = response_json(response)
    if (not isinstance(value, dict) or value.get("jsonrpc") != "2.0"
            or value.get("id") != identifier or "error" in value):
        return None
    return value.get("result")


async def mcp(probe, label, method, params):
    identifier = len(probe.observations) + 1
    response = await probe.request(label, "POST", AKASHI, "/mcp", payload={
        "jsonrpc": "2.0", "id": identifier, "method": method, "params": params,
    })
    value = response_json(response)
    if (not isinstance(value, dict) or value.get("jsonrpc") != "2.0"
            or value.get("id") != identifier or "error" in value):
        return None
    return value.get("result")


async def business(probe, descriptions):
    from scripts.akashi_assertions import normalize_proof, verify_proof

    summary: dict[str, Any] = {"state": "PARTIAL", "source_commit": POC_SOURCE_REF, "cases": {}}
    cases = summary["cases"]
    chain_id = await rpc(probe, "chain-id", "eth_chainId", [])
    head = await rpc(probe, "chain-head", "eth_getBlockByNumber", ["latest", False])
    initialized = await mcp(probe, "mcp-initialize", "initialize", {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "web3-agent-reputation-readonly-poc", "version": "1.0"},
    })
    tools = await mcp(probe, "mcp-tools", "tools/list", {})
    tool_list = tools.get("tools") if isinstance(tools, dict) else None
    tool_available = (
        isinstance(initialized, dict) and initialized.get("protocolVersion") == "2025-11-25"
        and isinstance(tool_list, list) and any(
            t.get("name") == "find_proof" and isinstance(t.get("annotations"), dict)
            and t["annotations"].get("readOnlyHint") is True
            for t in tool_list if isinstance(t, dict)
        )
    )
    summary["service_accessible"] = response_json(descriptions.get("health")) == {"ok": True}
    summary["mcp_find_proof_discovered"] = tool_available

    source = descriptions.get("worker-source")
    candidate = re.search(rb"txHash: '(0x[0-9a-f]{64})'", source.body) if source and source.status == 200 else None
    tx_hash = candidate.group(1).decode() if candidate else None
    if tx_hash:
        tx = await rpc(probe, "positive-tx", "eth_getTransactionByHash", [tx_hash])
        receipt = await rpc(probe, "positive-receipt", "eth_getTransactionReceipt", [tx_hash])
        block = canonical = None
        if isinstance(receipt, dict):
            block = await rpc(probe, "receipt-block", "eth_getBlockByHash", [receipt.get("blockHash"), False])
            canonical = await rpc(probe, "canonical-block", "eth_getBlockByNumber", [receipt.get("blockNumber"), False])
        evidence = {"chain_id": chain_id, "head": head, "tx": tx, "receipt": receipt,
                    "receipt_block": block, "canonical_block": canonical}
        (probe.output / "chain-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
        proofs = []
        for index in range(3):
            result = response_json(await probe.request(
                f"positive-http-{index + 1}", "GET", AKASHI, "/proof?tx=" + tx_hash
            ))
            try:
                normalized = normalize_proof(result)
                proofs.append(normalized)
                cases[f"positive-{index + 1}"] = verify_proof(normalized, {"tx": tx_hash}, evidence)
            except (ValueError, TypeError, KeyError):
                cases[f"positive-{index + 1}"] = {"status": "UNKNOWN", "reason": "HTTP_PROTOCOL_UNAVAILABLE"}
        if len(proofs) == 3:
            cases["repeat"] = {"status": "PASS" if proofs[0] == proofs[1] == proofs[2] else "FAIL",
                               "reason": "THREE_OBSERVATIONS_ONLY"}
        if proofs and tool_available:
            result = await mcp(probe, "positive-mcp", "tools/call", {
                "name": "find_proof", "arguments": {"tx": tx_hash},
            })
            try:
                normalized = normalize_proof(result, mcp=True)
                cases["http-mcp"] = {"status": "PASS" if normalized == proofs[0] else "FAIL",
                                     "reason": "NORMALIZED_BUSINESS_FIELDS"}
                cases["positive-mcp"] = verify_proof(normalized, {"tx": tx_hash}, evidence)
            except (ValueError, TypeError, KeyError):
                cases["http-mcp"] = {"status": "UNKNOWN", "reason": "MCP_PROTOCOL_UNAVAILABLE"}
    else:
        cases["positive"] = {"status": "UNKNOWN", "reason": "NO_OFFICIAL_CANDIDATE"}

    random_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    random_result = response_json(await probe.request(
        "random-hash", "GET", AKASHI, "/proof?hash=" + random_hash
    ))
    cases["random-query"] = {"status": "UNKNOWN", "reason": "GLOBAL_ABSENCE_NOT_ESTABLISHED",
                             "requested_hash": random_hash, "response": random_result}
    try:
        random_normalized = normalize_proof(random_result)
        reasonable = (random_result.get("hash") == random_hash
                      and random_normalized.get("anchored") is False
                      and not random_normalized.get("proofs")
                      and bool(random_result.get("searched")))
        cases["random-response"] = {"status": "PASS" if reasonable else "UNKNOWN",
                                    "reason": "BOUNDED_SEARCH_RESPONSE_ONLY"}
    except (ValueError, TypeError, KeyError, AttributeError):
        cases["random-response"] = {"status": "UNKNOWN", "reason": "HTTP_PROTOCOL_UNAVAILABLE"}
    invalid = await probe.request("invalid-hash", "GET", AKASHI, "/proof?hash=not-a-sha256")
    try:
        error = strict_json(invalid.body) if invalid is not None else None
    except (ValueError, RecursionError):
        error = None
    cases["invalid-input"] = {
        "status": "PASS" if invalid is not None and invalid.status == 400
        and isinstance(error, dict) and isinstance(error.get("error"), str) else "UNKNOWN",
        "reason": "INPUT_REJECTION",
    }

    identity: dict[str, Any] = {"status": "UNKNOWN", "reason": "REGISTRATION_NOT_VERIFIED"}
    if chain_id == "0x2105" and isinstance(head, dict):
        block_number = head.get("number")
        owner_raw = await rpc(probe, "identity-owner", "eth_call", [{
            "to": REGISTRY, "data": "0x6352211e" + format(AGENT_ID, "064x"),
        }, block_number])
        uri_raw = await rpc(probe, "identity-uri", "eth_call", [{
            "to": REGISTRY, "data": "0xc87b56dd" + format(AGENT_ID, "064x"),
        }, block_number])
        code = await rpc(probe, "identity-code", "eth_getCode", [REGISTRY, block_number])
        try:
            owner = decode(["address"], bytes.fromhex(owner_raw[2:]))[0]
            uri = decode(["string"], bytes.fromhex(uri_raw[2:]))[0]
            quantity(block_number)
            hex_data(head.get("hash"), 32)
            code = hex_data(code)
            registration = response_json(descriptions.get("registration"))
            claimed = {"agentId": AGENT_ID, "agentRegistry": f"eip155:8453:{REGISTRY}"}
            if (code and code != "0x" and int(owner, 16) != 0 and uri == REGISTRATION_URI
                    and isinstance(registration, dict) and claimed in registration.get("registrations", [])):
                identity = {"status": "PASS", "reason": "OWNER_AND_URI_READ_AT_FIXED_BLOCK",
                            "chain_id": 8453, "registry": REGISTRY, "agent_id": AGENT_ID,
                            "owner": owner, "token_uri": uri, "block_number": block_number,
                            "block_hash": head.get("hash")}
        except (ValueError, TypeError, KeyError, DecodingError):
            pass
    summary["erc8004_registration"] = identity
    positive_keys = ["positive-1", "positive-2", "positive-3", "repeat", "http-mcp", "positive-mcp", "invalid-input", "random-response"]
    verified_positive = all(cases.get(key, {}).get("confirmed_proofs")
                            for key in ("positive-1", "positive-2", "positive-3", "positive-mcp"))
    if verified_positive and all(cases.get(key, {}).get("status") == "PASS" for key in positive_keys):
        summary["state"] = "COMPLETED_READONLY_POC"
    summary["limits"] = ["No formal score or database integration", "Three repeats do not establish long-term availability",
                         "Random lookup does not establish whole-chain absence", "Registration does not establish executor binding"]
    return summary


async def run(output: Path):
    probe = Probe(output)
    try:
        descriptions = await discover(probe)
        summary = await business(probe, descriptions)
    except PaymentRequired as exc:
        summary = {"state": "BLOCKED_EXTERNAL", "reason": str(exc), "payment_attempted": False}
    finally:
        await probe.client.close()
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New evidence directory; refuses overwriting prior runs")
    args = parser.parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
