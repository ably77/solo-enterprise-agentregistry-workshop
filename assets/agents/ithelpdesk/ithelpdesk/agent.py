import os

from google.adk import Agent

from .bedrock_model import BedrockClaude
from .mcp_tools import get_mcp_tools
from .prompts_loader import build_instruction

os.environ.setdefault('OTEL_SERVICE_NAME', 'ithelpdesk')

from google.adk.telemetry.setup import maybe_set_otel_providers
maybe_set_otel_providers()


# Curated offline snapshot of sample IT helpdesk tickets and knowledge-base
# articles. A follow-up lab can swap this for a live ITSM API called
# through an MCP server (see mcp_tools.py).
TICKETS = {
    "INC-40125": {
        "status": "Open",
        "category": "hardware",
        "priority": "P2",
        "assignee": "D. Park",
        "opened_date": "2026-06-26",
        "last_update": "2026-06-27",
        "summary": "Laptop won't power on after firmware update",
    },
    "INC-40126": {
        "status": "In Progress",
        "category": "access",
        "priority": "P3",
        "assignee": "S. Alvarez",
        "opened_date": "2026-06-24",
        "last_update": "2026-06-28",
        "summary": "Needs VPN access restored after role change",
    },
    "INC-40127": {
        "status": "Resolved",
        "category": "software",
        "priority": "P3",
        "assignee": "D. Park",
        "opened_date": "2026-06-15",
        "last_update": "2026-06-18",
        "summary": "Outlook repeatedly crashing on send",
    },
    "INC-40128": {
        "status": "Closed",
        "category": "network",
        "priority": "P1",
        "assignee": "S. Alvarez",
        "opened_date": "2026-06-01",
        "last_update": "2026-06-03",
        "summary": "Office Wi-Fi outage, floor 4",
    },
    "INC-40129": {
        "status": "Open",
        "category": "software",
        "priority": "P4",
        "assignee": "Unassigned",
        "opened_date": "2026-06-28",
        "last_update": "2026-06-28",
        "summary": "Request to install approved design software",
    },
}

KB_ARTICLES = {
    "KB-2001": {
        "title": "Resetting your VPN access after a role change",
        "category": "access",
        "summary": "Steps to request VPN re-provisioning through the access portal after a team or role change.",
    },
    "KB-2002": {
        "title": "Laptop won't power on: troubleshooting steps",
        "category": "hardware",
        "summary": "Battery, charger, and forced-firmware-recovery steps for laptops that won't power on after an update.",
    },
    "KB-2003": {
        "title": "Fixing Outlook crashes on send",
        "category": "software",
        "summary": "Clearing the Outlook cache and disabling a known-bad add-in that causes crashes when sending mail.",
    },
    "KB-2004": {
        "title": "Requesting new software installs",
        "category": "software",
        "summary": "How to submit and track a request for approved software through the self-service catalog.",
    },
}


def get_ticket_status(ticket_id: str) -> dict:
    """Get the status and detail of one IT helpdesk ticket.

    Args:
        ticket_id: Ticket ID, e.g. INC-40125. Case-insensitive.

    Returns the ticket's status, category, priority, assignee, opened/last-
    update dates, and summary, or an error with the list of valid ticket
    IDs if the ID is unknown.
    """
    tid = ticket_id.strip().upper()
    if tid not in TICKETS:
        return {
            "error": f"unknown ticket_id '{ticket_id}'",
            "available_ticket_ids": sorted(TICKETS),
        }
    return {"ticket_id": tid, **TICKETS[tid]}


def search_kb_articles(query: str) -> dict:
    """Search knowledge-base articles by keyword.

    Args:
        query: Free-text keyword to match against article title, category,
            and summary (case-insensitive substring match).

    Returns the matching articles (id, title, category, summary), or an
    empty match list with the full list of available article IDs if
    nothing matches.
    """
    q = query.strip().lower()
    matches = [
        {"article_id": aid, **article}
        for aid, article in KB_ARTICLES.items()
        if q in article["title"].lower()
        or q in article["category"].lower()
        or q in article["summary"].lower()
    ]
    if not matches:
        return {
            "query": query,
            "matches": [],
            "available_article_ids": sorted(KB_ARTICLES),
        }
    return {"query": query, "matches": matches}


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
    name="ithelpdesk_agent",
    description="Internal IT helpdesk assistant for ticket status and knowledge-base lookups",
    instruction=build_instruction("""
You are an internal IT helpdesk assistant.

You answer questions about ticket status and knowledge-base articles using
ONLY the data available through your tools:
- Always call get_ticket_status or search_kb_articles rather than
  answering from memory, and cite the ticket ID or article ID for every
  detail you report.
- The data is a curated offline snapshot bundled with this demo agent, NOT
  a live ITSM system. Say so if asked about freshness, and never invent a
  ticket, status, assignee, or article that isn't returned by a tool call.
- If asked about a ticket outside the snapshot, say so and list the ticket
  IDs you do have. If a KB search returns no matches, say so and suggest
  the employee open a ticket.
- Keep answers concise and actionable: state the status/owner for tickets,
  or the relevant steps summary for KB articles.
"""),
    tools=[
        get_ticket_status,
        search_kb_articles,
    ] + (mcp_tools if mcp_tools else []),
)
