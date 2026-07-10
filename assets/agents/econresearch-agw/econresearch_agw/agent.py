import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from .gateway import openai_base_url
from .mcp_tools import get_mcp_tools
from .prompts_loader import build_instruction

# Set service name from environment variable for OpenTelemetry
os.environ.setdefault('OTEL_SERVICE_NAME', 'econresearch-agw')

from google.adk.telemetry.setup import maybe_set_otel_providers
maybe_set_otel_providers()


def create_model():
    """Use an OpenAI model consumed through Agentgateway.

    Unlike econresearch's Bedrock path (which needs a custom adapter because
    LiteLLM's bedrock translation drops tool descriptions), the OpenAI path
    works with ADK's built-in LiteLlm wrapper as-is. The api_key is a
    placeholder: the gateway's AgentgatewayBackend injects the real
    OPENAI_API_KEY from a Kubernetes Secret, so the key never ships with
    the agent. The base URL is derived at startup (see gateway.py).
    """
    return LiteLlm(
        model="openai/gpt-5.4-nano",
        api_base=openai_base_url(),
        api_key=os.environ.get("OPENAI_API_KEY", "gateway-injected"),
    )


# The agent's only tools are the FRED MCP server's (fred_browse, fred_search,
# fred_get_series), resolved from the registry via spec.mcpServers and served
# through Agentgateway. No offline snapshot: the data is live.
mcp_tools = get_mcp_tools()
root_agent = Agent(
    model=create_model(),
    name="econresearch_agw_agent",
    description="Economic research assistant with live FRED data via Agentgateway",
    instruction=build_instruction("""
You are an economic research assistant for a financial services team.

You answer questions about U.S. economic data using ONLY live FRED (Federal
Reserve Economic Data) series fetched through your tools:
- Discover series with fred_search (or fred_browse), then fetch numbers with
  fred_get_series. Never answer from memory.
- Cite the FRED series ID and the observation date for every number you
  report. The data is fetched live from the FRED API through the workshop's
  MCP server; say so if asked about freshness.
- If FRED has no series matching a question, say so rather than guessing.
- Keep answers concise and analytical; comparing series (e.g. mortgage
  spread over the 10-year treasury) is encouraged.
"""),
    tools=mcp_tools if mcp_tools else [],
)
