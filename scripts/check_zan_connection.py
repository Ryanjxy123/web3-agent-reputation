"""Check Base chain ID and head through the project's scoped ZAN read-only client."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_zan_key_file


def main() -> int:
    run = ROOT / "runtime" / ("zan-base-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                             + "-" + secrets.token_hex(4))
    run.mkdir(parents=True)
    targets = tuple(PublicTarget(key, "https://api.zan.top/node/v1/base/mainnet", "POST", json_body={
        "jsonrpc": "2.0", "id": index, "method": method, "params": [],
    }) for index, (key, method) in enumerate((("chain-id", "eth_chainId"), ("head", "eth_blockNumber")), 1))
    result = {"success": False, "expected_chain_id": 8453, "chain_id": None, "block_number": None,
              "request_attempts": 0, "transactions_sent": 0, "automatic_retries": 0, "error": None}
    with SafeHttpClient(targets, enabled=True, zan_key_url_file=load_zan_key_file(),
                        max_requests=2, timeout_seconds=30) as client:
        for target in targets:
            result["request_attempts"] += 1
            observed = client.fetch(target.key, run)
            result["http_status"] = observed.http_status
            if observed.error_kind or observed.http_status != 200 or not observed.body_complete:
                result["error"] = observed.error_kind or "incomplete_rpc_response"
                break
            try:
                data = json.loads((run / observed.response_file).read_bytes())
                if (not isinstance(data, dict) or data.get("jsonrpc") != "2.0"
                        or data.get("id") != target.json_body["id"] or data.get("error")):
                    raise ValueError
                value = data["result"]
                if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
                    raise ValueError
                number = int(value, 16)
            except (ValueError, KeyError, TypeError):
                result["error"] = "invalid_json_rpc_response"
                break
            if target.key == "chain-id":
                result.update(chain_id=number, chain_id_hex=value)
                if number != 8453:
                    result["error"] = "unexpected_chain_id"
                    break
            else:
                result["block_number"] = number
                result["success"] = number > 0
                if not result["success"]:
                    result["error"] = "invalid_block_number"
            network = run / (target.key + ".network.json")
            if network.is_file():
                result["network"] = json.loads(network.read_text(encoding="utf-8"))
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    print("diagnostics_directory=" + str(run))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError):
        raise SystemExit("ZAN check failed; inspect local credential path/configuration without printing private values") from None
