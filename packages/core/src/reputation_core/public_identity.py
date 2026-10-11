"""Deterministic parsing and limited endpoint association, never a control proof."""

import ipaddress
import re
from typing import Any, cast
from urllib.parse import urlsplit

from .evidence import hash_bytes, hash_json, strict_json
from .models.domain import AgentRef, AgentSnapshot, Endpoint
from .models.enums import Outcome, Reason
from .models.public_identity import (
    IdentityOutcome,
    PublicReadonlyProtocol,
    PublicRegistrationMetadata,
    PublicServiceDeclaration,
    ReadonlyIdentityAssociation,
)

AKASHI_ORIGIN = "https://anchor.akashi-notari.com"
AKASHI_MCP_URL = AKASHI_ORIGIN + "/mcp"
AKASHI_OPENAPI_URL = AKASHI_ORIGIN + "/openapi.json"
AKASHI_HTTP_URL = AKASHI_ORIGIN + "/proof"
MCP_VERSION = "2025-11-25"
_SECRET_KEYS = {
    "authorization", "cookie", "setcookie", "xapikey", "apikey", "token", "accesstoken",
    "refreshtoken", "password", "secret", "clientsecret", "privatekey", "mnemonic",
    "signedraw", "signedtransaction", "mcpsessionid", "sessionid",
}
_SENSITIVE_TEXT = re.compile(
    r'(?i)bearer\s|(?:authorization|cookie|api[_-]?key|access[_-]?token|token|password|'
    r'secret|private[_-]?key)["\x27]?\s*[:=]|-----BEGIN .*PRIVATE KEY'
)


def _json_document(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 1024 * 1024:
        raise ValueError("PUBLIC_METADATA_INVALID")
    try:
        value = strict_json(raw)
    except (ValueError, RecursionError, OverflowError):
        raise ValueError("PUBLIC_METADATA_INVALID") from None
    if not isinstance(value, dict):
        raise ValueError("PUBLIC_METADATA_INVALID")
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > 32:
            raise ValueError("PUBLIC_METADATA_INVALID")
        if isinstance(node, dict):
            for key, child in node.items():
                if (key.lower().replace("_", "").replace("-", "") in _SECRET_KEYS
                        or _SENSITIVE_TEXT.search(key)):
                    raise ValueError("PUBLIC_METADATA_SENSITIVE")
                stack.append((child, depth + 1))
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, str) and _SENSITIVE_TEXT.search(node):
            raise ValueError("PUBLIC_METADATA_SENSITIVE")
    return value


def _safe_https_url(value: str) -> bool:
    if not isinstance(value, str) or re.search(r"[\s\x00-\x1f\x7f\\%]", value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment):
            return False
        if not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+"
                            r"(?:[a-z0-9-]*[a-z0-9])?)+", host):
            return False
        if host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return address.is_global
    except ValueError:
        return False


def parse_registration_metadata(raw: bytes, agent_ref: AgentRef) -> PublicRegistrationMetadata:
    """Accept the locked registration-v1 fields; all other bytes stay untrusted evidence."""
    value = _json_document(raw)
    if set(value) - {
        "type", "name", "description", "image", "services", "x402Support", "active",
        "registrations", "supportedTrust",
    }:
        raise ValueError("PUBLIC_METADATA_INVALID")
    registrations = value.get("registrations")
    if not isinstance(registrations, list) or not 1 <= len(registrations) <= 20:
        raise ValueError("PUBLIC_METADATA_INVALID")
    keys = []
    for registration in registrations:
        if not isinstance(registration, dict) or set(registration) != {"agentId", "agentRegistry"}:
            raise ValueError("PUBLIC_METADATA_INVALID")
        registry = registration["agentRegistry"]
        if not isinstance(registry, str) or not re.fullmatch(
            r"eip155:(0|[1-9][0-9]{0,77}):0x[0-9a-fA-F]{40}", registry
        ):
            raise ValueError("PUBLIC_METADATA_INVALID")
        _, chain_id, address = registry.split(":")
        agent_id = registration["agentId"]
        if isinstance(agent_id, bool) or not isinstance(agent_id, (int, str)):
            raise ValueError("PUBLIC_METADATA_INVALID")
        try:
            ref = AgentRef(chain_id=chain_id,
                           registry_address=address, agent_id=str(agent_id))
        except ValueError:
            raise ValueError("PUBLIC_METADATA_INVALID") from None
        keys.append(ref.key_text)
    if len(set(keys)) != len(keys) or agent_ref.key_text not in keys:
        raise ValueError("PUBLIC_METADATA_IDENTITY_MISMATCH")
    services = value.get("services")
    if not isinstance(services, list) or len(services) > 20:
        raise ValueError("PUBLIC_METADATA_INVALID")
    declarations = []
    for service in services:
        if not isinstance(service, dict) or set(service) - {"name", "endpoint", "version"}:
            raise ValueError("PUBLIC_METADATA_INVALID")
        try:
            declaration = PublicServiceDeclaration.model_validate(service)
        except ValueError:
            raise ValueError("PUBLIC_METADATA_INVALID") from None
        if not _safe_https_url(declaration.endpoint):
            raise ValueError("PUBLIC_METADATA_INVALID")
        declarations.append(declaration)
    if len({service.name for service in declarations}) != len(declarations):
        raise ValueError("PUBLIC_METADATA_INVALID")
    if "image" in value and not _safe_https_url(value["image"]):
        raise ValueError("PUBLIC_METADATA_INVALID")
    try:
        return PublicRegistrationMetadata.model_validate({
            "type": value.get("type"), "name": value.get("name"),
            "description": value.get("description"), "services": tuple(declarations),
            "registration_agent_key": agent_ref.key_text,
            "x402_support": value.get("x402Support"), "active": value.get("active"),
            "supported_trust": value.get("supportedTrust", []),
        })
    except ValueError:
        raise ValueError("PUBLIC_METADATA_INVALID") from None


