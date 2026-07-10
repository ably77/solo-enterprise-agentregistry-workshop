# econresearch-agw Agent

The [`econresearch`](../econresearch/) agent, extended so that **both** of its
data planes route through the workshop's in-cluster Agentgateway. Used by
[Part 4 of the AWS Bedrock AgentCore labs](../../../labs/runtimes/agentcore-04-agentgateway-llm-mcp.md).

| Plane | econresearch | econresearch-agw |
|---|---|---|
| Model | Bedrock Claude, direct via `anthropic.AnthropicBedrock` | OpenAI `gpt-5.4-nano` via the gateway's `/openai` route (`LiteLlm`; key held in a k8s Secret at the gateway, never by the agent) |
| Tools | Offline snapshot dicts baked into `agent.py` | Live FRED MCP server via the gateway's `/registry/fred` route (`spec.mcpServers`) |

There is no `bedrock_model.py` here: the OpenAI-protocol path works with ADK's
built-in `LiteLlm` wrapper (the custom Bedrock adapter existed only because
LiteLLM's bedrock translation drops tool descriptions).

`gateway.py` derives the gateway's address at startup from the registry-injected
`MCP_SERVERS_CONFIG` (AgentCore deployments have no env-var passthrough, and
this folder is cloned from a shared Git URL, so the address can't be baked in).
`OPENAI_BASE_URL` overrides it for local runs.

`mcp_tools.py` and `prompts_loader.py` are unmodified scaffold files.
agentregistry clones this folder from GitHub and builds the `Dockerfile` when
you deploy the agent to the AgentCore runtime.
