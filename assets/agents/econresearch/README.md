# econresearch Agent

An economic research assistant for financial services teams, built with Google
ADK (Python) on AWS Bedrock Claude (`us.anthropic.claude-sonnet-4-6`). Used by
the [AWS Bedrock AgentCore labs](../../../labs/runtimes/agentcore-01-integration.md) — walked
through in [Part 2](../../../labs/runtimes/agentcore-02-create-agents.md) and deployed in
[Part 3](../../../labs/runtimes/agentcore-03-deploy-agents.md).

Two function tools answer questions from a curated offline snapshot of key
U.S. economic indicators (FRED series IDs):

| Series | Indicator |
|---|---|
| `FEDFUNDS` | Effective Federal Funds Rate |
| `CPIAUCSL` | Consumer Price Index (All Urban Consumers) |
| `UNRATE` | Unemployment Rate |
| `DGS10` | 10-Year Treasury Constant Maturity Rate |
| `MORTGAGE30US` | 30-Year Fixed Rate Mortgage Average |

The snapshot lives in `econresearch/agent.py` (`ECON_SERIES`). The agent cites
series IDs and as-of dates and is explicit that the data is a demo snapshot,
not live market data. A follow-up lab can swap the snapshot for live data via
the workshop's FRED MCP server through Agentgateway.

Scaffolded with `arctl init agent econresearch --framework adk --language
python --model-provider bedrock --model-name us.anthropic.claude-sonnet-4-6`;
`bedrock_model.py`, `mcp_tools.py`, and `prompts_loader.py` are unmodified
scaffold files. agentregistry clones this folder from GitHub and builds the
`Dockerfile` when you deploy the agent to the AgentCore runtime.
