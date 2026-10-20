"""Fixed NPM enumeration slots; no Agent output, identity or network selection."""

from collections import Counter

from reputation_core.disclosure import _position
from reputation_platform.position_oracle import NPM, canonical_position_id
from reputation_platform.query_oracle import _hex, _quantity

RULE = 'pancakeswap-v3-enumeration-midpoints/v1'
TASK_COUNT = 14
SUPPLY_SELECTOR = '0x18160ddd'
INDEX_SELECTOR = '0x4f6ccce7'
POSITION_SELECTOR = '0x99fbab88'


def decode_uint256(raw: object) -> int:
    """Accept one exact ABI word, without coercion or trailing return values."""
    return int(_hex(raw, 64), 16)


def enumeration_indices(total_supply: int, count: int = TASK_COUNT) -> list[int | None]:
    if type(total_supply) is not int or not 0 <= total_supply < 2**256:
        raise ValueError('NPM supply must be an exact uint256 integer')
    if type(count) is not int or not 1 <= count <= TASK_COUNT:
        raise ValueError('Position enumeration requires a bounded number of fixed slots')
    return [((total_supply - 1) * (2 * slot + 1) // (2 * count)) if total_supply else None
            for slot in range(count)]


def plan_specs(block: str, total_supply: int | None = None, position_ids=()) -> dict:
    """Return exact operator-RPC specifications; the caller authenticates provenance."""
    _quantity(block)

    def call(data):
        return 'eth_call', [{'to': NPM, 'data': data}, block]

    specs = {'supply': call(SUPPLY_SELECTOR)}
    if total_supply is not None:
        specs.update({f'index-{index}': call(INDEX_SELECTOR + f'{index:064x}')
                      for index in dict.fromkeys(enumeration_indices(total_supply)) if index is not None})
    ids = list(position_ids)
    if len(ids) > 7 or len(set(ids)) != len(ids):
        raise ValueError('Only the seven different functional slots require position reads')
    for token_id in ids:
        canonical_position_id(token_id)
        specs['position-' + token_id] = call(POSITION_SELECTOR + f'{int(token_id):064x}')
    return specs


def planner_slots(total_supply: int, enumerated_values: dict, excluded_ids=()) -> list[dict]:
    """Freeze seven F then seven B slots; no missing or excluded slot is replaced.

    A tokenByIndex result from the authenticated NPM at the fixed snapshot proves
    NFT membership. B needs this eligibility fact, not a second functional truth
    check. The caller must bind every value to its exact request and snapshot.
    """
    indices = enumeration_indices(total_supply)
    excluded = set(excluded_ids)
    for token_id in excluded:
        canonical_position_id(token_id)
    allowed = {index for index in indices if index is not None}
    if (not isinstance(enumerated_values, dict)
        or any(type(index) is not int or index not in allowed for index in enumerated_values)):
        raise ValueError('Enumeration values must belong only to the predetermined indices')
    decoded = {}
    for index, raw in enumerated_values.items():
        try:
            decoded[index] = str(decode_uint256(raw))
        except (TypeError, ValueError):
            pass
    token_counts = Counter(decoded.get(index) for index in indices if index in decoded)
    slots = []
    for slot, index in enumerate(indices):
        purpose = 'functional' if slot < 7 else 'behavioral'
        token_id = decoded.get(index)
        if index is None:
            reason = 'empty_npm_supply'
        elif token_id is None:
            reason = 'enumeration_unavailable'
        elif token_counts[token_id] > 1:
            reason = 'duplicate_enumerated_position'
        elif purpose == 'behavioral' and token_id in excluded:
            reason = 'historical_functional_task_excluded'
        else:
            reason = None
        slots.append({'slot': slot, 'purpose': purpose, 'index': index, 'position_id': token_id,
                      'eligible': reason is None, 'reason': reason})
    return slots


def position_expected(raw_positions: object) -> dict:
    """Normalize the five immutable facts, without inventing an owner reference."""
    words = _position(raw_positions)
    ticks = [word - 2**256 if word >= 2**255 else word for word in words[5:7]]
    if any(not -887272 <= tick <= 887272 for tick in ticks):
        raise ValueError('Position ticks exceed PancakeSwap v3 bounds')
    return {'token0': f'0x{words[2]:040x}', 'token1': f'0x{words[3]:040x}',
            'fee': words[4], 'tickLower': ticks[0], 'tickUpper': ticks[1]}
