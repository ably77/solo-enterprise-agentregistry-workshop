# claimsupport Agent

An insurance claim support assistant, built with Google ADK (Python) on AWS
Bedrock Claude (`us.anthropic.claude-sonnet-4-6`). Used by the
[AWS Bedrock AgentCore labs](../../../labs/runtimes/agentcore-01-integration.md) — walked
through in [Part 2](../../../labs/runtimes/agentcore-02-create-agents.md) and deployed in
[Part 3](../../../labs/runtimes/agentcore-03-deploy-agents.md).

Two function tools answer questions from a curated offline snapshot of
sample insurance claims and policies:

| Tool | Returns |
|---|---|
| `get_claim_status(claim_id)` | Status, type, filed/last-update dates, adjuster, claimed/approved amounts |
| `get_policy_coverage(policy_id)` | Type, coverage limit, deductible, monthly premium, status |

The snapshot lives in `claimsupport/agent.py` (`CLAIMS`, `POLICIES`). The
agent cites claim/policy IDs and is explicit that the data is a demo
snapshot, not a live claims-management system.

Scaffolded with `arctl init agent claimsupport --framework adk --language
python --model-provider bedrock --model-name us.anthropic.claude-sonnet-4-6`;
`bedrock_model.py`, `mcp_tools.py`, and `prompts_loader.py` are unmodified
scaffold files. agentregistry clones this folder from GitHub and builds the
`Dockerfile` when you deploy the agent to the AgentCore runtime.
