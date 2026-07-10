# LLM and MCP Through Agentgateway

> **AWS Bedrock AgentCore series, Part 4 of 4**
> [Part 1: Integrate Agentregistry and AgentCore](agentcore-01-integration.md) ·
> [Part 2: Create Agents](agentcore-02-create-agents.md) ·
> [Part 3: Register and Deploy Agents to AgentCore](agentcore-03-deploy-agents.md) ·
> **Part 4: LLM and MCP Through Agentgateway** (this lab)

In Parts 1–3, `econresearch`'s model calls went straight from AgentCore to Bedrock (SDK + IAM),
and its "data" was an offline snapshot baked into `agent.py`. This lab extends it into
[`econresearch-agw`](../../assets/agents/econresearch-agw/), where **both of the agent's data
planes route through the workshop's in-cluster Agentgateway**:

- **LLM plane:** an OpenAI model (`gpt-5.4-nano`) consumed through a `/openai` gateway route.
  The OpenAI API key lives in a Kubernetes `Secret` next to the gateway; the agent never holds
  it — the gateway injects it upstream.
- **Tool plane:** the real **FRED** (Federal Reserve Economic Data) MCP server from the
  [FRED MCP lab](../mcp/fred-mcp.md), served at `/registry/fred`, attached to the agent via
  `spec.mcpServers`. The offline snapshot is gone; every number is fetched live.

One gateway fronts the model and the tools: one place to hold credentials, observe traffic,
and enforce policy.

```
[ AWS Bedrock AgentCore runtime: econresearch-agw ]
        │                        │
   LLM calls                MCP tool calls
        ▼                        ▼
   /openai  ──────────┐    /registry/fred ─────┐
        [ agentregistry-gateway (in-cluster Agentgateway LB) ]
        │ injects OPENAI_API_KEY          │ routes to mcp-fred pod
        ▼                                 ▼
   api.openai.com                 FRED MCP ──▶ api.stlouisfed.org
```

> **Cost note:** this lab makes OpenAI API calls (your `OPENAI_API_KEY`), FRED API calls
> (free key), and reuses Part 1's AgentCore integration (image build + runtime + CloudWatch,
> small but non-zero). Cleanup removes the AWS-side resources.

## Lab Objectives

- Deploy the credentialed FRED MCP server and expose it through Agentgateway (condensed from
  the [FRED MCP lab](../mcp/fred-mcp.md))
- Add an **LLM route** to the same gateway: `Secret` + `AgentgatewayBackend` + `HTTPRoute`,
  verified with a raw `curl` before any agent exists
- Read the `econresearch-agw` agent as a diff against `econresearch`: LiteLLM instead of the
  Bedrock adapter, gateway discovery from `MCP_SERVERS_CONFIG`, live tools instead of snapshot
- Publish and deploy the agent to AgentCore, linked to the FRED deployment via `deploymentRefs`
- Verify answers are grounded in live FRED observations, not a snapshot

## Pre-requisites

- [Part 1](agentcore-01-integration.md) complete and **not cleaned up**: `arctl get runtimes`
  shows `agentcore`.
