"""One focused structural selector test, without provider names or network access."""

import hashlib
import unittest

from reputation_core import (
    AdmissionCheck, BusinessClaim, CandidateRecord, CheckCode, ClaimCitation, DeclarationAnalysis,
    PredictionHistoryDescriptor, PredictionToolDescriptor, SourceDocument, Verdict,
    select_prediction_plan, validate_analysis,
)


class PredictionPlanningTests(unittest.TestCase):
    def test_cited_structure_and_missing_or_misleading_metadata(self) -> None:
        description = "Make binary predictions on markets using the supplied question."
        digest = hashlib.sha256(description.encode()).hexdigest()
        source = SourceDocument(source_id="source", url="https://example.test/metadata",
                                raw_sha256=digest, projection_sha256=digest, text=description)
        claim = BusinessClaim(claim_id="forecast-claim", operation="unrelated_tool_v2",
            description="Forecast a binary market question.", inputs=["question text"],
            outputs=["p_yes and p_no"], constraints=[], access="unknown",
            citations=[ClaimCitation(source_id="source", quote=description)])
        analysis = validate_analysis(DeclarationAnalysis(claims=[claim], gaps=[]), [source])
        candidate = CandidateRecord(key="independent-provider", name="An unrelated name",
            registration_reference="eip155:100:0x" + "11" * 20 + ":5678",
            source_urls=[source.url], next_actions=[], checks=[
                AdmissionCheck(code=code, status=Verdict.UNKNOWN, explanation="Not verified", evidence=[])
                for code in CheckCode])
        tool = PredictionToolDescriptor(operation=claim.operation, description=description,
            input_type="text", output_type="object", result_type="string",
            required_output_fields=["requestId", "prompt", "result"], probability_fields=["p_yes", "p_no"])
        descriptor = PredictionHistoryDescriptor(candidate_key=candidate.key, claim_ids=[claim.claim_id],
            tools=[tool], chain_id=100, protocol="olas-mech-marketplace", metadata_source_id=source.source_id,
            metadata_source_file="runtime/fixture/metadata.response.bin", input_format="ipfs-v0.1",
            output_format="ipfs-v0.1", published_mech="0x" + "22" * 20, service_id="1234",
            history_shape="omen-binary-request-v1", history_source_file="runtime/fixture/request.response.bin",
            history_tool=tool.operation, history_context_type="omen", history_market="0x" + "33" * 20,
            history_prompt="Will the event happen? Give the p_yes and p_no probabilities.")
        selected = select_prediction_plan(analysis, candidate, descriptor)
        self.assertEqual((selected.status, selected.policy_id), ("SELECTED", "prediction-history-v1"))
        self.assertIn("execution_binding: UNKNOWN", selected.pending_evidence)
        cases = [
            (analysis, descriptor.model_copy(update={"protocol": None}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"history_source_file": None}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"service_id": "0"}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"chain_id": 1}), "UNSUPPORTED"),
            (analysis, descriptor.model_copy(update={"history_context_type": "another-market"}), "UNSUPPORTED"),
            (analysis, descriptor.model_copy(update={"claim_ids": ["absent"]}), "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"claim_ids": []}), "NEEDS_INFO"),
            (analysis.model_copy(update={"claims": [claim.model_copy(update={"citations": []})]}),
             descriptor, "NEEDS_INFO"),
            (analysis.model_copy(update={"claims": [claim.model_copy(update={"operation": "invented"})]}),
             descriptor, "NEEDS_INFO"),
            (analysis, descriptor.model_copy(update={"tools": [tool.model_copy(update={
                "description": "Validate code, repair snippets and execute programs."})]}), "UNSUPPORTED"),
        ]
        for altered_analysis, altered_descriptor, status in cases:
            with self.subTest(status=status, descriptor=altered_descriptor):
                result = select_prediction_plan(altered_analysis, candidate, altered_descriptor)
                self.assertEqual(result.status, status)
                self.assertIsNone(result.policy_id)


if __name__ == "__main__":
    unittest.main()
