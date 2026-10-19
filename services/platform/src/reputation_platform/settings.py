"""Local operator configuration; database credentials never enter public contracts."""

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


def load_llm_key_file(explicit: Path | None = None) -> Path:
    """Select a local key file without reading its credential contents."""
    if explicit is not None:
        return explicit
    value = os.environ.get("REPUTATION_LLM_KEY_FILE")
    if value is not None:
        return _file_pointer(value)
    pointer = PROJECT_ROOT / "runtime/platform-config/llm-key-file.txt"
    if pointer.is_file():
        return _file_pointer(pointer.read_text(encoding="utf-8"))
    return PROJECT_ROOT / "runtime/secrets/deepseek-api-key.txt"


def load_zan_key_file(explicit: Path | None = None, *, fallback: str | Path | None = None) -> Path:
    """Override transport credentials while retaining frozen RPC configuration bytes."""
    if explicit is not None:
        return explicit
    value = os.environ.get("REPUTATION_ZAN_KEY_FILE")
    if value is not None:
        return _file_pointer(value)
    if fallback is not None:
        return Path(fallback)
    return PROJECT_ROOT / "runtime/secrets/zan-rpc-url.txt"
