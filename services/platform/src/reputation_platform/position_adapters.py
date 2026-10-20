"""Reviewed call/schema/output mappings; no Agent-ID dispatch or network access."""

from decimal import Decimal, localcontext
import json

from reputation_platform.position_oracle import canonical_position_id as position_id
from reputation_platform.protocol_evaluation import _result
from reputation_platform.query_oracle import _hex

ADAPTERS = (
    {'id': 'brain.position-look/v1', 'endpoint': 'https://brainonbnb.com/mcp',
     'protocol': 'MCP', 'tool': 'pancakeswap_position_look', 'provider': 'Brain/BOBAI', 'chain': 56},
    {'id': 'hallmark.range-analyse/v1', 'endpoint': 'https://hallmark-agents.vercel.app/a2a/rebalancer',
     'protocol': 'A2A', 'tool': 'analyse', 'provider': 'Hallmark', 'chain': 56},
)
BRAIN_SCHEMA = {'type': 'object', 'properties': {'position': {'type': 'string'},
                'address': {'type': 'string'}}, 'additionalProperties': False}
HALLMARK_SCHEMA = {'type': 'object', 'properties': {
    'tokenId': {'type': 'string', 'pattern': '^(0|[1-9][0-9]*)$'},
    'chainId': {'type': 'integer', 'minimum': 56, 'maximum': 97},
    'widthBps': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
    'driftToleranceBps': {'type': 'integer', 'minimum': 0, 'maximum': 10000},
    'wallet': {'type': 'string', 'pattern': '^0x[0-9a-fA-F]{40}$'}},
    'required': ['tokenId'], 'additionalProperties': False}


def _schema_contract(value):
    if not isinstance(value, dict):
        return value
    return {key: ({name: _schema_contract(spec) for name, spec in item.items()}
                  if key == 'properties' and isinstance(item, dict) else _schema_contract(item))
            for key, item in value.items() if key != 'description'}


def match_position_adapter(identity: dict, endpoint: str, catalog) -> dict | None:
    try:
        return _match_position_adapter(identity, endpoint, catalog)
    except (TypeError, ValueError, AttributeError, KeyError):
        return None


def _match_position_adapter(identity: dict, endpoint: str, catalog) -> dict | None:
    if (not isinstance(identity, dict) or identity.get('registration_verified') is not True
        or identity.get('document') is None or not isinstance(identity.get('services'), list)
        or not str(identity.get('token_uri', '')).startswith(('data:application/json', 'https://'))
        or str(identity.get('canonical', '')).split(':')[:2] != ['eip155', '56']):
        return None
    for adapter in ADAPTERS:
        registered = any(str(s.get('name', '')).lower() == adapter['protocol'].lower()
                         and s.get('endpoint') == endpoint for s in identity.get('services', [])
                         if isinstance(s, dict))
        if endpoint != adapter['endpoint'] or not registered:
            continue
        if adapter['protocol'] == 'MCP':
            if not isinstance(catalog, list) or any(not isinstance(t, dict) for t in catalog):
                return None
            skills = [t for t in catalog if t.get('name') == adapter['tool']]
            allowed = {'name', 'description', 'inputSchema', 'annotations'}
            expected = BRAIN_SCHEMA
        else:
            if (not isinstance(catalog, dict) or catalog.get('type') != 'AgentCard'
                or catalog.get('url') != endpoint or catalog.get('protocolVersion') != '0.3.0'
                or catalog.get('preferredTransport') != 'JSONRPC'
                or catalog.get('security') != [] or catalog.get('securitySchemes') != {}
                or catalog.get('provider', {}).get('organization') != 'Hallmark'
                or catalog.get('supportsAuthenticatedExtendedCard') is not False
                or any(k in catalog for k in ('pricing', 'price', 'payment', 'authentication'))
                or not isinstance(catalog.get('skills'), list)
                or any(not isinstance(s, dict) for s in catalog['skills'])):
                return None
            skills = [s for s in catalog['skills'] if s.get('id') == adapter['tool']]
            allowed = {'id', 'name', 'description', 'tags', 'examples', 'inputModes', 'outputModes', 'inputSchema'}
            expected = HALLMARK_SCHEMA
        if len(skills) != 1 or set(skills[0]) - allowed:
            return None
        skill = skills[0]
        annotations = skill.get('annotations', {})
        if (not isinstance(annotations, dict) or annotations.get('readOnlyHint') is False
            or annotations.get('destructiveHint') is True
            or json.dumps(_schema_contract(skill.get('inputSchema')), sort_keys=True)
                != json.dumps(expected, sort_keys=True)):
            return None
        return dict(adapter)
    return None