def readonly_endpoints(metadata: PublicRegistrationMetadata) -> tuple[Endpoint, ...]:
    """Only static candidate targets; declarations do not grant network access or control."""
    endpoints = []
    for declaration in metadata.services:
        if (declaration.name == "MCP" and declaration.endpoint == AKASHI_MCP_URL
                and declaration.version == MCP_VERSION):
            endpoints.append(Endpoint(endpoint_id="akashi-mcp", scheme="https",
                                      host="anchor.akashi-notari.com", port=443, path="/mcp",
                                      method="POST", protocol="akashi-mcp-readonly-v1"))
        elif (declaration.name == "OpenAPI" and declaration.endpoint == AKASHI_OPENAPI_URL
              and declaration.version == "3.1.0"):
            endpoints.append(Endpoint(endpoint_id="akashi-http", scheme="https",
                                      host="anchor.akashi-notari.com", port=443, path="/proof",
                                      method="GET", protocol="akashi-http-readonly-v1"))
    return tuple(endpoints)


def normalized_public_metadata(metadata: PublicRegistrationMetadata) -> dict[str, Any]:
    normalized = metadata.model_dump(mode="json")
    # Candidate mapping is static adapter support; it is not an extracted or confirmed claim.
    normalized["capabilities"] = ["verify_record"] if readonly_endpoints(metadata) else []
    return normalized


def _openapi_endpoint(raw: bytes) -> bool:
    value = _json_document(raw)
    if value.get("openapi") != "3.1.0" or value.get("servers") != [{"url": AKASHI_ORIGIN}]:
        return False
    paths = value.get("paths")
    if not isinstance(paths, dict) or not isinstance(paths.get("/proof"), dict):
        return False
    path = paths["/proof"]
    operation = path.get("get")
    if not isinstance(operation, dict) or operation.get("operationId") != "proof":
        return False
    # Operation/path servers can override the document's origin.
    if ("servers" in path or "servers" in operation or "$ref" in path
            or operation.get("security") != []):
        return False
    if any(key in node for node in (value, path, operation)
           for key in ("x-payment-info", "x402", "x402Support", "x402Version", "paymentRequired",
                       "payment_required", "requiresPayment", "requires_payment",
                       "paymentRequirements", "price",
                       "$ref", "callbacks", "x-side-effects", "requestBody")):
        return False
    if path.get("parameters", []) != []:
        return False
    parameters = operation.get("parameters")
    if not isinstance(parameters, list) or len(parameters) != 2:
        return False
    names = set()
    for parameter in parameters:
        if (not isinstance(parameter, dict)
                or set(parameter) - {"name", "in", "required", "schema", "description"}
                or parameter.get("name") not in ("tx", "hash")
                or parameter.get("name") in names
                or parameter.get("in") != "query" or parameter.get("required") is not False
                or parameter.get("schema") != {"type": "string"}):
            return False
        names.add(parameter["name"])
    responses = operation.get("responses")
    return isinstance(responses, dict) and "200" in responses and "402" not in responses


