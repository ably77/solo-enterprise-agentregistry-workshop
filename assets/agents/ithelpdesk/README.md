# ithelpdesk Agent

An internal IT helpdesk assistant, built with Google ADK (Python) on AWS
Bedrock Claude (`us.anthropic.claude-sonnet-4-6`). Used by the
[AWS Bedrock AgentCore labs](../../../labs/runtimes/agentcore-01-integration.md): walked
through in [Part 2](../../../labs/runtimes/agentcore-02-create-agents.md) and deployed in
[Part 3](../../../labs/runtimes/agentcore-03-deploy-agents.md).

Two function tools answer questions from a curated offline snapshot of
sample IT helpdesk tickets and knowledge-base articles:

| Tool | Returns |
|---|---|
| `get_ticket_status(ticket_id)` | Status, category, priority, assignee, opened/last-update dates, summary |
| `search_kb_articles(query)` | Matching KB articles (title, category, summary) by keyword |

The snapshot lives in `ithelpdesk/agent.py` (`TICKETS`, `KB_ARTICLES`). The
agent cites ticket/article IDs and is explicit that the data is a demo
snapshot, not a live ITSM system.

Scaffolded with `arctl init agent ithelpdesk --framework adk --language
python --model-provider bedrock --model-name us.anthropic.claude-sonnet-4-6`;
`bedrock_model.py`, `mcp_tools.py`, and `prompts_loader.py` are unmodified
scaffold files. agentregistry clones this folder from GitHub and builds the
`Dockerfile` when you deploy the agent to the AgentCore runtime.
