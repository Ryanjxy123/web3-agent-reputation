"""Local operator configuration; database credentials never enter public contracts."""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def load_database_url() -> str:
    value = os.environ.get("REPUTATION_DATABASE_URL")
    if value is None:
        path = PROJECT_ROOT / "runtime/platform-config/database-url.txt"
        if not path.is_file():
            raise RuntimeError("Local database configuration is missing")
        value = path.read_text(encoding="utf-8")
    value = value.strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError("Local database configuration must contain one nonempty line")
    return value


def _file_pointer(value: str) -> Path:
    value = value.strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError("Credential file configuration must contain one nonempty path")
    return Path(value)


def _llm_local_config() -> dict:
    configured = os.environ.get("REPUTATION_LLM_CONFIG_FILE")
    path = _file_pointer(configured) if configured is not None else Path("runtime/platform-config/llm.json")
    path = PROJECT_ROOT / path
    if not path.is_file() and configured is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise RuntimeError("Local LLM configuration file is missing, unreadable or invalid JSON") from None
    if (not isinstance(data, dict) or set(data) - {"base_url", "api_key_file", "model", "api_style"}
            or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise RuntimeError("Local LLM configuration has invalid fields; use the configuration template")
    return data


def load_llm_config():
    from reputation_platform.llm import LEGACY_CONFIG, LLMConfig

    data = _llm_local_config()
    for field in ("base_url", "model", "api_style"):
        value = os.environ.get("REPUTATION_LLM_" + field.upper())
        if value is not None:
            data[field] = value
    if not any(field in data for field in ("base_url", "model", "api_style")):
        return LEGACY_CONFIG
    if not data.get("base_url") or not data.get("model"):
        raise RuntimeError("Set both LLM base_url and model; no automatic model fallback")
    return LLMConfig(data["base_url"], data["model"], data.get("api_style", "chat_completions"))


def load_llm_key_file(explicit: Path | None = None) -> Path:
    """Select a local key file without reading its credential contents."""
    if explicit is not None:
        return explicit
    value = os.environ.get("REPUTATION_LLM_API_KEY_FILE", os.environ.get("REPUTATION_LLM_KEY_FILE"))
    if value is not None:
        return PROJECT_ROOT / _file_pointer(value)
    value = _llm_local_config().get("api_key_file")
    if value is not None:
        return PROJECT_ROOT / _file_pointer(value)
    pointer = PROJECT_ROOT / "runtime/platform-config/llm-key-file.txt"
    if pointer.is_file():
        return PROJECT_ROOT / _file_pointer(pointer.read_text(encoding="utf-8"))
    return PROJECT_ROOT / "runtime/secrets/deepseek-api-key.txt"


def load_zan_key_file(explicit: Path | None = None, *, fallback: str | Path | None = None) -> Path:
    """Override transport credentials while retaining frozen RPC configuration bytes."""
    if explicit is not None:
        return explicit
    value = os.environ.get("REPUTATION_ZAN_KEY_FILE")
    if value is not None:
        return PROJECT_ROOT / _file_pointer(value)
    pointer = PROJECT_ROOT / "runtime/platform-config/zan-key-file.txt"
    if pointer.is_file():
        return PROJECT_ROOT / _file_pointer(pointer.read_text(encoding="utf-8-sig"))
    conventional = PROJECT_ROOT / "secrets/zan-base-rpc.txt"
    if conventional.is_file():
        return conventional
    if fallback is not None:
        return Path(fallback)
    return PROJECT_ROOT / "runtime/secrets/zan-rpc-url.txt"
