import os

from google.adk import Agent

from .bedrock_model import BedrockClaude
from .mcp_tools import get_mcp_tools
from .prompts_loader import build_instruction

# Set service name from environment variable for OpenTelemetry
os.environ.setdefault('OTEL_SERVICE_NAME', 'econresearch')

from google.adk.telemetry.setup import maybe_set_otel_providers
maybe_set_otel_providers()


# Curated offline snapshot of key U.S. economic indicators, keyed by FRED
# series ID. A follow-up lab can swap this for live data from the FRED MCP
# server through Agentgateway (see labs/mcp/fred-mcp.md).
ECON_SERIES = {
    "FEDFUNDS": {
        "name": "Effective Federal Funds Rate",
        "value": 3.90,
        "unit": "percent, annualized",
        "as_of": "2026-05-31",
    },
    "CPIAUCSL": {
        "name": "Consumer Price Index for All Urban Consumers (All Items)",
        "value": 331.2,
        "unit": "index, 1982-1984=100, seasonally adjusted",
        "as_of": "2026-05-31",
        "note": "approximately +2.7% year-over-year",
    },
    "UNRATE": {
        "name": "Unemployment Rate",
        "value": 4.2,
        "unit": "percent, seasonally adjusted",
        "as_of": "2026-05-31",
    },
    "DGS10": {
        "name": "10-Year Treasury Constant Maturity Rate",
        "value": 4.15,
        "unit": "percent, annualized",
        "as_of": "2026-06-27",
    },
    "MORTGAGE30US": {
        "name": "30-Year Fixed Rate Mortgage Average",
        "value": 6.42,
        "unit": "percent, annualized",
        "as_of": "2026-06-25",
    },
}


def list_series() -> list[dict]:
    """List the economic data series available in this assistant's snapshot.

    Returns one entry per series with its FRED series ID, human-readable
    name, unit, and the as-of date of the snapshot value.
    """
    return [
        {"series_id": sid, "name": s["name"], "unit": s["unit"], "as_of": s["as_of"]}
        for sid, s in ECON_SERIES.items()
    ]


def get_series_latest(series_id: str) -> dict:
    """Get the latest snapshot value for one economic series.

    Args:
        series_id: FRED series ID, e.g. FEDFUNDS, CPIAUCSL, UNRATE, DGS10,
            MORTGAGE30US. Case-insensitive.

    Returns the series name, value, unit, and as-of date, or an error with
    the list of valid series IDs if the ID is unknown.
    """
    sid = series_id.strip().upper()
    if sid not in ECON_SERIES:
        return {
            "error": f"unknown series_id '{series_id}'",
            "available_series_ids": sorted(ECON_SERIES),
        }
    return {"series_id": sid, **ECON_SERIES[sid]}


def create_model():
    """Use an AWS Bedrock Claude model via the anthropic[bedrock] SDK.

    LiteLLM's bedrock translation is known to drop tool descriptions; the
    custom BedrockClaude adapter (vendored from solo-io/agentregistry-dev-samples)
    talks to Bedrock via anthropic.AnthropicBedrock directly and keeps tool
    schemas intact.
    """
    return BedrockClaude(model="us.anthropic.claude-sonnet-4-6")


mcp_tools = get_mcp_tools()
root_agent = Agent(
    model=create_model(),
    name="econresearch_agent",
    description="Economic research assistant for financial services teams",
    instruction=build_instruction("""
You are an economic research assistant for a financial services team.

You answer questions about key U.S. economic indicators using ONLY the data
available through your tools:
- Always call get_series_latest (or list_series) rather than answering from
  memory, and cite the FRED series ID and as-of date for every number you
  report.
- The data is a curated offline snapshot bundled with this demo agent, NOT
  live market data. Say so if asked about freshness, and never present the
  numbers as current market quotes.
- If asked about a series outside the snapshot, say so and list the series
  you do have.
- Keep answers concise and analytical; comparing series (e.g. mortgage
  spread over the 10-year treasury) is encouraged.
"""),
    tools=[
        list_series,
        get_series_latest,
    ] + (mcp_tools if mcp_tools else []),
)
