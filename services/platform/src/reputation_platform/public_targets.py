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
    PublicTarget(
        "brain-job-health-56657", "https://agent.brainonbnb.com/job/56657/result",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "brain-job-grid-56670", "https://agent.brainonbnb.com/job/56670/result",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "brain-job-yield-56850", "https://agent.brainonbnb.com/job/56850/result",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget("brain-burns", "https://logs.brainonbnb.com/logs/burns.json"),
    PublicTarget("catalog-defi", "https://api.8004scan.io/api/v1/agents/56/363709"),
    PublicTarget(
        "brain-look-position", "https://agent.brainonbnb.com/lp/look?position=7637521",
        purpose=MeasurementPurpose.AVAILABILITY,
    ),
    PublicTarget(
        "custos-snapshot", "https://trycustos.xyz/api/snapshot",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "custos-decisions", "https://trycustos.xyz/api/decisions",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "olas-registration-2182", "https://marketplace.olas.network/api/erc8004/gnosis/ai-agents/2182",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "olas-manifest-2182",
        "https://gateway.autonolas.tech/ipfs/f01701220dd974e01447d4b3fcc180e9320fb0bbd452ca374407c99a876e420a07be88c29",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget(
        "olas-analytics-2182",
        "https://mech-analytics-api.autonolas.tech/v1/metrics/mech/100/0xc05e7412439bd7e91730a6880e18d5d5873f632c",
        purpose=MeasurementPurpose.BACKGROUND,
    ),
    PublicTarget("catalog-delu", "https://api.8004scan.io/api/v1/agents/8453/30004"),
    PublicTarget("catalog-clicks", "https://api.8004scan.io/api/v1/agents/8453/45074"),
    PublicTarget("clicks-registration", "https://clicksprotocol.xyz/.well-known/agent-registration.json"),
    PublicTarget("clicks-mcp-document", "https://clicksprotocol.xyz/mcp/server.json"),
    PublicTarget(
        "clicks-initialize", "https://mcp.clicksprotocol.xyz/mcp", "POST",
        json_body={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "web3-reputation-readonly", "version": "0.1.0"}}},
    ),
    PublicTarget(
        "clicks-tools", "https://mcp.clicksprotocol.xyz/mcp", "POST",
        json_body={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ),
    PublicTarget(
        "clicks-split-query", "https://mcp.clicksprotocol.xyz/mcp", "POST",
        json_body={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "clicks_simulate_split", "arguments": {
                "amount": "1.234567", "agent_address": "0xf873bb73e10d24cd3cf9bbed917f5e2d07da8b80"}}},
    ),
)
