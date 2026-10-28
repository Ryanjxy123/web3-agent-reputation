"""Offline ABI/intent checks for three unsigned ERC20 swap protocols.

ABI sources: verified HydrexMultiRouter implementation 0x2e5e3d3fbfb77df85b3535fbefa09d61a8320aac,
verified Kyber MetaAggregationRouterV2 0x6131b5fae19ea4f9d964eac0408e4408b66337b5,
and 0xProject/0x-settler interfaces IAllowanceHolder/ISettlerTakerSubmitted/ISettlerActions.
These describe protocols, not a provider identity. Deployment/implementation binding,
current fee state, simulation and actual execution require separate source evidence.
No runtime paths, network, wallet, clock, provider verdicts or scores are used here.
"""
from datetime import datetime

from eth_hash.auto import keccak

from reputation_core.prediction_chain import selector
from reputation_core.swap import address, hex_bytes, integer

ZERO = '0x' + '00' * 20
EXEC = selector('exec(address,address,uint256,address,bytes)')
SETTLE = selector('execute((address,address,uint256),bytes[],bytes32)')
HYDREX = selector('executeSwaps((address,address,address,uint256,uint256,bytes,address,string,address,uint256)[],uint256)')
KYBER = selector('swap((address,address,bytes,(address,address,address[],uint256[],address[],uint256[],address,uint256,uint256,uint256,bytes),bytes))')
TRANSFER_FROM = selector('TRANSFER_FROM(address,((address,uint256),uint256,uint256),bytes)')
UNISWAP_V3_VIP = selector('UNISWAPV3_VIP(address,((address,uint256),uint256,uint256),bytes,bytes,uint256)')
BASIC = selector('BASIC(address,uint256,address,uint256,bytes)')
MAVERICK = selector('MAVERICKV2(address,address,uint256,address,bool,int32,uint256)')
SURPLUS = selector('POSITIVE_SLIPPAGE(address,address,uint256,uint256,uint256)')
NATIVE_CHECK = selector('NATIVE_CHECK(uint256,uint256)')


class UnsupportedUnsignedSwap(ValueError):
    """The ABI or execution mode is outside this decoder's explicit protocol scope."""


class UnsignedSwapMismatch(ValueError):
    """A decoded constraint contradicts the supplied independent task intent."""


def _check(value, reason):
    if not value:
        raise ValueError(reason)


def _hash(data):
    return '0x' + keccak(data).hex()


