"""Pure planner checks use synthetic ABI values, never real evaluation samples."""

import unittest

from reputation_platform.position_oracle import NPM
from reputation_platform.position_planner import (
    INDEX_SELECTOR, POSITION_SELECTOR, SUPPLY_SELECTOR, decode_uint256,
    enumeration_indices, plan_specs, planner_slots, position_expected,
)
from test_position_oracle import TOKEN0, TOKEN1, position_bytes


def word(value):
    return '0x' + f'{value:064x}'


class PositionPlannerTests(unittest.TestCase):
    def test_fixed_midpoints_and_exact_rpc_specs_are_independent_of_agent(self):
        indices = enumeration_indices(5251723)
        self.assertEqual(indices, [(5251722 * (2 * slot + 1)) // 28 for slot in range(14)])
        self.assertEqual(len(set(indices)), 14)
        specs = plan_specs('0x64', 5251723, ('123', '124'))
        self.assertEqual(specs['supply'], ('eth_call', [{'to': NPM, 'data': SUPPLY_SELECTOR}, '0x64']))
        self.assertEqual(specs['index-' + str(indices[0])], ('eth_call', [
            {'to': NPM, 'data': INDEX_SELECTOR + f'{indices[0]:064x}'}, '0x64']))
        self.assertEqual(specs['position-123'], ('eth_call', [
            {'to': NPM, 'data': POSITION_SELECTOR + f'{123:064x}'}, '0x64']))

    def test_fourteen_disjoint_slots_keep_unavailable_and_old_functional_tasks(self):
        indices = enumeration_indices(1000)
        values = {index: word(100 + slot) for slot, index in enumerate(indices)}
        values.pop(indices[2])
        values[indices[10]] = '0x01'
        slots = planner_slots(1000, values, ('107',))
        self.assertEqual(len(slots), 14)
        self.assertEqual([s['purpose'] for s in slots], ['functional'] * 7 + ['behavioral'] * 7)
        self.assertEqual([s['slot'] for s in slots], list(range(14)))
        self.assertEqual(slots[2]['reason'], 'enumeration_unavailable')
        self.assertEqual(slots[7]['reason'], 'historical_functional_task_excluded')
        self.assertEqual(slots[7]['position_id'], '107')
        self.assertEqual(slots[10]['reason'], 'enumeration_unavailable')
        self.assertEqual(slots[11]['position_id'], '111')
        f_ids = {s['position_id'] for s in slots[:7] if s['eligible']}
        b_ids = {s['position_id'] for s in slots[7:] if s['eligible']}
        self.assertFalse(f_ids & b_ids)
        self.assertNotIn('107', b_ids)

    def test_empty_small_and_conflicting_enumeration_never_create_duplicate_tasks(self):
        self.assertEqual(enumeration_indices(0), [None] * 14)
        self.assertTrue(all(not s['eligible'] for s in planner_slots(0, {})))
        self.assertTrue(all(not s['eligible'] for s in planner_slots(1, {0: word(123)})))
        specs = plan_specs('0x64', 1)
        self.assertEqual(len(specs), 2)
        indices = enumeration_indices(1000)
        values = {index: word(slot + 100) for slot, index in enumerate(indices)}
        values[indices[13]] = values[indices[0]]
        slots = planner_slots(1000, values)
        self.assertEqual(slots[0]['reason'], 'duplicate_enumerated_position')
        self.assertEqual(slots[13]['reason'], 'duplicate_enumerated_position')
        self.assertEqual(sum(s['eligible'] for s in slots), 12)

    def test_uint256_schema_and_bounds_are_exact(self):
        self.assertEqual(decode_uint256(word(2**256 - 1)), 2**256 - 1)
        self.assertEqual(decode_uint256(word(0)), 0)
        for raw in (None, 1, True, '0x0', '0x' + '0' * 63, word(1) + '00', '0x' + 'z' * 64):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode_uint256(raw)
        for supply in (True, -1, 1.0, '14', 2**256):
            with self.subTest(supply=supply), self.assertRaises(ValueError):
                enumeration_indices(supply)
        for count in (True, 0, 15, 1.5):
            with self.assertRaises(ValueError):
                enumeration_indices(100, count)
        with self.assertRaises(ValueError):
            planner_slots(100, {True: word(1)})
        with self.assertRaises(ValueError):
            planner_slots(100, {999: word(1)})
        with self.assertRaises(ValueError):
            planner_slots(100, {}, ('001',))
        for block in ('latest', '0x064'):
            with self.assertRaises(ValueError):
                plan_specs(block)
        with self.assertRaises(ValueError):
            plan_specs('0x64', position_ids=('123', '123'))

    def test_functional_reference_reuses_strict_abi_without_dynamic_field_scoring(self):
        expected = {'token0': TOKEN0, 'token1': TOKEN1, 'fee': 500, 'tickLower': -100, 'tickUpper': 100}
        self.assertEqual(position_expected(position_bytes()), expected)
        self.assertEqual(position_expected(position_bytes(liquidity=0, owed0=999)), expected)
        for changes in ({'token0': 0}, {'fee': 0}, {'tickLower': 100},
                        {'tickLower': 2**24 - 100}, {'tickLower': -887273}, {'tickUpper': 887273}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                position_expected(position_bytes(**changes))
        with self.assertRaises(ValueError):
            position_expected('0x')


if __name__ == '__main__':
    unittest.main()
