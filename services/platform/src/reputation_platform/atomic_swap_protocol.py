"""Deterministic checks for an ERC20 / Permit2 / Universal Router atomic batch.

This scope uses the verified Slipstream router command dialect: path uint24 slots
are positive int24 tick spacings, not Uniswap fee tiers. Only exact input followed
by SWEEP, bounded approvals and zero cleanup are supported. Deployment, caller,
atomic execution, pool binding and recipient balance effects need independent
evidence. No network, database, clock, Agent identity or scores belong here.
"""
import json

from eth_hash.auto import keccak

from reputation_core.prediction_chain import selector
from reputation_core.swap import address, hex_bytes, integer
from reputation_platform.unsigned_swap_protocol import UnsupportedUnsignedSwap, UnsignedSwapMismatch


APPROVE = selector('approve(address,uint256)')
PERMIT2_APPROVE = selector('approve(address,address,uint160,uint48)')
EXECUTE = selector('execute(bytes,bytes[],uint256)')
ZERO = '0x' + '00' * 20
NATIVE = '0x' + 'ee' * 20
ADDRESS_THIS = '0x' + '00' * 19 + '02'
FIELDS = ('token_in', 'token_out', 'amount_in', 'recipient', 'minimum_out')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _word(data, offset, bits=256):
    _require(0 <= offset <= len(data) - 32, 'Incomplete ABI word')
    value = int.from_bytes(data[offset:offset + 32], 'big')
    _require(value < 2**bits, 'Noncanonical ABI integer width')
    return value


def _addr(data, offset):
    return f'0x{_word(data, offset, 160):040x}'


