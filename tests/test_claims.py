import hashlib
import unittest

from reputation_core import (
    BusinessClaim,
    ClaimCitation,
    DeclarationAnalysis,
    SourceDocument,
    validate_analysis,
)


class ClaimCitationTests(unittest.TestCase):
    def test_source_quote_is_accepted_and_fabricated_quote_is_rejected(self) -> None:
        text = "This fixture agent returns the BNB balance of a wallet."
        digest = hashlib.sha256(text.encode()).hexdigest()
        source = SourceDocument(
            source_id="fixture-doc", url="https://example.test/docs",
            raw_sha256=digest, projection_sha256=digest, text=text,
        )
        claim = BusinessClaim(
            claim_id="fixture-balance", operation="get_balance",
            description="Return the BNB balance of a wallet.",
            inputs=["wallet"], outputs=["BNB balance"], constraints=["read only"],
            access="free", citations=[ClaimCitation(source_id=source.source_id,
                                                   quote="returns the BNB balance of a wallet")],
        )
        analysis = DeclarationAnalysis(claims=[claim], gaps=[])
        self.assertIs(validate_analysis(analysis, [source]), analysis)

        fabricated = claim.model_copy(update={"citations": [ClaimCitation(
            source_id=source.source_id, quote="transfers BNB to another wallet",
        )]})
        with self.assertRaisesRegex(ValueError, "quote not found"):
            validate_analysis(analysis.model_copy(update={"claims": [fabricated]}), [source])
