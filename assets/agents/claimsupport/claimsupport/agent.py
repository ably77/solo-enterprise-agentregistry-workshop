import os

from google.adk import Agent

from .bedrock_model import BedrockClaude
from .mcp_tools import get_mcp_tools
from .prompts_loader import build_instruction

# Set service name from environment variable for OpenTelemetry
os.environ.setdefault('OTEL_SERVICE_NAME', 'claimsupport')

from google.adk.telemetry.setup import maybe_set_otel_providers
maybe_set_otel_providers()


# Curated offline snapshot of sample insurance claims and policies. A
# follow-up lab can swap this for a live claims-management API called
# through an MCP server (see mcp_tools.py).
CLAIMS = {
    "CLM-10234": {
        "policy_id": "POL-55821",
        "type": "auto",
        "status": "Under Review",
        "filed_date": "2026-06-02",
        "last_update": "2026-06-15",
        "adjuster": "J. Rivera",
        "amount_claimed": 4200.00,
        "amount_approved": None,
    },
    "CLM-10235": {
        "policy_id": "POL-55822",
        "type": "home",
        "status": "Approved",
        "filed_date": "2026-05-20",
        "last_update": "2026-06-10",
        "adjuster": "M. Chen",
        "amount_claimed": 9800.00,
        "amount_approved": 9100.00,
    },
    "CLM-10236": {
        "policy_id": "POL-55821",
        "type": "auto",
        "status": "Denied",
        "filed_date": "2026-04-11",
        "last_update": "2026-04-28",
        "adjuster": "J. Rivera",
        "amount_claimed": 1500.00,
        "amount_approved": 0.00,
    },
    "CLM-10237": {
        "policy_id": "POL-55823",
        "type": "health",
        "status": "Paid",
        "filed_date": "2026-03-02",
        "last_update": "2026-03-19",
        "adjuster": "A. Osei",
        "amount_claimed": 620.00,
        "amount_approved": 620.00,
    },
    "CLM-10238": {
        "policy_id": "POL-55824",
        "type": "home",
        "status": "Under Review",
        "filed_date": "2026-06-25",
        "last_update": "2026-06-27",
        "adjuster": "M. Chen",
        "amount_claimed": 15300.00,
        "amount_approved": None,
    },
}

POLICIES = {
    "POL-55821": {
        "type": "auto",
        "coverage_limit": 50000.00,
        "deductible": 500.00,
        "premium_monthly": 128.50,
        "status": "active",
    },
    "POL-55822": {
        "type": "home",
        "coverage_limit": 350000.00,
        "deductible": 1000.00,
        "premium_monthly": 89.00,
        "status": "active",
    },
    "POL-55823": {
        "type": "health",
        "coverage_limit": 1000000.00,
        "deductible": 250.00,
        "premium_monthly": 410.75,
        "status": "active",
    },
    "POL-55824": {
        "type": "home",
        "coverage_limit": 500000.00,
        "deductible": 1500.00,
        "premium_monthly": 102.25,
        "status": "active",
    },
}


def get_claim_status(claim_id: str) -> dict:
    """Get the status and detail of one insurance claim.

    Args:
        claim_id: Claim ID, e.g. CLM-10234. Case-insensitive.

    Returns the claim's policy ID, type, status, filed/last-update dates,
    assigned adjuster, and claimed/approved amounts, or an error with the
    list of valid claim IDs if the ID is unknown.
    """
    cid = claim_id.strip().upper()
    if cid not in CLAIMS:
        return {
            "error": f"unknown claim_id '{claim_id}'",
            "available_claim_ids": sorted(CLAIMS),
        }
    return {"claim_id": cid, **CLAIMS[cid]}


def get_policy_coverage(policy_id: str) -> dict:
    """Get the coverage detail of one insurance policy.

    Args:
        policy_id: Policy ID, e.g. POL-55821. Case-insensitive.

    Returns the policy's type, coverage limit, deductible, monthly premium,
    and status, or an error with the list of valid policy IDs if the ID is
    unknown.
    """
    pid = policy_id.strip().upper()
    if pid not in POLICIES:
        return {
            "error": f"unknown policy_id '{policy_id}'",
            "available_policy_ids": sorted(POLICIES),
        }
    return {"policy_id": pid, **POLICIES[pid]}


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
    name="claimsupport_agent",
    description="Insurance claim support assistant for policyholders and claims staff",
    instruction=build_instruction("""
You are an insurance claim support assistant.

You answer questions about claim status and policy coverage using ONLY the
data available through your tools:
- Always call get_claim_status or get_policy_coverage rather than answering
  from memory, and cite the claim ID or policy ID for every detail you
  report.
- The data is a curated offline snapshot bundled with this demo agent, NOT
  a live claims-management system. Say so if asked about freshness, and
  never invent a claim, policy, status, or dollar amount that isn't
  returned by a tool call.
- If asked about a claim or policy outside the snapshot, say so and list
  the IDs you do have.
- Keep answers concise and specific: state the status, key dates, and
  amounts a policyholder or claims rep would need.
"""),
    tools=[
        get_claim_status,
        get_policy_coverage,
    ] + (mcp_tools if mcp_tools else []),
)