- A **publicly reachable** Agentgateway LoadBalancer. The agent runs in AWS, so it must be able
  to reach your gateway over the internet. Managed clusters (EKS/GKE/AKS) with a public LB: yes.
  **kind/local clusters: the deploy in section 4 will not work** — you can still read along and
  run sections 1–2. (The production answer for private networking is the registry's managed
  EC2 gateway; see [Next](#next).)
- A **FRED API key** (free): https://fred.stlouisfed.org/docs/api/api_key.html
- An **OpenAI API key**: https://platform.openai.com/api-keys
- Shell context (re-run in every new shell):

```bash
export FRED_API_KEY=<your-fred-api-key>
export OPENAI_API_KEY=<your-openai-api-key>   # skip if already in your shell profile

export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"

export AWS_REGION=us-east-1   # must match the region you used in Part 1
```

> **Security callout:** this lab exposes an **unauthenticated** `/openai` route on a public
> LoadBalancer — anyone who finds the address can spend your OpenAI credits. This is a
> workshop-only posture: tear it down promptly (Cleanup), or harden it with gateway auth /
> virtual keys (see [Next](#next)).

## 1. FRED MCP Server Through the Gateway

Condensed from the [FRED MCP lab](../mcp/fred-mcp.md) — **skip to step 1.4 if you've already
done that lab** and `arctl get deployment fred-incluster-agw` shows `DeployedViaAgentgateway`.

### 1.1 Secret + workload

The FRED API key is the MCP server's own config: it lives in a `Secret` next to the workload,
never in the catalog.

```bash
kubectl create namespace mcp
kubectl create secret generic fred-api-key -n mcp \
  --from-literal=FRED_API_KEY="${FRED_API_KEY}"

kubectl apply -f assets/mcp/in-cluster/fred-deployment.yaml
kubectl rollout status deployment/mcp-fred -n mcp
```

### 1.2 Parent Gateway

Shared with the MCP labs — skip if already applied:

```bash
kubectl apply -f assets/mcp/agentgateway/parent-gateway-and-route.yaml
kubectl -n agentgateway-system get gateway agentregistry-gateway -w
# Wait for PROGRAMMED=True + ADDRESS, then Ctrl-C
```

### 1.3 Catalog + deploy via Agentgateway

```bash
arctl apply -f assets/mcp/in-cluster/fred-mcp.yaml
arctl apply -f assets/mcp/in-cluster/fred-mcp-deploy.yaml
sleep 5
arctl get deployment fred-incluster-agw -o yaml | grep -E "reason:|url:"
```

Expect `reason: DeployedViaAgentgateway` and `url: http://<gateway-address>/registry/fred`.

### 1.4 The reachability gate

Capture the gateway address and confirm it's public — this is the go/no-go for section 4:

```bash
export AGW_ADDRESS=$(kubectl -n agentgateway-system get gateway agentregistry-gateway \
  -o jsonpath='{.status.addresses[0].value}')
echo "gateway: ${AGW_ADDRESS}"
```

If `AGW_ADDRESS` is a private IP (`10.*`, `172.16-31.*`, `192.168.*`) or `localhost`, AgentCore
cannot reach it — sections 1–2 still work from your machine, but stop before section 4.

## 2. OpenAI Route on the Same Gateway

### 2.1 Create the credential Secret

Same pattern as FRED: the key lives in a `Secret` in the gateway's namespace, not in the
catalog, not in the agent.

```bash
kubectl create secret generic openai-secret -n agentgateway-system \
  --from-literal=Authorization="${OPENAI_API_KEY}"
```

### 2.2 Backend + route

[`openai-backend-and-route.yaml`](../../assets/mcp/agentgateway/openai-backend-and-route.yaml)
adds an `AgentgatewayBackend` (provider `openai`, auth from the Secret) and an `HTTPRoute` at
`/openai` on the same parent Gateway that serves `/registry/fred`:

```bash
cat assets/mcp/agentgateway/openai-backend-and-route.yaml
kubectl apply -f assets/mcp/agentgateway/openai-backend-and-route.yaml
```

The backend is **unpinned** (`openai: {}`), so the calling agent picks the model. Pinning
`openai.model` at the backend instead turns the gateway into the enforcement point for which
model an organization allows.

### 2.3 Prove it with curl — no agent, no API key on the client

```bash
curl -s -X POST "http://${AGW_ADDRESS}/openai" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.4-nano","messages":[{"role":"user","content":"Reply with exactly: gateway works"}]}' \
  | jq -r '.choices[0].message.content'
```

Expected:

```
gateway works
```

Note what just happened: the request carried **no** `Authorization` header. The gateway matched
`/openai`, injected the key from `openai-secret`, and proxied to OpenAI. That's the LLM plane
the agent will use. (404 instead? Try `http://${AGW_ADDRESS}/openai/chat/completions` — the
exact path handling depends on the agentgateway version — and use whichever form works as the
mental model for the agent's traffic; the agent's OpenAI client appends `/chat/completions`
to its base URL.)

## 3. The Agent, as a Diff

Open [`econresearch-agw/`](../../assets/agents/econresearch-agw/) next to
[`econresearch/`](../../assets/agents/econresearch/). Three changes:

**The model adapter is gone.** `econresearch` vendored `bedrock_model.py` because LiteLLM's
Bedrock translation drops tool descriptions. The OpenAI path has no such problem, so
`create_model()` is just ADK's built-in wrapper:

```python
return LiteLlm(
    model="openai/gpt-5.4-nano",
    api_base=openai_base_url(),
    api_key=os.environ.get("OPENAI_API_KEY", "gateway-injected"),
)
```

The `api_key` is a placeholder — the gateway injects the real one (section 2).

**Gateway discovery (`gateway.py`).** How does the agent know your gateway's address? It can't
be baked into the source (this folder is cloned from a shared GitHub URL at deploy time), and
AgentCore deployments accept no custom env vars from the registry. But the registry *does*
inject `MCP_SERVERS_CONFIG` — whose FRED URL points at the gateway. So the agent derives its
LLM base URL from the MCP config's origin: `http://<gw>/registry/fred` → `http://<gw>/openai`.
The registry already tells the agent where its gateway is — via the MCP config.
(`OPENAI_BASE_URL` overrides this for local runs.)

**Snapshot out, live tools in.** `ECON_SERIES`, `list_series`, and `get_series_latest` are
deleted. The agent's only tools are the FRED MCP server's — `fred_browse`, `fred_search`,
`fred_get_series` — resolved from `agent.yaml`:

```yaml
spec:
  mcpServers:
    - kind: MCPServer
      name: fred-incluster-mcp
```

The instruction changes to match: cite series IDs and **observation dates**, disclose the data
is live from FRED — the "demo snapshot" disclaimer is gone.

## 4. Publish and Deploy

> Go/no-go: section 1.4's `AGW_ADDRESS` must be publicly reachable.

Publish the catalog entry, then deploy to the `agentcore` runtime from Part 1. The new piece
is `deploymentRefs`: it links the agent deployment to the FRED MCP *deployment*, so the
registry resolves the gateway-served URL into the agent's `MCP_SERVERS_CONFIG`:

```bash
arctl apply -f assets/agents/econresearch-agw/agent.yaml

arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: Deployment
metadata:
  name: econresearch-agw
spec:
  targetRef:
    kind: Agent
    name: econresearch-agw
    tag: "1.0.0"
  runtimeRef:
    kind: Runtime
    name: agentcore
  deploymentRefs:
    - name: fred-incluster-agw
  runtimeConfig:
    region: ${AWS_REGION}
    workdir: assets/agents/econresearch-agw
EOF

arctl get deployments
```

The Deployment moves `deploying` → `deployed` (clone, image build, AgentCore rollout — a few
minutes, same phases as [Part 3](agentcore-03-deploy-agents.md)).

## 5. Verify: Live Data, Governed Planes

Open the **Instances** view (`http://${AR_IP}:12121/are/instances/`), select
`econresearch-agw`, and ask:

> What is the latest US CPI reading, and how does the current 30-year mortgage rate compare
> to the 10-year treasury?

Check the answer against Part 3's `econresearch`:

- It cites **recent observation dates** (this month/quarter — live FRED data), not the fixed
  snapshot dates, and no "demo snapshot" disclaimer appears.
- The tool calls are `fred_search` / `fred_get_series`, not `get_series_latest`.

Both planes are now observable in one place. CloudWatch still has the agent's own logs
(Part 3's flow):

```bash
aws logs describe-log-groups --region "${AWS_REGION}" \
  --log-group-name-prefix /aws/bedrock-agentcore/runtimes/
aws logs tail "/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT" \
  --region "${AWS_REGION}" --follow
```

and the gateway sees the LLM and MCP traffic:

```bash
kubectl -n agentgateway-system logs deploy/agentregistry-gateway --tail=50
# LLM calls to /openai and MCP calls to /registry/fred, from the same agent
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| curl in 2.3 returns 401/`invalid_api_key` | `openai-secret` wrong or missing: recreate it from `$OPENAI_API_KEY` (2.1) and re-check. The key must be under the `Authorization` key of the Secret. |
| curl in 2.3 returns 404 | Route/path mismatch: confirm the HTTPRoute is `Accepted` (`kubectl -n agentgateway-system describe httproute openai-llm`) and try the `/openai/chat/completions` form. |
| curl in 2.3 rejects the model name | Backend pinned to a different model: unpin (`openai: {}`) or match the pinned name. |
| Agent deploys but replies with connection errors to the LLM | The gateway isn't reachable *from AWS*: re-check section 1.4 — a private LB address works from your laptop but not from AgentCore. |
| Agent has no FRED tools (answers from memory or refuses) | MCP wiring: `spec.mcpServers` present in the published agent (`arctl get agent econresearch-agw -o yaml`), `deploymentRefs: [fred-incluster-agw]` present on the Deployment, and the FRED deployment is `DeployedViaAgentgateway`. |
| Agent crashes at startup with `cannot determine the agentgateway LLM base URL` | `MCP_SERVERS_CONFIG` wasn't injected — same MCP-wiring checks as above; the LLM base URL is derived from it. |
| FRED `tools/list` works but `tools/call` fails | FRED credential problem, not connectivity: check the `fred-api-key` Secret (see the [FRED MCP lab](../mcp/fred-mcp.md)). |

## Cleanup

```bash
# Agent
arctl delete deployment econresearch-agw
arctl delete agent econresearch-agw --tag 1.0.0

# OpenAI route (stop exposing your key's spend!)
kubectl delete -f assets/mcp/agentgateway/openai-backend-and-route.yaml
kubectl delete secret openai-secret -n agentgateway-system

# FRED (skip if you set it up in the FRED MCP lab and want to keep it)
arctl delete deployment fred-incluster-agw
arctl delete mcp fred-incluster-mcp --tag latest
kubectl delete -f assets/mcp/in-cluster/fred-deployment.yaml
kubectl delete secret fred-api-key -n mcp
kubectl delete namespace mcp --ignore-not-found
```

> AgentCore leaves the runtime's CloudWatch log group behind; remove it with
> `aws logs delete-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT" --region "${AWS_REGION}"`.
> The parent Gateway is shared with the MCP labs — remove it only if you're done with those
> (see the [FRED MCP lab](../mcp/fred-mcp.md) cleanup). To tear down the AgentCore integration
> itself, run [Part 1's Cleanup](agentcore-01-integration.md#cleanup).

## Next

- **Private networking, production-style:** instead of a public LB, the registry can deploy a
  **managed Agentgateway on EC2 inside your VPC** and run the agent with
  `runtimeConfig.networkMode: vpc` — LLM and MCP traffic never leave the private network. See
  the [agentregistry AgentCore quickstart](https://docs.solo.io/agentregistry/latest/quickstart/agentcore/).
- **Harden the LLM route:** gateway-level auth and per-team **virtual keys** with budgets:
  [agentgateway LLM consumption docs](https://docs.solo.io/agentgateway/latest/llm/).
- Govern who can see and use these assets: [AccessPolicy / RBAC](../access-control/access-policies.md)
