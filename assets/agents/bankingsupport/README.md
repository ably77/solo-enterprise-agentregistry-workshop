# bankingsupport Agent

A personal banking support assistant, built with Google ADK (Python) on AWS
Bedrock Claude (`us.anthropic.claude-sonnet-4-6`). Used by the
[AWS Bedrock AgentCore labs](../../../labs/runtimes/agentcore-01-integration.md) — walked
through in [Part 2](../../../labs/runtimes/agentcore-02-create-agents.md) and deployed in
[Part 3](../../../labs/runtimes/agentcore-03-deploy-agents.md).

Two function tools answer questions from a curated offline snapshot of
sample personal banking accounts and recent transactions:

| Tool | Returns |
|---|---|
| `get_account_summary(account_id)` | Type, balance, currency, opened date, status |
| `list_recent_transactions(account_id)` | Recent transactions (date, description, amount, type, balance_after) |

The snapshot lives in `bankingsupport/agent.py` (`ACCOUNTS`, `TRANSACTIONS`).
The agent cites account IDs and is explicit that the data is a demo
snapshot, not a live core-banking system.

Scaffolded with `arctl init agent bankingsupport --framework adk --language
python --model-provider bedrock --model-name us.anthropic.claude-sonnet-4-6`;
`bedrock_model.py`, `mcp_tools.py`, and `prompts_loader.py` are unmodified
scaffold files. agentregistry clones this folder from GitHub and builds the
`Dockerfile` when you deploy the agent to the AgentCore runtime.
