"""Documented free reads reviewed by the operator, not URLs from metadata."""

from reputation_core import MeasurementPurpose
from reputation_platform.safe_http import PublicTarget


PUBLIC_TARGETS = (
    PublicTarget("degen-discovery", "https://degenai.dev/x402"),
    PublicTarget("degen-jobs", "https://degenai.dev/erc8183"),
    PublicTarget(
        "degen-assets", "https://degenai.dev/x402/get_available_assets", "POST",
        MeasurementPurpose.AVAILABILITY, {"filter": "BTC"},
    ),
    PublicTarget(
        "arena-query", "https://agentarena.site/api/agent/8453/18500",
        purpose=MeasurementPurpose.AVAILABILITY,
    ),
    PublicTarget("brain-docs", "https://brainonbnb.com/services"),
    PublicTarget("catalog-degen", "https://api.8004scan.io/api/v1/agents/1/23121"),
    PublicTarget("catalog-arena", "https://api.8004scan.io/api/v1/agents/8453/18500"),
    PublicTarget("catalog-synthesis", "https://api.8004scan.io/api/v1/agents/8453/31929"),
    PublicTarget("catalog-brain", "https://api.8004scan.io/api/v1/agents/56/49467"),
    PublicTarget("brain-defi", "https://brainonbnb.com/defi"),
    PublicTarget("brain-agent", "https://agent.brainonbnb.com/lp/agent"),
    PublicTarget("brain-burns", "https://logs.brainonbnb.com/logs/burns.json"),
    PublicTarget("catalog-defi", "https://api.8004scan.io/api/v1/agents/56/363709"),
    PublicTarget(
        "brain-look-position", "https://agent.brainonbnb.com/lp/look?position=7637521",
        purpose=MeasurementPurpose.AVAILABILITY,
    ),
)