def _adapter(adapter: dict) -> dict:
    if not isinstance(adapter, dict) or adapter not in ADAPTERS:
        raise ValueError('Unreviewed position adapter')
    return adapter


def position_arguments(adapter: dict, token_id: str) -> dict:
    adapter, token_id = _adapter(adapter), position_id(token_id)
    return {'position': token_id} if adapter['protocol'] == 'MCP' else {'chainId': 56, 'tokenId': token_id}


def position_request(adapter: dict, key: str, token_id: str) -> dict:
    arguments = position_arguments(adapter, token_id)
    if not isinstance(key, str) or not key:
        raise ValueError('A nonempty request ID is required')
    if adapter['protocol'] == 'MCP':
        method, params = 'tools/call', {'name': adapter['tool'], 'arguments': arguments}
    else:
        method, params = 'message/send', {'message': {'kind': 'message', 'role': 'user',
            'messageId': key, 'parts': [{'kind': 'data', 'data': {'skill': adapter['tool'], 'input': arguments}}]}}
    return {'jsonrpc': '2.0', 'id': key, 'method': method, 'params': params}


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_float=Decimal)


def parse_position_claim(adapter: dict, raw: bytes, request_id: str) -> dict | None:
    try:
        adapter = _adapter(adapter)
        envelope = _json(raw)
        if type(envelope.get('id')) is not type(request_id):
            return None
        result = _result(raw, request_id)
        if adapter['protocol'] == 'MCP':
            content = result.get('content')
            if (result.get('isError', False) is not False or not isinstance(content, list)
                or len(content) != 1 or not isinstance(content[0], dict)
                or content[0].get('type') != 'text' or not isinstance(content[0].get('text'), str)):
                return None
            answer = _json(content[0]['text'])
            if (not isinstance(answer, dict) or answer.get('service') != 'lp_position_look'
                or type(answer.get('positions')) is not int or answer['positions'] != 1):
                return None
            pool = answer['pool']
            percent = pool['fee_tier_pct']
            if type(percent) not in (int, Decimal):
                return None
            percent = Decimal(percent)
            if not percent.is_finite() or percent.adjusted() > 77:
                return None
            with localcontext() as ctx:
                ctx.prec = max(28, len(percent.as_tuple().digits) + 5)
                fee = percent * 10000
                if fee != fee.to_integral_value():
                    return None
                fee = int(fee)
            ticks = pool['ticks']
            if not isinstance(ticks, list) or len(ticks) != 2:
                return None
            claim = {'positionId': answer['position'], 'token0': pool['token0'],
                     'token1': pool['token1'], 'fee': fee, 'tickLower': ticks[0], 'tickUpper': ticks[1]}
        else:
            parts = result.get('parts')
            if (result.get('kind') != 'message' or result.get('role') != 'agent'
                or not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict)
                or parts[0].get('kind') != 'data'):
                return None
            data = parts[0]['data']
            if data.get('skill') != 'analyse':
                return None
            answer = data['result']
            if answer.get('skill') != 'analyse' or 'error' in answer:
                return None
            position = answer['facts']['position']
            claim = {'positionId': answer['subject']['tokenId'], 'token0': position['token0']['address'],
                     'token1': position['token1']['address'], 'fee': position['fee'],
                     'tickLower': position['tickLower'], 'tickUpper': position['tickUpper'],
                     'reportedChain': answer['chainId'], 'reportedPositionId': position['tokenId']}
            if type(claim['reportedChain']) is not int:
                return None
            position_id(claim['reportedPositionId'])
        position_id(claim['positionId'])
        claim['token0'], claim['token1'] = _hex(claim['token0'], 40), _hex(claim['token1'], 40)
        if any(type(claim[key]) is not int for key in ('fee', 'tickLower', 'tickUpper')):
            return None
        return claim
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, ArithmeticError):
        return None