def _blob(data, offset):
    length = _word(data, offset)
    start = offset + 32
    end = start + length
    padded_end = start + ((length + 31) // 32) * 32
    _require(padded_end <= len(data), 'Truncated ABI bytes')
    _require(not any(data[end:padded_end]), 'Nonzero ABI bytes padding')
    return data[start:end], padded_end


def _args(call, signature, size=None):
    raw = hex_bytes(call['data'])
    if raw[:4] != bytes.fromhex(signature[2:]):
        raise UnsupportedUnsignedSwap('Unsupported atomic call selector')
    args = raw[4:]
    if size is not None:
        _require(len(args) == size, 'Noncanonical fixed ABI length')
    return args


def _execute(call):
    args = _args(call, EXECUTE)
    _require(_word(args, 0) == 96, 'Noncanonical commands offset')
    commands, end = _blob(args, 96)
    # Do not mask away ALLOW_REVERT or reserved flags. No permits, subplans,
    # arbitrary transfers, native legs or NFT commands are accepted.
    if commands != b'\x00\x04':
        raise UnsupportedUnsignedSwap('Only unflagged V3_SWAP_EXACT_IN then SWEEP are supported')
    _require(_word(args, 32) == end, 'Noncanonical inputs offset')
    base = end
    _require(_word(args, base) == 2, 'Exactly two command inputs required')
    inputs = []
    cursor = base + 96
    for index in range(2):
        _require(base + 32 + _word(args, base + 32 + index * 32) == cursor,
                 'Overlapping, gapped or noncanonical command inputs')
        value, cursor = _blob(args, cursor)
        inputs.append(value)
    _require(cursor == len(args), 'Unaccounted trailing execute bytes')
    deadline = _word(args, 64)
    _require(deadline > 0, 'A positive explicit router deadline is required')
    return inputs[0], inputs[1], deadline


def _path(raw):
    _require(len(raw) >= 43 and (len(raw) - 20) % 23 == 0, 'Incomplete Slipstream V3 path')
    tokens = ['0x' + raw[:20].hex()]
    hops = []
    for offset in range(20, len(raw), 23):
        spacing = int.from_bytes(raw[offset:offset + 3], 'big', signed=True)
        token = '0x' + raw[offset + 3:offset + 23].hex()
        _require(0 < spacing < 2**23, 'Positive int24 tick spacing required')
        _require(token != tokens[-1], 'A path hop must change tokens')
        hops.append({'token_in': tokens[-1], 'token_out': token, 'tick_spacing': spacing,
                     'pool_binding_verified': False})
        tokens.append(token)
    _require(all(x not in (ZERO, NATIVE) for x in tokens), 'Only explicit ERC20 path assets supported')
    return tokens, hops


def _approve(call):
    args = _args(call, APPROVE, 64)
    return _addr(args, 0), _word(args, 32)


def _permit2_approve(call):
    args = _args(call, PERMIT2_APPROVE, 128)
    return _addr(args, 0), _addr(args, 32), _word(args, 64, 160), _word(args, 96, 48)


def normalize_atomic_swap(plan, *, quote_deadline=None):
    """Parse the explicit seven-call dialect; never authorize its execution.

    `plan` is {chain_id, calls}; each call has to/data/value and optional label,
    from, chain_id/chainId. Targets are not trusted deployments by their address.
    All calls must later execute as ordinary CALLs, in order, by the required
    executor in ONE atomic batch. Independent evidence must establish that fact.
    """
    _require(isinstance(plan, dict) and set(plan) == {'chain_id', 'calls'}, 'Expected chain_id and calls')
    chain_id = integer(plan['chain_id'])
    _require(chain_id > 0, 'Positive chain id required')
    calls = plan['calls']
    if not isinstance(calls, list) or len(calls) != 7:
        raise UnsupportedUnsignedSwap('This scope requires exactly seven ordered atomic calls')
    normalized = []
    for call in calls:
        _require(isinstance(call, dict) and {'to', 'data', 'value'}.issubset(call), 'Incomplete atomic CALL')
        if set(call) - {'to', 'data', 'value', 'label', 'from', 'chain_id', 'chainId'}:
            raise UnsupportedUnsignedSwap('Unsupported atomic CALL attributes or execution mode')
        _require(integer(call['value']) == 0, 'Only zero-native-value atomic CALLs supported')
        for field in ('chain_id', 'chainId'):
            if field in call:
                _require(integer(call[field]) == chain_id, 'Atomic CALL chain differs from plan')
        normalized.append({'to': address(call['to']), 'data': '0x' + hex_bytes(call['data']).hex(), 'value': 0})
    token_in, permit2, router = normalized[0]['to'], normalized[3]['to'], normalized[4]['to']
    _require(len({token_in, permit2, router}) == 3 and ZERO not in (token_in, permit2, router),
             'Distinct nonzero token, Permit2 and router targets required')
    _require([x['to'] for x in normalized] == [token_in, token_in, token_in, permit2, router, permit2, token_in],
             'Atomic target order differs from bounded approval/swap/cleanup')

    v3, sweep, deadline = _execute(normalized[4])
    _require(len(v3) >= 160 and _word(v3, 96) == 160, 'Noncanonical V3 path offset')
    path, end = _blob(v3, 160)
    _require(end == len(v3), 'Unaccounted trailing V3 input bytes')
    _require(_word(v3, 128) == 1, 'V3 input must be paid by the atomic executor through Permit2')
    _require(_addr(v3, 0) in (router, ADDRESS_THIS), 'V3 output must stay in router until SWEEP')
    amount = _word(v3, 32, 160)
    inner_minimum = _word(v3, 64)
    _require(amount > 0, 'Positive bounded exact input required')
    tokens, hops = _path(path)
    token_out = tokens[-1]
    _require(tokens[0] == token_in and token_out != token_in, 'Approval token and path endpoints differ')
    _require(len(sweep) == 96, 'Noncanonical SWEEP ABI length')
    _require(_addr(sweep, 0) == token_out, 'SWEEP asset differs from V3 output')
    recipient = _addr(sweep, 32)
    # map(address(1)) means lockedBy, whose identity is not encoded. Keep the
    # explicit-recipient scope instead of pretending it is an external address.
    if int(recipient, 16) <= 2 or recipient in (router, permit2):
        raise UnsupportedUnsignedSwap('An explicit external SWEEP recipient is required')
    minimum = _word(sweep, 64, 160)  # Verified fork dispatch truncates this to uint160.
    _require(minimum > 0, 'Positive final output minimum required')
    for call in calls:
        if 'from' in call:
            _require(address(call['from']) == recipient, 'Atomic CALL sender differs from required executor')

    _require([_approve(normalized[i]) for i in (0, 1, 2, 6)] ==
             [(router, 0), (permit2, 0), (permit2, amount), (permit2, 0)],
             'ERC20 approvals must be exact, with both initial resets and zero cleanup')
    approved_token, approved_router, approved_amount, expiration = _permit2_approve(normalized[3])
    cleared_token, cleared_router, cleared_amount, cleared_expiration = _permit2_approve(normalized[5])
    _require((approved_token, approved_router, approved_amount) == (token_in, router, amount),
             'Permit2 approval differs from exact input and router')
    _require((cleared_token, cleared_router, cleared_amount) == (token_in, router, 0),
             'Permit2 cleanup must clear the same token/router allowance')
    _require(expiration > 0, 'A positive explicit Permit2 expiration is required')
    deadlines = [{'kind': 'router-execute', 'timestamp': deadline},
                 {'kind': 'permit2-allowance-expiration', 'timestamp': expiration}]
    if quote_deadline is not None:
        quote_deadline = integer(quote_deadline)
        _require(quote_deadline > 0, 'Positive quote deadline required')
        deadlines.append({'kind': 'declared-quote-expiry', 'timestamp': quote_deadline})
    state_reads = []
    for spender in (permit2, router):
        state_reads.append({'target': token_in, 'signature': 'allowance(address,address)',
            'args': [recipient, spender], 'phases': ['before', 'after'], 'required_after': 0})
    state_reads.append({'target': permit2, 'signature': 'allowance(address,address,address)',
        'args': [recipient, token_in, router], 'phases': ['before', 'after'],
        'outputs': ['amount:uint160', 'expiration:uint48', 'nonce:uint48'], 'required_after_amount': 0})
    for token, owner in ((token_in, recipient), (token_out, recipient), (token_in, router), (token_out, router)):
        state_reads.append({'target': token, 'signature': 'balanceOf(address)', 'args': [owner],
                            'phases': ['before', 'after']})
    serialized = json.dumps({'chain_id': chain_id, 'calls': normalized}, sort_keys=True, separators=(',', ':')).encode()
    return {'protocol': 'universal-router-slipstream-v3-atomic-v1', 'chain_id': chain_id,
        'router': router, 'permit2': permit2, 'spender': permit2, 'token_in': token_in, 'token_out': token_out,
        'amount_in': amount, 'recipient': recipient, 'required_executor': recipient, 'minimum_out': minimum,
        'inner_swap_minimum_out': inner_minimum, 'minimum_out_check': 'router-total-token-balance-before-sweep',
        'recipient_balance_delta_verified': False, 'requires_router_output_balance_accounting': True,
        'atomic_required': True, 'atomic_execution_verified': False, 'calls': normalized,
        'call_types': ['CALL'] * 7, 'commands': ['V3_SWAP_EXACT_IN', 'SWEEP'], 'commands_hex': '0x0004',
        'path_hex': '0x' + path.hex(), 'path_encoding': 'address/int24-tick-spacing/address', 'path_hops': hops,
        'deadlines': deadlines, 'earliest_known_deadline': min(x['timestamp'] for x in deadlines),
        'permit2_cleanup_expiration': cleared_expiration, 'approval_amount': amount,
        'encoded_cleanup_amounts': {'token_to_permit2': 0, 'token_to_router': 0, 'permit2_to_router': 0},
        'required_state_reads': state_reads,
        'required_deployment_bindings': [{'target': router, 'method': 'verified-constructor-immutables',
            'parameters': ['permit2', 'clFactory', 'clImplementation'], 'getter_available': False,
            'required_permit2': permit2}],
        'required_pool_bindings': [{'factory_role': 'clFactory-from-verified-deployment',
            'signature': 'getPool(address,address,int24)',
            'args': sorted([hop['token_in'], hop['token_out']]) + [hop['tick_spacing']],
            'pool_getters': ['token0()', 'token1()', 'tickSpacing()'],
            'erc1167_implementation_role': 'clImplementation-from-verified-deployment',
            'pool_binding_verified': False} for hop in hops],
        'required_contracts': sorted({router, permit2, *tokens}), 'fees': [], 'fee_state_verified': False,
        'opaque_payloads': [], 'unsupported_actions': [], 'call_shapes_supported': True,
        'deadline_decoding_complete': True, 'deployment_verified': False, 'simulation_verified': False,
        'execution_verified': False, 'call_sequence_hash': '0x' + keccak(serialized).hex()}


def verify_atomic_swap_intent(plan, expected, *, quote_deadline=None):
    """Bind decoded fields to independent constraints; no F/B score is produced."""
    _require(isinstance(expected, dict) and set(FIELDS).issubset(expected),
             'Independent atomic swap intent requires all five binding fields')
    fact = normalize_atomic_swap(plan, quote_deadline=quote_deadline)
    for field in ('token_in', 'token_out', 'recipient', 'router', 'permit2'):
        if field in expected and fact[field] != address(expected[field]):
            raise UnsignedSwapMismatch(f'Decoded {field} differs from independent atomic intent')
    for field in ('amount_in', 'minimum_out', 'chain_id'):
        if field in expected and fact[field] != integer(expected[field]):
            raise UnsignedSwapMismatch(f'Decoded {field} differs from independent atomic intent')
    if 'executor' in expected and fact['required_executor'] != address(expected['executor']):
        raise UnsignedSwapMismatch('Atomic executor differs from independent task intent')
    if 'deadline' in expected and fact['deadlines'][0]['timestamp'] != integer(expected['deadline']):
        raise UnsignedSwapMismatch('Router deadline differs from independent task intent')
    fact['calldata_binding_verified'] = True
    return fact
