"""A matched V3 task set owns F slots; unsupported capabilities retain old dispatch."""

import unittest
from unittest.mock import Mock, patch

from reputation_platform.checker_dispatch import collect_business_checks


class PositionDispatchTests(unittest.TestCase):
    def test_matched_position_suppresses_erc20_without_agent_id_branch(self):
        position = Mock(return_value=(['position-capability'], ['seven-frozen-tasks'], ['position-scope']))
        transfer = Mock(return_value=(['erc20'], ['eighth-task'], []))
        mech = Mock(return_value=([], [], []))
        with patch('reputation_platform.checker_dispatch.BUSINESS_CHECKERS', (
            ('query.pancakeswap-v3-position', position), ('query.erc20-transfer-record', transfer), ('mech', mech))):
            capabilities, samples, limits = collect_business_checks({'canonical': 'any-verified-identity'}, object())
        self.assertEqual(capabilities, ['position-capability'])
        self.assertEqual(samples, ['seven-frozen-tasks'])
        self.assertEqual(len(limits), 2)
        transfer.assert_not_called()
        mech.assert_called_once()

    def test_no_match_preserves_existing_erc20_and_mech_collectors(self):
        position = Mock(return_value=([], [], []))
        transfer = Mock(return_value=(['erc20'], ['single-query-task'], ['old-scope']))
        mech = Mock(return_value=(['history'], ['behavioral-tasks'], []))
        with patch('reputation_platform.checker_dispatch.BUSINESS_CHECKERS', (
            ('query.pancakeswap-v3-position', position), ('query.erc20-transfer-record', transfer), ('mech', mech))):
            self.assertEqual(collect_business_checks({}, object()),
                             (['erc20', 'history'], ['single-query-task', 'behavioral-tasks'], ['old-scope']))
        transfer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
