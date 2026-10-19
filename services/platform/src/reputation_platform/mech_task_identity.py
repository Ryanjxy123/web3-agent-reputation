"""Recheck retained Gnosis Mech identity without provider-domain or prediction assumptions."""

import hashlib
import json
from urllib.parse import urlsplit

from reputation_core import ReportFinding, Verdict
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import (
    BRIDGER, REGISTRY, SERVICE_REGISTRY, _hex, _words, calldata, call_value,
)
from reputation_platform.registration_discovery import _abi_string


def verify_mech_identity(evidence, bundle: dict, canonical: str) -> dict:
    """Authenticate a completed legacy bundle's identity using its original RPC/HTTP sources.

    ``evidence`` is the existing RetainedEvidence reader; all retained dependencies
    enter its inputs. No request is sent and no historical task is relabelled here.
    """
    try:
        reference = normalize_reference(canonical)
        if reference is None:
            raise ValueError('Expected a complete registered identity')
        _, chain, registry, token = reference.split(':')
        if int(chain) != 100 or registry != REGISTRY or int(token) >= 2**256:
            raise ValueError('Only the trusted Gnosis identity registry is supported')

        profile = bundle['profile']
        if (profile['chain_id'] != 100 or str(profile['registry']).lower() != REGISTRY
            or type(profile['agent_id']) is not int or profile['agent_id'] != int(token)):
            raise ValueError('Bundle identity hints differ from the submitted canonical identity')
        mech = _hex(profile['mech'], 40)
        service_id, snapshot = profile['service_id'], profile['snapshot_block']
        if (int(mech, 16) == 0 or type(service_id) is not int or not 0 <= service_id < 2**256
            or type(snapshot) is not int or snapshot < 0):
            raise ValueError('Mech, service or snapshot hint is invalid')

        identity = evidence.tree(bundle['identity'])
        chain_proof, head_proof, header_proof = [identity[name] for name in ('chain', 'head', 'header')]
        head = int(_hex(head_proof['value']), 16)
        header = header_proof['value']
        if (chain_proof['method'] != 'eth_chainId' or chain_proof['params'] != []
            or int(_hex(chain_proof['value']), 16) != 100
            or head_proof['method'] != 'eth_blockNumber' or head_proof['params'] != []
            or type(profile['confirmation_head']) is not int or head != profile['confirmation_head']
            or head - snapshot < 64
            or header_proof['method'] != 'eth_getBlockByNumber' or header_proof['params'] != [hex(snapshot), False]
            or int(_hex(header['number']), 16) != snapshot
            or _hex(header['hash'], 64) != _hex(profile['snapshot_hash'], 64)):
            raise ValueError('Original chain, head or fixed snapshot differs from the identity hints')

        calls = identity['calls']

        def word(name: str, contract: str, signature: str, *arguments) -> int:
            return _words(call_value(calls, name, contract, calldata(signature, *arguments), snapshot), 1)[0]

        if (word('registration-owner', REGISTRY, 'ownerOf(uint256)', int(token)) != int(BRIDGER, 16)
            or word('bridger-agent-id', BRIDGER, 'mapServiceIdAgentIds(uint256)', service_id) != int(token)
            or word('mech-service-id', mech, 'serviceId()') != service_id
            or word('mech-service-registry', mech, 'serviceRegistry()') != int(SERVICE_REGISTRY, 16)):
            raise ValueError('Original registry, bridge mapping and Mech service getters do not bind this identity')
        operator = word('mech-operator', mech, 'getOperator()')
        if not 0 < operator < 2**160:
            raise ValueError('Current service operator is not a nonzero address')

        uri = _abi_string(call_value(calls, 'registration-uri', REGISTRY,
                                     calldata('tokenURI(uint256)', int(token)), snapshot))
        parsed = urlsplit(uri)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError('This retained Mech adapter supports registered HTTPS JSON documents')
        registration = identity['registration']
        observation, raw = evidence.observation(registration['evidence'], url=uri, method='GET')
        retained = evidence.remember(profile['registration_source'], profile['registration_sha256'])
        if (observation.request_json is not None or retained.read_bytes() != raw
            or hashlib.sha256(raw).hexdigest() != profile['registration_sha256']):
            raise ValueError('Original registered document differs from its retained source')
        document = json.loads(raw)
        if not isinstance(document, dict) or document != registration['payload']:
            raise ValueError('Registered document copy differs from the original JSON object')
        registrations = document.get('registrations', [])
        if not isinstance(registrations, list) or not any(
            isinstance(item, dict) and type(item.get('agentId')) is int and item['agentId'] == int(token)
            and str(item.get('agentRegistry', '')).lower() == f'eip155:100:{REGISTRY}'
            for item in registrations
        ):
            raise ValueError('Original registration document does not identify the submitted Agent')

        checks = [
            ReportFinding(label='固定链与区块', verdict=Verdict.PASS,
                explanation='原始可信 RPC 证明链号、固定区块哈希与至少64块确认距离一致。'),
            ReportFinding(label='注册身份与服务关联', verdict=Verdict.PASS,
                explanation='注册持有人为官方桥；桥的服务到Agent映射及Mech的服务号、注册表和当前operator getter均有对应原件。'),
            ReportFinding(label='登记文档来源', verdict=Verdict.PASS,
                explanation='实际链上tokenURI对应原始HTTPS文档，且文档registrations精确列出本身份；不以提供方域名推定关联。'),
        ]
        return {'canonical': reference, 'mech': mech, 'service_id': service_id,
                'confirmation_head': head, 'document': document, 'checks': checks}
    except (KeyError, TypeError, AttributeError, IndexError, OSError) as error:
        raise ValueError('Missing or malformed retained Mech identity evidence') from error
