"""Reviewed provider contracts over shared position schemas and output mappings."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from reputation_platform.position_adapters import (
    ADAPTERS, BRAIN_SCHEMA, HALLMARK_SCHEMA, _schema_contract, _unique_pairs,
    parse_position_claim, position_request,
)
from reputation_platform.position_oracle import canonical_position_id

CONFIG = 'configs/position-adapter-reviews-v1.json'
REVIEW_CONFIG_ENV = 'REPUTATION_POSITION_REVIEW_CONFIG'
SCHEMA_VERSION = 'position-adapter-reviews-v1'
SAFETY = {'reviewed': True, 'free': True, 'read_only': True,
          'signing': False, 'mainnet_writes': False, 'delegation': False}
MAPPINGS = {
    'mcp-position-look/v1': ('MCP', BRAIN_SCHEMA, ADAPTERS[0]),
    'a2a-range-analysis/v1': ('A2A', HALLMARK_SCHEMA, ADAPTERS[1]),
}


def _same(left, right):
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _review_paths(adapter):
    refs = adapter.get('review_dependencies')
    if not isinstance(refs, list) or not refs:
        raise ValueError('Position contract requires retained source review evidence')
    paths = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
            raise ValueError('Malformed position review dependency')
        name = ref['path']
        if (not isinstance(name, str) or not name or '\\' in name or Path(name).drive
            or Path(name).is_absolute() or '..' in Path(name).parts or name in paths
            or not isinstance(ref['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', ref['sha256']) is None):
            raise ValueError('Invalid position review path or digest')
        paths.add(name)
    return refs


def _contract(adapter):
    if not isinstance(adapter, dict):
        raise ValueError('Position adapter must be an object')
    mapping = MAPPINGS.get(adapter.get('output_mapping'))
    if (mapping is None or adapter.get('protocol') != mapping[0]
        or type(adapter.get('chain')) is not int or adapter['chain'] != 56
        or not _same(adapter.get('safety'), SAFETY)
        or not _same(_schema_contract(adapter.get('input_schema')), mapping[1])
        or any(not isinstance(adapter.get(key), str) or not adapter[key] for key in ('id', 'tool', 'provider', 'endpoint'))):
        raise ValueError('Position adapter is outside a reviewed schema, mapping or safety scope')
    url = urlsplit(adapter['endpoint'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Position contract requires an exact HTTPS endpoint')
    _review_paths(adapter)
    return mapping[2]


def review_config_path(root: Path, config_path: str) -> str:
    """Keep deployment choices and frozen references inside the same repository."""
    if (not isinstance(config_path, str) or not config_path or '\\' in config_path
        or Path(config_path).drive or Path(config_path).is_absolute()
        or any(part in ('', '.', '..') for part in config_path.split('/'))
        or not (Path(root).resolve() / config_path).resolve().is_relative_to(Path(root).resolve())):
        raise ValueError('Position review config must be a canonical repository-relative path')
    return config_path


def load_contract_reviews(root: Path, config_path: str = CONFIG) -> dict:
    """Only local files are read; callers also freeze config and dependencies in their manifest."""
    root = Path(root).resolve()
    path = (root / review_config_path(root, config_path)).resolve()
    try:
        config = json.loads(path.read_bytes(), object_pairs_hook=_unique_pairs)
        if (not isinstance(config, dict) or config.get('schema_version') != SCHEMA_VERSION
            or not isinstance(config.get('adapters'), list) or not config['adapters']):
            raise ValueError('Unknown position review configuration')
        ids, endpoints = set(), set()
        for adapter in config['adapters']:
            _contract(adapter)
            if adapter['id'] in ids or adapter['endpoint'] in endpoints:
                raise ValueError('Ambiguous position review adapter')
            ids.add(adapter['id'])
            endpoints.add(adapter['endpoint'])
            for ref in _review_paths(adapter):
                source = (root / ref['path']).resolve()
                if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest() != ref['sha256']:
                    raise ValueError('Position source review evidence changed: ' + ref['path'])
    except OSError as error:
        raise ValueError('Position review evidence is unavailable') from error
    return config


def match_contract(identity: dict, endpoint: str, catalog, config: dict) -> dict | None:
    """A similar schema never grants execution permission without a reviewed config entry."""
    try:
        if (not isinstance(identity, dict) or identity.get('registration_verified') is not True
            or identity.get('document') is None or not isinstance(identity.get('services'), list)
            or not str(identity.get('token_uri', '')).startswith(('data:application/json', 'https://'))
            or str(identity.get('canonical', '')).split(':')[:2] != ['eip155', '56']
            or not isinstance(config, dict) or config.get('schema_version') != SCHEMA_VERSION
            or not isinstance(config.get('adapters'), list)):
            return None
        entries = [item for item in config['adapters'] if isinstance(item, dict) and item.get('endpoint') == endpoint]
        if len(entries) != 1:
            return None
        adapter = entries[0]
        _contract(adapter)
        if not any(isinstance(service, dict) and str(service.get('name', '')).lower() == adapter['protocol'].lower()
                   and service.get('endpoint') == endpoint for service in identity['services']):
            return None
        if adapter['protocol'] == 'MCP':
            if not isinstance(catalog, list) or any(not isinstance(item, dict) for item in catalog):
                return None
            skills = [item for item in catalog if item.get('name') == adapter['tool']]
            allowed = {'name', 'description', 'inputSchema', 'annotations'}
        else:
            if (not isinstance(catalog, dict) or catalog.get('type') != 'AgentCard'
                or catalog.get('url') != endpoint or catalog.get('protocolVersion') != '0.3.0'
                or catalog.get('preferredTransport') != 'JSONRPC' or catalog.get('security') != []
                or catalog.get('securitySchemes') != {} or catalog.get('supportsAuthenticatedExtendedCard') is not False
                or catalog.get('provider', {}).get('organization') != adapter['provider']
                or any(key in catalog for key in ('pricing', 'price', 'payment', 'authentication'))
                or not isinstance(catalog.get('skills'), list)
                or any(not isinstance(item, dict) for item in catalog['skills'])):
                return None
            skills = [item for item in catalog['skills'] if item.get('id') == adapter['tool']]
            allowed = {'id', 'name', 'description', 'tags', 'examples', 'inputModes', 'outputModes', 'inputSchema'}
        if len(skills) != 1 or set(skills[0]) - allowed:
            return None
        skill = skills[0]
        hints = skill.get('annotations', {})
        if (not isinstance(hints, dict)
            or ('readOnlyHint' in hints and hints['readOnlyHint'] is not True)
            or ('destructiveHint' in hints and hints['destructiveHint'] is not False)
            or not _same(_schema_contract(skill.get('inputSchema')), _schema_contract(adapter['input_schema']))):
            return None
        return deepcopy(adapter)
    except (TypeError, ValueError, AttributeError, KeyError):
        return None


def request_contract(adapter: dict, key: str, tokenid: str) -> dict:
    legacy = _contract(adapter)
    request = position_request(legacy, key, tokenid)
    if adapter['protocol'] == 'MCP':
        request['params']['name'] = adapter['tool']
    else:
        request['params']['message']['parts'][0]['data']['skill'] = adapter['tool']
    return request


def parse_contract(adapter: dict, raw: bytes, key: str, tokenid: str | None = None) -> dict | None:
    """Keep subject mismatches as observed facts for independent F/B verification."""
    try:
        legacy = _contract(adapter)
        if tokenid is not None:
            canonical_position_id(tokenid)
        if adapter['protocol'] == 'A2A':
            envelope = json.loads(raw, object_pairs_hook=_unique_pairs)
            parts = envelope.get('result', {}).get('parts')
            if not isinstance(parts, list) or len(parts) != 1:
                return None
            data = parts[0]['data']
            if data.get('skill') != adapter['tool'] or data.get('result', {}).get('skill') != adapter['tool']:
                return None
            data['skill'] = data['result']['skill'] = legacy['tool']
            raw = json.dumps(envelope, allow_nan=False).encode()
        return parse_position_claim(legacy, raw, key)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return None
