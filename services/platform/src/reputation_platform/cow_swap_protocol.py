"""Deterministic CoW sell-order/UID/event rules; no service names, I/O or clock."""
import json
import re
from copy import deepcopy

from eth_hash.auto import keccak
from reputation_core.swap import address, hex_bytes


ORDER_FIELDS = (('sellToken', 'address'), ('buyToken', 'address'), ('receiver', 'address'),
    ('sellAmount', 'uint256'), ('buyAmount', 'uint256'), ('validTo', 'uint32'),
    ('appData', 'bytes32'), ('feeAmount', 'uint256'), ('kind', 'string'),
    ('partiallyFillable', 'bool'), ('sellTokenBalance', 'string'), ('buyTokenBalance', 'string'))
TRADE_TOPIC = '0x' + keccak(b'Trade(address,address,address,uint256,uint256,uint256,bytes)').hex()
TRANSFER_TOPIC = '0x' + keccak(b'Transfer(address,address,uint256)').hex()


class CowSwapMismatch(ValueError):
    """An understood order contradicts the independently frozen task."""


class UnsupportedCowSwap(ValueError):
    """An unadapted mode must remain UNKNOWN rather than be guessed."""


def require(value, reason):
    if not value:
        raise CowSwapMismatch(reason)


def uint(value, bits=256):
    require(type(value) is int or isinstance(value, str) and bool(re.fullmatch(r'0|[1-9][0-9]*', value)),
            'Noncanonical unsigned integer')
    number = int(value)
    require(0 <= number < 2**bits, 'Unsigned integer width differs')
    return number


def word(value):
    return uint(value).to_bytes(32, 'big')


