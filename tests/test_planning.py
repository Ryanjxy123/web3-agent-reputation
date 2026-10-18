"""Plan selection is independent of already passing the eventual evaluation."""

import unittest

from reputation_core import AdmissionCheck, BusinessClaim, CandidateRecord, CheckCode, ClaimCitation, DeclarationAnalysis, Verdict
from reputation_core.planning import LiquidityHistoryDescriptor, select_plan


class PlanSelectionTests(unittest.TestCase):
    def test_structural_selection_and_missing_or_unsupported_sources(self) -> None:
        candidate = CandidateRecord(
            key="unrelated-provider", name="An independent test provider",
            registration_reference="https://example.test/registration",
            source_urls=["https://example.test/docs"], next_actions=[],
            checks=[AdmissionCheck(code=code, status=Verdict.UNKNOWN,
                                   explanation="Not independently checked yet", evidence=[])
                    for code in CheckCode],
        )
        claim = BusinessClaim(
            claim_id="published-increases", operation="Published liquidity operations",
            description="The provider publishes historical liquidity increases.",
            inputs=[], outputs=["execution records"], constraints=["read-only history"], access="unknown",
            citations=[ClaimCitation(source_id="fixture-doc", quote="We publish historical liquidity increases.")],
        )
        analysis = DeclarationAnalysis(claims=[claim], gaps=[])
        descriptor = LiquidityHistoryDescriptor(
            candidate_key=candidate.key, claim_ids=[claim.claim_id], chain_id=56,
            protocol="pancakeswap-v3-npm", history_shape="run-history-increase-v1",
            history_source_file="runtime/fixture/history.response.bin", history_json_path="$.history",
            published_execution_wallet="0x" + "11" * 20, trusted_manager="0x" + "22" * 20,
        )
        selected = select_plan(analysis, candidate, descriptor)
        self.assertEqual(selected.status, "SELECTED")
        self.assertEqual(selected.policy_id, "liquidity-history-v1")
        self.assertIn("execution_binding: UNKNOWN", selected.pending_evidence)

        cases = [
            (analysis, descriptor.model_copy(update={"claim_ids": ["absent"]}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"chain_id": 1}), "UNSUPPORTED"),
            (analysis, descriptor.model_copy(update={"protocol": None}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"claim_ids": [claim.claim_id] * 2}), "NEEDS_INFO"),
            (analysis.model_copy(update={"claims": [claim, claim]}), descriptor, "NEEDS_INFO"),
        ]
        for altered_analysis, altered_descriptor, status in cases:
            with self.subTest(status=status, descriptor=altered_descriptor):
                selection = select_plan(altered_analysis, candidate, altered_descriptor)
                self.assertEqual(selection.status, status)
                self.assertIsNone(selection.policy_id)
