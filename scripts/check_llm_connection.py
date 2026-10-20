"""Free LLM connectivity/model-list check. Never sends an inference request."""

from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_llm_config, load_llm_key_file


def main() -> int:
    config = load_llm_config()
    run = ROOT / "runtime" / ("llm-network-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                             + "-" + secrets.token_hex(4))
    run.mkdir(parents=True)
    target = PublicTarget("models", config.models_endpoint)
    with SafeHttpClient((target,), enabled=True, provider_key_file=load_llm_key_file(),
                        provider_config=config, provider_models_check=True,
                        max_requests=1, timeout_seconds=30) as client:
        observation = client.fetch(target.key, run)
    present = None
    result = {"http_status": observation.http_status, "error": observation.error_kind,
              "model": config.model, "model_present": present, "inference_requests": 0}
    if observation.http_status == 200 and observation.body_complete and not observation.error_kind:
        try:
            data = json.loads((run / observation.response_file).read_bytes())["data"]
            if not isinstance(data, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in data):
                raise ValueError
            present = any(item["id"] == config.model for item in data)
            result.update(model_present=present, result="model_listed" if present else "model_not_listed")
        except (ValueError, KeyError, TypeError):
            result.update(error="invalid_models_response", result="protocol_error")
    else:
        result["result"] = "connection_or_http_error"
    network = run / "models.network.json"
    if network.is_file():
        result["network"] = json.loads(network.read_text(encoding="utf-8"))
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    print("diagnostics_directory=" + str(run))
    return 0 if present else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, PermissionError):
        raise SystemExit("LLM configuration/network setup failed; check local settings without printing private values") from None