class _ABI:
    """Bounded ABI primitives for the documented structs/arrays below."""
    def __init__(self, data):
        self.data, self.end = data, 0

    def word(self, at):
        _check(type(at) is int and 0 <= at <= len(self.data) - 32, 'Incomplete ABI word')
        self.end = max(self.end, at + 32)
        return int.from_bytes(self.data[at:at + 32], 'big')

    def addr(self, at):
        value = self.word(at)
        _check(value < 2**160, 'Noncanonical ABI address')
        return f'0x{value:040x}'

    def pointer(self, base, slot, head_words):
        offset = self.word(base + slot * 32)
        _check(offset % 32 == 0 and offset >= head_words * 32, 'Invalid ABI dynamic offset')
        at = base + offset
        _check(at <= len(self.data) - 32, 'ABI dynamic offset outside calldata')
        return at

    def blob_at(self, at):
        length = self.word(at)
        begin, end = at + 32, at + 32 + length
        padded = begin + ((length + 31) // 32) * 32
        _check(padded <= len(self.data), 'Truncated ABI bytes')
        _check(not any(self.data[end:padded]), 'Nonzero ABI byte padding')
        self.end = max(self.end, padded)
        return self.data[begin:end]

    def blob(self, base, slot, head_words):
        return self.blob_at(self.pointer(base, slot, head_words))

    def array(self, base, slot, head_words, *, addresses=False, dynamic=False):
        at = self.pointer(base, slot, head_words)
        count = self.word(at)
        start = at + 32
        _check(count <= (len(self.data) - start) // 32, 'Truncated ABI array')
        if dynamic:
            return [self.pointer(start, i, count) for i in range(count)]
        return [(self.addr if addresses else self.word)(start + i * 32) for i in range(count)]


def _call(data, expected):
    raw = hex_bytes(data)
    if len(raw) < 4 or '0x' + raw[:4].hex() != expected:
        raise UnsupportedUnsignedSwap('Unexpected protocol function selector')
    return _ABI(raw[4:])


def _base(protocol, transaction, chain_id, token_in, token_out, amount, recipient, minimum):
    _check(chain_id > 0 and amount > 0 and minimum > 0, 'Positive chain, input and minimum required')
    _check(token_in != token_out, 'Swap assets must differ')
    if token_in in (ZERO, '0x' + 'ee' * 20) or token_out in (ZERO, '0x' + 'ee' * 20):
        raise UnsupportedUnsignedSwap('Native-token or zero-address assets are outside this ERC20 scope')
    return {'protocol': protocol, 'chain_id': chain_id, 'spender': address(transaction['to']),
        'token_in': token_in, 'token_out': token_out, 'amount_in': amount, 'recipient': recipient,
        'minimum_out': minimum, 'deadlines': [], 'fees': [], 'actions': [], 'opaque_payloads': [],
        'unsupported_actions': [], 'required_contracts': [address(transaction['to']), token_in, token_out],
        'deployment_verified': False, 'simulation_verified': False, 'execution_verified': False}


def _settler(transaction, chain_id):
    outer = _call(transaction['data'], EXEC)
    operator, token, amount, target = outer.addr(0), outer.addr(32), outer.word(64), outer.addr(96)
    if operator != target:
        raise UnsupportedUnsignedSwap('Only direct AllowanceHolder-to-Settler execution is supported')
    inner = outer.blob(0, 4, 5)
    abi = _call('0x' + inner.hex(), SETTLE)
    recipient, bought, minimum = abi.addr(0), abi.addr(32), abi.word(64)
    abi.word(128)  # zid/affiliate: retained in the calldata hash, not an instruction.
    actions = [abi.blob_at(at) for at in abi.array(0, 3, 5, dynamic=True)]
    fact = _base('0x-allowanceholder-settler', transaction, chain_id, token, bought, amount, recipient, minimum)
    fact['required_contracts'].append(target)
    transfer_count = 0
    for index, raw in enumerate(actions):
        sig, item = '0x' + raw[:4].hex(), _ABI(raw[4:])
        if sig == TRANSFER_FROM:
            transfer_count += 1
            _check(index == 0 and item.addr(0) == target and item.addr(32) == token
                and item.word(64) == amount and item.word(96) == 0 and item.blob(0, 5, 6) == b'',
                'Forwarded input transfer differs from the complete exact-input plan')
            deadline = item.word(128)
            fact['deadlines'].append({'kind': 'settler-transfer-permit', 'timestamp': deadline})
            fact['actions'].append({'kind': 'allowanceholder-transfer', 'target': target, 'token': token,
                                    'amount': amount, 'deadline': deadline})
        elif sig == UNISWAP_V3_VIP:
            # A VIP action pulls the permitted input and executes the V3 path in
            # one action. Its path omits the initial token, supplied by permit.
            transfer_count += 1
            _check(index == 0 and item.addr(0) == target and item.addr(32) == token
                   and item.word(64) == amount and item.word(96) == 0
                   and item.blob(0, 6, 8) == b'', 'VIP input, recipient or empty-signature allowance flow differs')
            path = item.blob(0, 5, 8)
            _check(path and len(path) % 44 == 0, 'Incomplete V3 VIP hop encoding')
            hops, current = [], token
            for offset in range(0, len(path), 44):
                hop = path[offset:offset + 44]
                output = '0x' + hop[24:44].hex()
                hops.append({'token_in': current, 'token_out': output, 'fork_id': hop[0],
                    'pool_id': int.from_bytes(hop[1:4], 'big'),
                    'sqrt_price_limit': int.from_bytes(hop[4:24], 'big'), 'pool_binding_verified': False})
                current = output
            _check(current == bought, 'VIP output path differs from Settler final output asset')
            deadline = item.word(128)
            fact['deadlines'].append({'kind': 'settler-vip-transfer-permit', 'timestamp': deadline})
            fact['actions'].append({'kind': 'uniswap-v3-vip', 'target': target, 'recipient': target,
                'token_in': token, 'token_out': bought, 'amount': amount, 'deadline': deadline,
                'action_minimum_out': item.word(224), 'hops': hops})
        elif sig == BASIC:
            sell, ppm, destination, offset = item.addr(0), item.word(32), item.addr(64), item.word(96)
            transfer = item.blob(0, 4, 5)
            if (sell not in (token, bought) or destination != sell or offset != 36 or ppm > 1_000_000
                    or len(transfer) != 68 or '0x' + transfer[:4].hex() != selector('transfer(address,uint256)')):
                fact['unsupported_actions'].append(f'BASIC action {index} is not a supported ERC20 fee transfer')
                continue
            args = _ABI(transfer[4:])
            fee = {'kind': 'settler-input-balance-fraction' if sell == token else 'settler-output-balance-fraction',
                   'token': sell, 'recipient': args.addr(0),
                   'ppm': ppm, 'denominator': 1_000_000, 'encoded_amount_overwritten': args.word(32),
                   'amount_basis': 'Settler token balance immediately before this action'}
            fact['fees'].append(fee)
            fact['actions'].append({'kind': 'erc20-transfer-fee', 'target': destination, 'fee': fee})
        elif sig == MAVERICK:
            _check(item.addr(0) == target and item.addr(32) == token and item.word(64) == 1_000_000,
                   'Maverick route does not consume the remaining input into this Settler')
            pool, token_a_in, tick = item.addr(96), item.word(128), item.word(160)
            tick = tick - 2**256 if tick >= 2**255 else tick
            _check(token_a_in in (0, 1) and -2**31 <= tick < 2**31, 'Invalid Maverick bool/int32')
            fact['required_contracts'].append(pool)
            fact['actions'].append({'kind': 'maverick-v2', 'target': pool, 'token_a_in': bool(token_a_in),
                'tick_limit': tick, 'pool_minimum_out': item.word(192), 'recipient': target,
                'pool_tokens_verified': False})
        elif sig == SURPLUS:
            receiver, fee_token = item.addr(0), item.addr(32)
            expected, surplus, cap = item.word(64), item.word(96), item.word(128)
            if fee_token != bought or surplus > 1_000_000 or cap > 1_000_000:
                fact['unsupported_actions'].append(f'Unsupported positive-slippage parameters at action {index}')
                continue
            fee = {'kind': 'positive-slippage', 'token': fee_token, 'recipient': receiver,
                'expected_amount': expected, 'surplus_ppm': surplus, 'max_ppm': cap, 'denominator': 1_000_000}
            fact['fees'].append(fee)
            fact['actions'].append({'kind': 'positive-slippage', 'fee': fee})
        elif sig == NATIVE_CHECK:
            deadline, value_bound = item.word(0), item.word(32)
            fact['deadlines'].append({'kind': 'settler-native-check', 'timestamp': deadline})
            fact['actions'].append({'kind': 'native-value-upper-bound', 'value_bound': value_bound})
        else:
            fact['unsupported_actions'].append(f'Unknown Settler action selector {sig}')
    _check(transfer_count == 1, 'One complete forwarded input transfer is required')
    fact['actions'].append({'kind': 'settler-final-minimum', 'token': bought, 'recipient': recipient, 'minimum': minimum})
    fact['trailing_bytes'] = len(outer.data) - outer.end
    return fact


def _hydrex(transaction, chain_id):
    abi = _call(transaction['data'], HYDREX)
    entries = abi.array(0, 0, 2, dynamic=True)
    if len(entries) != 1:
        raise UnsupportedUnsignedSwap('This exact-input scope supports one Hydrex swap per task')
    base = entries[0]
    router, sold, bought = abi.addr(base), abi.addr(base + 32), abi.addr(base + 64)
    amount, minimum = abi.word(base + 96), abi.word(base + 128)
    call = abi.blob(base, 5, 10)
    recipient = abi.addr(base + 192)
    origin = abi.blob(base, 7, 10).decode('utf-8')
    referral, referral_bps = abi.addr(base + 256), abi.word(base + 288)
    _check(referral == ZERO or referral_bps <= 100, 'Hydrex referral exceeds the documented maximum')
    fact = _base('hydrex-multirouter', transaction, chain_id, sold, bought, amount, recipient, minimum)
    fact['deadlines'].append({'kind': 'hydrex-execute-swaps', 'timestamp': abi.word(32)})
    fact['fees'].append({'kind': 'hydrex-output-protocol-fee', 'token': bought,
        'rate_source': 'feeBps() at the observation block', 'recipient_source': 'feeRecipient() at that block',
        'amount_basis': 'positive output balance delta', 'state_verified': False})
    if referral != ZERO:
        fact['fees'].append({'kind': 'hydrex-output-referral-fee', 'token': bought,
                            'recipient': referral, 'basis_points': referral_bps, 'denominator': 10_000})
    if '0x' + call[:4].hex() == HYDREX:
        raise UnsupportedUnsignedSwap('Recursive Hydrex wrappers are outside this scope')
    child = _decode({'to': router, 'data': '0x' + call.hex(), 'value': '0', 'from': transaction['to']}, chain_id)
    _check((child['token_in'], child['token_out'], child['amount_in'], child['recipient'])
           == (sold, bought, amount, address(transaction['to'])), 'Hydrex inner route differs from the wrapper intent')
    for field in ('deadlines', 'fees', 'actions', 'opaque_payloads', 'unsupported_actions', 'required_contracts'):
        fact[field].extend(child[field])
    fact['actions'].append({'kind': 'hydrex-net-output-transfer', 'target': bought, 'recipient': recipient,
        'minimum': minimum, 'origin': origin, 'router': router, 'clears_internal_router_allowance': True})
    fact['inner_minimum_out'] = child['minimum_out']
    fact['referral'], fact['referral_fee_bps'] = referral, referral_bps
    return fact


def _kyber(transaction, chain_id):
    abi = _call(transaction['data'], KYBER)
    base = abi.pointer(0, 0, 1)
    executor, approve_target = abi.addr(base), abi.addr(base + 32)
    payload = abi.blob(base, 2, 5)
    desc = abi.pointer(base, 3, 5)
    sold, bought = abi.addr(desc), abi.addr(desc + 32)
    receivers = abi.array(desc, 2, 11, addresses=True)
    amounts = abi.array(desc, 3, 11)
    fee_receivers = abi.array(desc, 4, 11, addresses=True)
    fee_amounts = abi.array(desc, 5, 11)
    recipient, amount, minimum, flags = abi.addr(desc + 192), abi.word(desc + 224), abi.word(desc + 256), abi.word(desc + 288)
    if recipient == ZERO:
        if 'from' not in transaction:
            raise UnsupportedUnsignedSwap('Implicit Kyber recipient requires an independently bound caller')
        recipient = address(transaction['from'])
    permit = abi.blob(desc, 10, 11)
    client_data = abi.blob(base, 4, 5)
    _check(len(receivers) == len(amounts) and len(fee_receivers) == len(fee_amounts)
           and sum(amounts) <= amount and executor != ZERO and payload, 'Inconsistent Kyber receivers or executor data')
    fact = _base('kyber-metaaggregation-v2', transaction, chain_id, sold, bought, amount, recipient, minimum)
    # The normal ERC20 path enforces recipient net balance delta. Other modes need their own checks.
    if flags & 0x3f:
        fact['unsupported_actions'].append('Kyber partial/native/claim/burn/simple execution mode is not supported')
    if permit:
        fact['unsupported_actions'].append('Kyber token permit is outside an unsigned exact-approval plan')
    fact['flags'], fact['unrecognized_flag_bits'] = flags, flags & ~0x1ff
    for destination, fee in zip(fee_receivers, fee_amounts):
        fact['fees'].append({'kind': 'kyber-explicit-router-fee', 'token': bought if flags & 0x40 else sold,
            'recipient': destination, 'amount_or_basis_points': fee, 'in_basis_points': bool(flags & 0x80)})
    fact['required_contracts'].append(executor)
    fact['opaque_payloads'].append({'kind': 'kyber-executor-route', 'target': executor,
        'data_hash': _hash(payload), 'byte_length': len(payload), 'deadline_and_pool_fees_decoded': False})
    fact['actions'].append({'kind': 'kyber-input-transfer', 'receivers': receivers, 'amounts': amounts,
        'executor': executor, 'approve_target': approve_target})
    fact['actions'].append({'kind': 'kyber-recipient-balance-minimum', 'token': bought,
                           'recipient': recipient, 'minimum': minimum})
    fact['client_data_hash'] = _hash(client_data)
    return fact


def _decode(transaction, chain_id):
    address(transaction['to'])
    if integer(transaction.get('value', 0)) != 0:
        raise UnsupportedUnsignedSwap('This module supports zero-native-value ERC20 swaps only')
    data = hex_bytes(transaction['data'])
    sig = '0x' + data[:4].hex()
    decoder = {EXEC: _settler, HYDREX: _hydrex, KYBER: _kyber}.get(sig)
    if decoder is None:
        raise UnsupportedUnsignedSwap(f'Unsupported unsigned-swap selector {sig}')
    return decoder(transaction, chain_id)


def decode_unsigned_swap(transaction, *, chain_id, quote_deadline=None):
    """Decode constraints; no deployment, simulation, provider or transaction PASS is inferred."""
    chain_id = integer(chain_id)
    if 'chainId' in transaction:
        _check(integer(transaction['chainId']) == chain_id, 'Transaction chain differs from the observation chain')
    fact = _decode(transaction, chain_id)
    if quote_deadline is not None:
        if isinstance(quote_deadline, str) and not quote_deadline.isdigit():
            value = datetime.fromisoformat(quote_deadline.replace('Z', '+00:00'))
            _check(value.tzinfo is not None, 'Quote deadline needs an explicit timezone')
            quote_deadline = int(value.timestamp())
        fact['deadlines'].append({'kind': 'declared-quote-expiry', 'timestamp': integer(quote_deadline)})
    fact['earliest_known_deadline'] = min((row['timestamp'] for row in fact['deadlines']), default=None)
    fact['deadline_decoding_complete'] = not fact['opaque_payloads'] and not fact['unsupported_actions']
    fact['call_shapes_supported'] = not fact['opaque_payloads'] and not fact['unsupported_actions']
    fact['encoded_fee_actions_decoded'] = not fact['opaque_payloads'] and not fact['unsupported_actions']
    fact['fee_state_verified'] = False  # AMM fees and mutable wrapper fees are not calldata facts.
    fact['required_contracts'] = sorted(set(fact['required_contracts']))
    fact['calldata_hash'] = _hash(hex_bytes(transaction['data']))
    return fact


def verify_unsigned_swap_intent(transaction, expected, *, chain_id, quote_deadline=None):
    """Bind decoded fields to an independent intent; this is not a complete F or B verdict."""
    _check({'token_in', 'token_out', 'amount_in', 'recipient', 'minimum_out'}.issubset(expected),
           'Independent swap intent requires all five binding fields')
    fact = decode_unsigned_swap(transaction, chain_id=chain_id, quote_deadline=quote_deadline)
    for field in ('token_in', 'token_out', 'recipient'):
        if fact[field] != address(expected[field]):
            raise UnsignedSwapMismatch(f'Decoded {field} differs from the task intent')
    for field in ('amount_in', 'minimum_out'):
        if fact[field] != integer(expected[field]):
            raise UnsignedSwapMismatch(f'Decoded {field} differs from the task intent')
    if fact['unsupported_actions']:
        raise UnsupportedUnsignedSwap('; '.join(fact['unsupported_actions']))
    fact['calldata_binding_verified'] = True
    return fact