def associate_readonly_identity(
    snapshot: AgentSnapshot, target_url: str, protocol: str, *,
    metadata_raw: bytes | None = None, openapi_raw: bytes | None = None
) -> ReadonlyIdentityAssociation:
    if protocol not in ("akashi-http-readonly-v1", "akashi-mcp-readonly-v1"):
        raise ValueError("UNSUPPORTED_PUBLIC_PROTOCOL")
    read = snapshot.public_identity
    identity_hash = hash_json(read.model_dump(mode="json")) if read is not None else None
    registration = read.registration_outcome if read else Outcome.UNKNOWN
    registration_reason = read.registration_reason if read else Reason.MISSING_EVIDENCE
    endpoint: IdentityOutcome = Outcome.UNKNOWN
    endpoint_reason: Reason | None = Reason.MISSING_EVIDENCE
    openapi_hash = hash_bytes(openapi_raw) if openapi_raw is not None else None
    parsed_metadata = None
    if metadata_raw is not None:
        try:
            parsed_metadata = parse_registration_metadata(metadata_raw, snapshot.core.agent_ref)
        except ValueError:
            pass
    safe_target = target_url if _safe_https_url(target_url) else "[REJECTED TARGET URL]"
    expected_hash = hash_json(snapshot.core.model_dump(mode="json")) if read is None else hash_json({
        "core": snapshot.core.model_dump(mode="json"),
        "public_identity": read.model_dump(mode="json"),
    })
    if snapshot.snapshot_hash != expected_hash or (read is not None and (
        snapshot.core.source_type != "public_registry"
        or snapshot.core.declared_executor is not None
        or read.registry_code_hash != snapshot.core.registry_chain.registry_code_hash
    )):
        registration, registration_reason = Outcome.UNKNOWN, Reason.CONTENT_HASH_MISMATCH
        endpoint_reason = Reason.CONTENT_HASH_MISMATCH
    elif registration == Outcome.PASS and read is not None:
        if read.metadata_outcome != Outcome.PASS or read.metadata is None:
            endpoint_reason = read.metadata_reason or Reason.MISSING_EVIDENCE
        elif metadata_raw is None:
            endpoint_reason = Reason.MISSING_EVIDENCE
        elif hash_bytes(metadata_raw) != read.metadata_bytes_hash:
            endpoint_reason = Reason.CONTENT_HASH_MISMATCH
        elif parsed_metadata is None:
            endpoint_reason = Reason.SCHEMA_ERROR
        elif (read.metadata.registration_agent_key != snapshot.core.agent_ref.key_text
              or parsed_metadata != read.metadata
              or snapshot.core.metadata_hash != hash_json(normalized_public_metadata(read.metadata))
              or snapshot.core.normalized_metadata != normalized_public_metadata(read.metadata)):
            endpoint_reason = Reason.CONTENT_HASH_MISMATCH
        else:
            candidates = readonly_endpoints(read.metadata)
            selected = [candidate for candidate in candidates if candidate.protocol == protocol]
            if not selected:
                endpoint, endpoint_reason = Outcome.FAIL, Reason.SEMANTIC_MISMATCH
            else:
                candidate = selected[0]
                expected_url = (AKASHI_HTTP_URL if protocol == "akashi-http-readonly-v1"
                                else AKASHI_MCP_URL)
                if target_url != expected_url or candidate not in snapshot.core.endpoints:
                    endpoint, endpoint_reason = Outcome.FAIL, Reason.SEMANTIC_MISMATCH
                elif protocol == "akashi-mcp-readonly-v1":
                    endpoint, endpoint_reason = Outcome.PASS, None
                elif openapi_raw is None or read.openapi_bytes_hash is None:
                    endpoint_reason = Reason.MISSING_EVIDENCE
                elif openapi_hash != read.openapi_bytes_hash:
                    endpoint_reason = Reason.CONTENT_HASH_MISMATCH
                else:
                    try:
                        matches = _openapi_endpoint(openapi_raw)
                    except ValueError:
                        endpoint_reason = Reason.SCHEMA_ERROR
                    else:
                        endpoint = Outcome.PASS if matches else Outcome.FAIL
                        endpoint_reason = None if matches else Reason.SEMANTIC_MISMATCH
    return ReadonlyIdentityAssociation(
        snapshot_hash=snapshot.snapshot_hash, identity_hash=identity_hash,
        target_url=safe_target, protocol=cast(PublicReadonlyProtocol, protocol),
        openapi_bytes_hash=openapi_hash,
        registration_outcome=registration, registration_reason=registration_reason,
        endpoint_outcome=endpoint, endpoint_reason=endpoint_reason,
    )
