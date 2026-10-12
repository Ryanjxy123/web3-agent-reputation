"""The disclosure gate refuses sensitive originals and preserves safe content."""

import copy
import json

import pytest
from reputation_platform.application.errors import ApplicationError, require_public_safe


@pytest.mark.parametrize("field", [
    "token", "accessToken", "privateKey", "clientSecret", "refresh_token", "sessionId",
    "Mcp-Session-Id", "signedTransaction",
])
def test_sensitive_field_aliases_are_restricted_and_redacted_placeholders_are_safe(field):
    value = {"nested": [{field: "SYNTHETIC_SECRET_ONLY"}]}
    with pytest.raises(ApplicationError) as failure:
        require_public_safe(value)
    assert failure.value.status == 403
    assert failure.value.code == "HISTORICAL_EVIDENCE_RESTRICTED"
    assert value == {"nested": [{field: "SYNTHETIC_SECRET_ONLY"}]}
    require_public_safe({field: "[REDACTED]"})


@pytest.mark.parametrize("encoding", [
    "slashes", "unicode", "nested", "dictionary_key", "duplicate_key", "large_number",
])
def test_escaped_embedded_json_userinfo_is_restricted_without_mutation(encoding):
    url = "https://audit-user:SYNTHETIC_SECRET_ONLY@example.com/legacy"
    raw = json.dumps({url: "example"} if encoding == "dictionary_key" else {"example": url})
    if encoding == "unicode":
        raw = raw.replace("/", r"\u002f").replace("@", r"\u0040")
    else:
        raw = raw.replace("/", r"\/")
    if encoding == "nested":
        raw = json.dumps({"raw_body_utf8": raw})
    elif encoding == "duplicate_key":
        raw = raw[:-1] + ', "example": "innocent duplicate"}'
    elif encoding == "large_number":
        raw = raw[:-1] + f', "number": {2**100}' + "}"
    value = {"response": {"raw_body_utf8": raw}}
    original = copy.deepcopy(value)
    with pytest.raises(ApplicationError) as failure:
        require_public_safe(value)
    assert failure.value.code == "HISTORICAL_EVIDENCE_RESTRICTED"
    assert value == original


def test_safe_json_and_opaque_text_are_not_rewritten_or_restricted():
    value = {"type": "text", "text": "ordinary non-JSON text", "response": {
        "raw_body_utf8": json.dumps({"url": "https://example.com/legacy", "token": "[REDACTED]"}),
    }}
    original = copy.deepcopy(value)
    require_public_safe(value)
    assert value == original


def test_uninspectable_deep_json_text_is_restricted_without_disclosing_it():
    value = {"raw_body_utf8": "[" * 10000 + '"legacy"' + "]" * 10000}
    original = value.copy()
    with pytest.raises(ApplicationError) as failure:
        require_public_safe(value)
    assert failure.value.status == 403
    assert failure.value.code == "HISTORICAL_EVIDENCE_RESTRICTED"
    assert value == original
