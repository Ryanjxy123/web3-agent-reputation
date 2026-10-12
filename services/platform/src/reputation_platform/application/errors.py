"""Transport-independent, public-safe application failures."""

import json

from reputation_core.public_identity import contains_sensitive_text

from reputation_platform.infrastructure.evidence_store import SECRET_NAMES


class ApplicationError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def require_public_safe(value: object) -> None:
    # Refuse disclosure without changing immutable evidence or its committed hash.
    pending = [value]
    while pending:
        node = pending.pop()
        sensitive_field = isinstance(node, dict) and any(
            contains_sensitive_text(key) or (
                key.lower().replace("_", "").replace("-", "") in SECRET_NAMES
                and child != "[REDACTED]"
            ) for key, child in node.items()
        )
        sensitive_text = False
        if isinstance(node, str):
            try:
                decoded = json.loads(
                    node, object_pairs_hook=lambda pairs: [{key: child} for key, child in pairs],
                    parse_int=lambda _: None, parse_float=lambda _: None,
                )
            except RecursionError:
                sensitive_text = True
            except ValueError:
                sensitive_text = contains_sensitive_text(node)
            else:
                # Inspect retained JSON text as data, preserving escaped originals.
                pending.append(decoded)
        if sensitive_text or sensitive_field:
            raise ApplicationError(
                403, "HISTORICAL_EVIDENCE_RESTRICTED",
                "Historical evidence contains sensitive content and is restricted.",
            )
        if isinstance(node, dict):
            pending.extend(node)
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