def pointer(value, path):
    require(isinstance(path, str) and (not path or path.startswith('/')), 'Expected a JSON pointer')
    for part in path.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def derive_cow_argument(spec, prior, depth=0):
    """Closed frozen-data expressions; overlay only existing object fields.

    Prior rows contain the independently retained MCP ``payload``. No code,
    URLs, clocks or signatures are resolved by this function.
    """
    require(depth <= 8 and isinstance(spec, dict), 'Frozen argument derivation is too deep or malformed')
    rule = spec.get('rule')
    if rule in {'stage-value', 'quote-minimum'}:
        row = prior.get(spec['stage'])
        require(row and row['payload'] is not None, 'Derived argument lacks its prior original response')
        value = deepcopy(pointer(row['payload'], spec['pointer']))
        if rule == 'stage-value':
            return value
        bps = uint(spec['slippage_bps'])
        require(bps < 10000, 'Invalid frozen slippage')
        return str((uint(value) * (10000 - bps) + 9999) // 10000)
    if rule == 'keccak-utf8':
        value = derive_cow_argument(spec['value'], prior, depth + 1)
        require(isinstance(value, str), 'UTF8 hash input must be exact text')
        return '0x' + keccak(value.encode('utf-8')).hex()
    require(rule in {'object-overlay', 'json-overlay'}, 'Unsupported frozen argument derivation')
    value = derive_cow_argument(spec['base'], prior, depth + 1)
    if rule == 'json-overlay':
        require(isinstance(value, str), 'JSON text overlay needs retained text')
        value = json.loads(value)
    require(isinstance(value, dict), 'Overlay needs an existing object')
    literal, derived = spec.get('overrides', {}), spec.get('derived_overrides', {})
    require(isinstance(literal, dict) and isinstance(derived, dict) and not literal.keys() & derived.keys(),
            'Conflicting frozen overlay fields')
    for path, replacement in [*literal.items(), *[(path, derive_cow_argument(item, prior, depth + 1))
                                                for path, item in derived.items()]]:
        require(isinstance(path, str) and path.startswith('/') and len(path) > 1, 'Overlay needs an explicit field pointer')
        parent_path, _, name = path.rpartition('/')
        parent = pointer(value, parent_path)
        name = name.replace('~1', '/').replace('~0', '~')
        require(isinstance(parent, dict) and name in parent, 'Overlay may only replace an existing object field')
        parent[name] = deepcopy(replacement)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')) if rule == 'json-overlay' else value


def order_uid_key(chain_id, uid):
    require(isinstance(uid, str) and bool(re.fullmatch(r'0x[0-9a-fA-F]{112}', uid)), 'Malformed 56-byte order UID')
    return uint(chain_id), uid.lower()


def normalize_order(order):
    require(isinstance(order, dict) and set(order) == {name for name, _ in ORDER_FIELDS},
            'Unexpected or missing signed order field')
    result = {}
    for name, kind in ORDER_FIELDS:
        value = order[name]
        if kind == 'address':
            value = address(value)
            require(int(value, 16) > 0, 'Explicit nonzero asset/receiver required')
        elif kind.startswith('uint'):
            value = uint(value, int(kind[4:]))
        elif kind == 'bytes32':
            require(isinstance(value, str) and bool(re.fullmatch(r'0x[0-9a-fA-F]{64}', value)), 'Malformed appData hash')
            value = value.lower()
        elif kind == 'bool':
            require(type(value) is bool, 'Expected a canonical signed boolean')
        else:
            require(isinstance(value, str), 'Expected a signed string')
        result[name] = value
    require(result['sellToken'] != result['buyToken'] and result['sellAmount'] > 0
            and result['buyAmount'] > 0 and result['validTo'] > 0, 'Invalid asset, amount or expiry')
    if (result['kind'] != 'sell' or result['partiallyFillable']
        or result['sellTokenBalance'] != 'erc20' or result['buyTokenBalance'] != 'erc20'):
        raise UnsupportedCowSwap('Only exact-input ERC20 fill-or-kill sell orders are adapted')
    return result


def domain_separator(domain):
    require(set(domain) == {'name', 'version', 'chainId', 'verifyingContract'}, 'Unexpected signing domain fields')
    return keccak(keccak(b'EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)')
        + keccak(domain['name'].encode()) + keccak(domain['version'].encode())
        + word(uint(domain['chainId'])) + bytes.fromhex(address(domain['verifyingContract'])[2:]).rjust(32, b'\0'))


def inspect_cow_order(material, expected, binding, app_data_policy):
    """Service payload pointers and partner-fee/provenance policy live in frozen data."""
    order = normalize_order(material['order'])
    owner = address(expected['owner'])
    domain = dict(material['domain'])
    domain['verifyingContract'] = address(domain['verifyingContract'])
    declared_domain = dict(binding['domain'])
    declared_domain['verifyingContract'] = address(declared_domain['verifyingContract'])
    require(domain == declared_domain and uint(domain['chainId']) == uint(binding['chain_id'])
            and uint(material['chain_id']) == uint(binding['chain_id'])
            and domain['verifyingContract'] == address(binding['settlement']), 'Domain or chain differs from reviewed binding')
    require(material['orderbook_url'] == binding['orderbook_url'], 'Orderbook differs from frozen protocol source')
    require(material['primary_type'] == 'Order'
            and material['types'] == {'Order': [{'name': name, 'type': kind} for name, kind in ORDER_FIELDS]},
            'Unexpected signed EIP-712 type')
    require(address(material['owner']) == owner == order['receiver'] == address(expected['recipient']),
            'Owner or own receiver differs from task')
    require(order['sellToken'] == address(expected['token_in'])
            and order['buyToken'] == address(expected['token_out']), 'Signed assets differ from task')
    require(order['sellAmount'] + order['feeAmount'] == uint(expected['amount_in'])
            and order['buyAmount'] == uint(expected['minimum_out']), 'Gross sell budget or exact signed minimum differs')
    if 'signed_fee_amount' in expected:
        require(order['feeAmount'] == uint(expected['signed_fee_amount']), 'Signed fee differs from frozen request')
    require(uint(expected['valid_to_min'], 32) <= order['validTo'] <= uint(expected['valid_to_max'], 32),
            'Signed deadline differs from request time/lifetime binding')
    full = material['full_app_data']
    require(isinstance(full, str), 'fullAppData must retain its exact UTF-8 text')
    app_hash = '0x' + keccak(full.encode('utf-8')).hex()
    require(material['app_data_hash'].lower() == order['appData'] == app_hash, 'Exact fullAppData bytes/hash differ')
    app = json.loads(full)
    require(isinstance(app, dict), 'appData is not an object')
    if app.get('metadata', {}).get('hooks'):
        raise UnsupportedCowSwap('Order hooks require a separate reviewed execution scope')
    for path, value in app_data_policy['required_values'].items():
        require(pointer(app, path) == value, 'appData differs from frozen declared policy at ' + path)
    for path, field in app_data_policy.get('task_values', {}).items():
        require(pointer(app, path) == expected[field], 'appData differs from frozen task parameter at ' + path)
    separator = domain_separator(domain)
    type_string = 'Order(' + ','.join(kind + ' ' + name for name, kind in ORDER_FIELDS) + ')'
    encoded = keccak(type_string.encode())
    for name, kind in ORDER_FIELDS:
        value = order[name]
        if kind == 'address':
            encoded += bytes.fromhex(value[2:]).rjust(32, b'\0')
        elif kind == 'bytes32':
            encoded += bytes.fromhex(value[2:])
        elif kind == 'string':
            encoded += keccak(value.encode())
        else:
            encoded += word(int(value) if kind == 'bool' else value)
    struct_hash = keccak(encoded)
    digest = keccak(b'\x19\x01' + separator + struct_hash)
    uid = '0x' + (digest + bytes.fromhex(owner[2:]) + order['validTo'].to_bytes(4, 'big')).hex()
    return {'chain_id': uint(binding['chain_id']), 'owner': owner, 'recipient': order['receiver'],
        'settlement': address(binding['settlement']), 'vault_relayer': address(binding['vault_relayer']),
        'order': order, 'gross_sell_raw': str(order['sellAmount'] + order['feeAmount']),
        'minimum_buy_raw': str(order['buyAmount']), 'signed_fee_raw': str(order['feeAmount']),
        'valid_to': order['validTo'], 'app_data_hash': app_hash,
        'domain_separator': '0x' + separator.hex(), 'order_struct_hash': '0x' + struct_hash.hex(),
        'order_digest': '0x' + digest.hex(), 'uid': uid}


def decode_trade(log, settlement):
    if address(log['address']) != address(settlement) or not log.get('topics') or log['topics'][0].lower() != TRADE_TOPIC:
        return None
    require(len(log['topics']) == 2 and not log.get('removed'), 'Trade topic or removed flag differs')
    owner_word = hex_bytes(log['topics'][1])
    raw = hex_bytes(log['data'])
    require(len(owner_word) == 32 and not any(owner_word[:12]) and len(raw) == 288, 'Malformed Trade ABI width')
    words = [raw[index:index + 32] for index in range(0, 192, 32)]
    require(not any(words[0][:12]) and not any(words[1][:12]) and int.from_bytes(words[5], 'big') == 192
            and int.from_bytes(raw[192:224], 'big') == 56 and not any(raw[280:288]), 'Noncanonical Trade ABI')
    uid = '0x' + raw[224:280].hex()
    owner = '0x' + owner_word[-20:].hex()
    require(uid[66:106] == owner[2:], 'UID owner and indexed Trade owner differ')
    return {'owner': owner, 'token_in': '0x' + words[0][-20:].hex(), 'token_out': '0x' + words[1][-20:].hex(),
        'sell_amount': int.from_bytes(words[2], 'big'), 'buy_amount': int.from_bytes(words[3], 'big'),
        'fee_amount': int.from_bytes(words[4], 'big'), 'uid': uid}


def transfer_net(receipt, token, owner):
    token, owner = address(token), address(owner)
    net = 0
    for log in receipt['logs']:
        if address(log['address']) != token or not log.get('topics') or log['topics'][0].lower() != TRANSFER_TOPIC:
            continue
        require(not log.get('removed') and len(log['topics']) == 3, 'Malformed or removed token transfer')
        sender, receiver = (hex_bytes(value) for value in log['topics'][1:])
        amount = hex_bytes(log['data'])
        require(len(sender) == len(receiver) == len(amount) == 32
                and not any(sender[:12]) and not any(receiver[:12]), 'Noncanonical token transfer ABI')
        value = int.from_bytes(amount, 'big')
        if '0x' + sender[-20:].hex() == owner:
            net -= value
        if '0x' + receiver[-20:].hex() == owner:
            net += value
    return net
