"""Small OpenAI-compatible request adapter; public records exclude private endpoints."""

from dataclasses import dataclass
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit, urlunsplit


def endpoint_url(base_url: str, api_style: str) -> str:
    if api_style not in {"chat_completions", "responses"}:
        raise ValueError("Unsupported LLM API style; use chat_completions or responses")
    try:
        parsed = urlsplit(base_url)
        if (not isinstance(base_url, str) or not base_url or any(c.isspace() for c in base_url)
                or parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.port not in (None, 443) or "?" in base_url or "#" in base_url
                or "\\" in base_url or "%" in parsed.netloc):
            raise ValueError
        host = parsed.hostname
        if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
        path = parsed.path.rstrip("/")
        suffix = "/chat/completions" if api_style == "chat_completions" else "/responses"
        other = "/responses" if api_style == "chat_completions" else "/chat/completions"
        if path.endswith(other):
            raise ValueError("LLM endpoint path conflicts with API style")
        if not path.endswith(suffix):
            path += suffix
        return urlunsplit(("https", parsed.netloc.lower(), path, "", ""))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("LLM Base URL must be public HTTPS on port 443, without credentials, query or fragment; check API style/path") from None


def validate_record(record: dict) -> dict:
    if (not isinstance(record, dict)
            or set(record) != {"schema_version", "api_style", "model", "endpoint_sha256"}
            or record["schema_version"] != "llm-config-v1"
            or record["api_style"] not in ("chat_completions", "responses")
            or not isinstance(record["model"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}", record["model"])
            or "://" in record["model"]
            or not isinstance(record["endpoint_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["endpoint_sha256"])):
        raise ValueError("Invalid LLM configuration record")
    return dict(record)


def fingerprint(record: dict) -> str:
    return hashlib.sha256(json.dumps(validate_record(record), sort_keys=True).encode()).hexdigest()


def evidence_url(record: dict) -> str:
    return "https://llm.invalid/" + fingerprint(record)


@dataclass(frozen=True, repr=False)
class LLMConfig:
    base_url: str
    model: str
    api_style: str = "chat_completions"

    def __post_init__(self) -> None:
        self.record()

    @property
    def endpoint(self) -> str:
        return endpoint_url(self.base_url, self.api_style)

    @property
    def models_endpoint(self) -> str:
        suffix = "/chat/completions" if self.api_style == "chat_completions" else "/responses"
        return self.endpoint.removesuffix(suffix) + "/models"

    def record(self) -> dict:
        return validate_record({"schema_version": "llm-config-v1", "api_style": self.api_style,
            "model": self.model, "endpoint_sha256": hashlib.sha256(self.endpoint.encode()).hexdigest()})

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.record())

    @property
    def evidence_url(self) -> str:
        return evidence_url(self.record())

    @property
    def is_legacy(self) -> bool:
        return self.record() == LEGACY_CONFIG.record()


LEGACY_CONFIG = LLMConfig("https://api.deepseek.com", "deepseek-flash", "responses")


def request_body(instructions: str, input_data: dict, schema: dict, name: str, record: dict) -> dict:
    record = validate_record(record)
    text = json.dumps(input_data, ensure_ascii=False)
    if record["api_style"] == "chat_completions":
        # Prompt plus local schema validation also works on providers without structured-output parameters.
        return {"model": record["model"], "stream": False, "messages": [
            {"role": "system", "content": instructions + "\nReturn only JSON matching this schema, without Markdown:\n"
             + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": text},
        ]}
    body = {"model": record["model"], "instructions": instructions, "input": text,
        "max_output_tokens": 8192, "stream": False,
        "text": {"format": {"type": "json_schema", "name": name, "schema": schema}}}
    if record == LEGACY_CONFIG.record():
        body.update(reasoning={"effort": "none"}, tools=[], tool_choice="none")
    return body


def response_text(response: dict, api_style: str) -> str:
    """Reject partial/tool/refusal output; never expose provider error bodies in exceptions."""
    if api_style not in {"chat_completions", "responses"}:
        raise ValueError("Unsupported LLM API style")
    try:
        if not isinstance(response, dict) or response.get("error"):
            raise ValueError
        if api_style == "chat_completions":
            choices = response["choices"]
            if not isinstance(choices, list) or len(choices) != 1 or choices[0]["finish_reason"] != "stop":
                raise ValueError
            message = choices[0]["message"]
            if (message.get("role") != "assistant" or message.get("tool_calls")
                    or message.get("function_call") or message.get("refusal")):
                raise ValueError
            content = message["content"]
            if isinstance(content, list):
                if not content or any(part.get("type") != "text" for part in content):
                    raise ValueError
                content = "".join(part["text"] for part in content)
        else:
            if response.get("status") != "completed":
                raise ValueError
            outputs = response["output"]
            if not isinstance(outputs, list) or any(item["type"] not in {"message", "reasoning"} for item in outputs):
                raise ValueError
            parts = [part for item in outputs if item["type"] == "message" for part in item["content"]]
            if not parts or any(part["type"] != "output_text" for part in parts):
                raise ValueError
            content = "".join(part["text"] for part in parts)
        if not isinstance(content, str) or not content.strip():
            raise ValueError
        return content
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("LLM output incomplete, refused, malformed or contains unsupported tool output; check selected model/API style") from None
