import os

from google.adk import Agent

from .bedrock_model import BedrockClaude
from .mcp_tools import get_mcp_tools
from .prompts_loader import build_instruction

os.environ.setdefault('OTEL_SERVICE_NAME', 'bankingsupport')

from google.adk.telemetry.setup import maybe_set_otel_providers
maybe_set_otel_providers()


# Curated offline snapshot of sample personal banking accounts and recent
# transactions. A follow-up lab can swap this for a live core-banking API
# called through an MCP server (see mcp_tools.py).
ACCOUNTS = {
    "ACC-100234": {
        "type": "checking",
        "balance": 2456.78,
        "currency": "USD",
        "opened_date": "2021-03-14",
        "status": "active",
    },
    "ACC-100235": {
        "type": "savings",
        "balance": 18320.10,
        "currency": "USD",
        "opened_date": "2019-11-02",
        "status": "active",
    },
    "ACC-100236": {
        "type": "checking",
        "balance": 312.45,
        "currency": "USD",
        "opened_date": "2024-07-30",
        "status": "active",
    },
    "ACC-100237": {
        "type": "savings",
        "balance": 500.00,
        "currency": "USD",
        "opened_date": "2023-01-09",
        "status": "frozen",
    },
}

TRANSACTIONS = {
    "ACC-100234": [
        {"date": "2026-06-28", "description": "Grocery Mart", "amount": -84.12, "type": "debit", "balance_after": 2456.78},
        {"date": "2026-06-25", "description": "Payroll Deposit", "amount": 1850.00, "type": "credit", "balance_after": 2540.90},
        {"date": "2026-06-20", "description": "Electric Co.", "amount": -112.30, "type": "debit", "balance_after": 690.90},
    ],
    "ACC-100235": [
        {"date": "2026-06-15", "description": "Interest Payment", "amount": 22.40, "type": "credit", "balance_after": 18320.10},
        {"date": "2026-05-15", "description": "Interest Payment", "amount": 21.95, "type": "credit", "balance_after": 18297.70},
    ],
    "ACC-100236": [
        {"date": "2026-06-27", "description": "Coffee Shop", "amount": -5.75, "type": "debit", "balance_after": 312.45},
        {"date": "2026-06-26", "description": "Transfer from ACC-100234", "amount": 100.00, "type": "credit", "balance_after": 318.20},
    ],
    "ACC-100237": [
        {"date": "2026-04-02", "description": "Account Frozen - Compliance Hold", "amount": 0.00, "type": "hold", "balance_after": 500.00},
    ],
}


def get_account_summary(account_id: str) -> dict:
    """Get the summary detail of one banking account.

    Args:
        account_id: Account ID, e.g. ACC-100234. Case-insensitive.

    Returns the account's type, balance, currency, opened date, and status,
    or an error with the list of valid account IDs if the ID is unknown.
    """
    aid = account_id.strip().upper()
    if aid not in ACCOUNTS:
        return {
            "error": f"unknown account_id '{account_id}'",
            "available_account_ids": sorted(ACCOUNTS),
        }
    return {"account_id": aid, **ACCOUNTS[aid]}


def list_recent_transactions(account_id: str) -> dict:
    """List recent transactions for one banking account.

    Args:
        account_id: Account ID, e.g. ACC-100234. Case-insensitive.

    Returns the account ID and its recent transactions (date, description,
    amount, type, balance_after), or an error with the list of valid
    account IDs if the ID is unknown.
    """
    aid = account_id.strip().upper()
    if aid not in TRANSACTIONS:
        return {
            "error": f"unknown account_id '{account_id}'",
            "available_account_ids": sorted(TRANSACTIONS),
        }
    return {"account_id": aid, "transactions": TRANSACTIONS[aid]}


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
    name="bankingsupport_agent",
    description="Personal banking support assistant for account and transaction questions",
    instruction=build_instruction("""
You are a personal banking support assistant.

You answer questions about account balances and recent transactions using
ONLY the data available through your tools:
- Always call get_account_summary or list_recent_transactions rather than
  answering from memory, and cite the account ID for every balance or
  transaction you report.
- The data is a curated offline snapshot bundled with this demo agent, NOT
  a live core-banking system. Say so if asked about freshness, and never
  invent a balance, transaction, or account that isn't returned by a tool
  call.
- If asked about an account outside the snapshot, say so and list the
  account IDs you do have.
- Keep answers concise: state the balance, status, or transaction detail a
  customer or support rep would need.
"""),
    tools=[
        get_account_summary,
        list_recent_transactions,
    ] + (mcp_tools if mcp_tools else []),
)
