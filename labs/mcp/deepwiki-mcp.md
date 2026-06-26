# DeepWiki MCP through Agentgateway

A second public, remote MCP example alongside [Solo Docs](solo-docs-mcp.md) — **DeepWiki**
(`https://mcp.deepwiki.com/mcp`), which answers questions about public GitHub repositories. Same
gateway-fronted pattern, no token required. This lab is intentionally short; see the
[Solo Docs lab](solo-docs-mcp.md) for the full explanation of each step.

## Lab Objectives

- Catalog a second remote MCP server (DeepWiki) with no token
- Expose it at its own path (`/registry/deepwiki`) on the **same** parent Gateway
- Call its `ask_question` tool through the gateway

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- Optional: to run this lab's calls from a browser instead of `curl`, use the
  [MCP Client UI](mcp-client-ui.md) and pick the **DeepWiki (remote)** endpoint.
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

## 1. Parent Gateway (shared)

One parent Gateway fronts many MCPs at different path suffixes. Apply it if you haven't (e.g. you
ran the Solo Docs lab and left it up — then skip this):

```bash
cat assets/mcp/agentgateway/parent-gateway-and-route.yaml
kubectl apply -f assets/mcp/agentgateway/parent-gateway-and-route.yaml
kubectl -n agentgateway-system get gateway mcp-gateway -w
# Wait for PROGRAMMED=True + ADDRESS, then Ctrl-C
```

## 2. Catalog + Deploy DeepWiki

```bash
cat assets/mcp/agentgateway/deepwiki-remote-mcp.yaml assets/mcp/agentgateway/deepwiki-remote-mcp-deploy.yaml
arctl apply -f assets/mcp/agentgateway/deepwiki-remote-mcp.yaml
arctl apply -f assets/mcp/agentgateway/deepwiki-remote-mcp-deploy.yaml
sleep 5
arctl get deployment deepwiki-remote-mcp-agw -o yaml | grep -E "reason:|url:"
```

Expect `reason: DeployedViaAgentgateway` and `url: http://<gateway-address>/registry/deepwiki`.
(If it's stuck at `NoAcceptedListener`, the Gateway wasn't programmed yet — `arctl delete` the
deployment and re-apply.)

## 3. Call It

```bash
export AGW_ADDRESS=$(kubectl -n agentgateway-system get gateway mcp-gateway \
  -o jsonpath='{.status.addresses[0].value}')

export SID=$(curl -s -D - -o /dev/null -X POST \
  -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.1"}}}' \
  "http://${AGW_ADDRESS}/registry/deepwiki" | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')

H=(-H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
   -H "mcp-session-id: ${SID}" -H "MCP-Protocol-Version: 2025-06-18")
curl -s -o /dev/null -X POST "${H[@]}" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' "http://${AGW_ADDRESS}/registry/deepwiki"

# list tools
curl -s -X POST "${H[@]}" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  "http://${AGW_ADDRESS}/registry/deepwiki" | sed 's/^data: //' | jq -r '.result.tools[].name'
```

Expected (public tools):

```
read_wiki_structure
read_wiki_contents
ask_question
```

Ask a question about a repo. The repo must already be indexed on deepwiki.com (most popular public
repos are; `solo-io/gloo` works):

```bash
curl -s -X POST "${H[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ask_question","arguments":{"repoName":"solo-io/gloo","question":"What is this project?"}}}' \
  "http://${AGW_ADDRESS}/registry/deepwiki" | sed 's/^data: //' | jq -r '.result.content[0].text' | head -20
```

You get an AI-generated answer sourced from the repo's docs, served through the gateway. (If you ask
about a repo DeepWiki hasn't indexed, the tool returns `Repository not found. Visit
https://deepwiki.com to index it.` — that's a valid response from the upstream, proving the gateway
path works.)

> **Two MCPs, one gateway.** If you also ran the Solo Docs lab, both are now live on the same
> Gateway LB at different paths — `/registry/solo-docs` and `/registry/deepwiki`. That's the
> Virtual-runtime pattern: one endpoint, many catalog-published MCP backends.

## Cleanup

```bash
arctl delete deployment deepwiki-remote-mcp-agw
arctl delete mcp deepwiki-remote-mcp --tag latest
# Only if you're done with the parent Gateway (other MCP labs share it):
kubectl -n agentgateway-system delete httproute remote-mcp-delegate --ignore-not-found
kubectl -n agentgateway-system delete gateway   mcp-gateway   --ignore-not-found
```

## Next

- [MCP Client UI](mcp-client-ui.md) - call this endpoint from a browser instead of curl
- [In-Cluster MCP Server](in-cluster-mcp.md) - host your own MCP server and register it
- [AccessPolicy / RBAC](../access-control/access-policies.md)
