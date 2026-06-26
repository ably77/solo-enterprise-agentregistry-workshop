# In-Cluster MCP Server with a Credential (FRED)

The [In-Cluster MCP](in-cluster-mcp.md) lab self-hosted a server that needed no credentials. Most
real MCP servers do — they call some backend API on your behalf. This lab covers that case with the
**FRED** (Federal Reserve Economic Data) MCP server, which needs its own `FRED_API_KEY` to reach the
St. Louis Fed API.

The important idea: **that credential is the MCP server's own config, not the registry's.** You keep
it in a Kubernetes `Secret` next to the workload; agentregistry only registers the in-cluster Service
URL and never sees the key. This is the recommended pattern for any MCP server with a backend
credential.

> **Which kind of credential is this?** FRED's key is a **server-internal** credential (the server
> uses it to call its upstream API). That's different from a credential a *caller* must present to
> the MCP endpoint (an `Authorization` header), which would live in `spec.remote.headers` and be
> stored on the catalog object itself. Keeping server-internal creds in a workload `Secret` keeps
> them out of the catalog entirely.

## Lab Objectives

- Store an MCP server's API key in a Kubernetes `Secret`
- Deploy the MCP server in-cluster, consuming the key via `secretKeyRef`
- Register it in the catalog by Service URL — with **no credential in the catalog object**
- Call a tool that exercises the credentialed upstream

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- Optional: to run this lab's calls from a browser instead of `curl`, use the
  [MCP Client UI](mcp-client-ui.md) and pick the **FRED (in-cluster, credentialed)** endpoint.
- A **FRED API key** (free): https://fred.stlouisfed.org/docs/api/api_key.html

```bash
export FRED_API_KEY=<your-fred-api-key>

export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

> **Third-party image notice:** `ably7/fred-mcp-server` is a community image, used here for
> convenience. Build/pin and scan your own image for anything beyond a workshop.

## 1. Create the Credential Secret

```bash
kubectl create namespace mcp
kubectl create secret generic fred-api-key -n mcp \
  --from-literal=FRED_API_KEY="${FRED_API_KEY}"
```

## 2. Deploy the MCP Server (consuming the Secret)

[`assets/mcp/in-cluster/fred-deployment.yaml`](../../assets/mcp/in-cluster/fred-deployment.yaml)
injects the key via `secretKeyRef` — the key never appears in the manifest:

```yaml
env:
  - name: FRED_API_KEY
    valueFrom:
      secretKeyRef: { name: fred-api-key, key: FRED_API_KEY }
```

```bash
cat assets/mcp/in-cluster/fred-deployment.yaml
kubectl apply -f assets/mcp/in-cluster/fred-deployment.yaml
kubectl rollout status deployment/mcp-fred -n mcp
```

## 3. Parent Gateway and Route

Same shared parent Gateway. Skip if you already applied it in another MCP lab.

```bash
cat assets/mcp/agentgateway/parent-gateway-and-route.yaml
kubectl apply -f assets/mcp/agentgateway/parent-gateway-and-route.yaml
kubectl -n agentgateway-system get gateway mcp-gateway -w
# Wait for PROGRAMMED=True + ADDRESS, then Ctrl-C
```

## 4. Catalog and Deploy

Note the catalog entry ([`fred-mcp.yaml`](../../assets/mcp/in-cluster/fred-mcp.yaml)) has **no
credential** — just the Service URL:

```bash
cat assets/mcp/in-cluster/fred-mcp.yaml assets/mcp/in-cluster/fred-mcp-deploy.yaml
arctl apply -f assets/mcp/in-cluster/fred-mcp.yaml
arctl apply -f assets/mcp/in-cluster/fred-mcp-deploy.yaml
sleep 5
arctl get deployment fred-incluster-agw -o yaml | grep -E "reason:|url:"
```

Expect `reason: DeployedViaAgentgateway` and `url: http://<gateway-address>/registry/fred`.
(If it's stuck at `NoAcceptedListener`, the Gateway wasn't programmed yet — `arctl delete` the
deployment and re-apply.)

Confirm the key really is absent from the catalog object (only the URL is stored). We grep for the
markers that *would* indicate a stored credential — a caller `headers:` block, a `secretRef`, or the
`FRED_API_KEY` name itself — rather than bare words like `key`/`secret`, which also appear in the
asset's own description:

```bash
arctl get mcp fred-incluster-mcp --tag latest -o yaml | grep -iE "headers:|secretRef|FRED_API_KEY" || echo "no credential in the catalog entry ✓"
```

Expected:

```
no credential in the catalog entry ✓
```

## 5. Call a Credentialed Tool

```bash
export AGW_ADDRESS=$(kubectl -n agentgateway-system get gateway mcp-gateway \
  -o jsonpath='{.status.addresses[0].value}')

export SID=$(curl -s -D - -o /dev/null -X POST \
  -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.1"}}}' \
  "http://${AGW_ADDRESS}/registry/fred" | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')

H=(-H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
   -H "mcp-session-id: ${SID}" -H "MCP-Protocol-Version: 2025-06-18")
curl -s -o /dev/null -X POST "${H[@]}" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' "http://${AGW_ADDRESS}/registry/fred"

# tools
curl -s -X POST "${H[@]}" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  "http://${AGW_ADDRESS}/registry/fred" | sed 's/^data: //' | jq -r '.result.tools[].name'
```

Expected:

```
fred_browse
fred_search
fred_get_series
```

Fetch a real economic series — this only works because the server has a valid `FRED_API_KEY`:

```bash
curl -s -X POST "${H[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fred_get_series","arguments":{"series_id":"GDP","observation_start":"2024-01-01","observation_end":"2024-12-31"}}}' \
  "http://${AGW_ADDRESS}/registry/fred" | sed 's/^data: //' | jq -r '.result.content[0].text' | head -12
```

You get real GDP data (`"title": "Gross Domestic Product"`, quarterly observations). If the key were
missing or wrong, this `tools/call` would fail at the upstream while `tools/list` still worked — a
useful way to tell a credential problem apart from a connectivity problem.

## Where the Credential Lives

```
client → gateway LB /registry/fred
           → child route + backend            (agentregistry-generated; NO credential)
              → http://mcp-fred.mcp.svc.cluster.local/mcp
                 → FRED MCP pod  ── reads FRED_API_KEY from the `fred-api-key` Secret ──▶ api.stlouisfed.org
```

The catalog entry, the generated backend, and the gateway are all credential-free. The only place
the key exists is the Kubernetes `Secret` mounted into the pod — manage and rotate it with your usual
secret tooling (External Secrets Operator, Vault CSI, sealed-secrets).

## Cleanup

```bash
arctl delete deployment fred-incluster-agw
arctl delete mcp fred-incluster-mcp --tag latest
kubectl delete -f assets/mcp/in-cluster/fred-deployment.yaml
kubectl delete secret fred-api-key -n mcp
kubectl delete namespace mcp --ignore-not-found
# Only if you're done with the parent Gateway (other MCP labs share it):
kubectl -n agentgateway-system delete httproute remote-mcp-delegate --ignore-not-found
kubectl -n agentgateway-system delete gateway   mcp-gateway   --ignore-not-found
```

## Next

- [MCP Client UI](mcp-client-ui.md) - call this endpoint from a browser instead of curl
- [In-Cluster MCP Server](in-cluster-mcp.md) - the no-credential version of this pattern
- [AccessPolicy / RBAC](../access-control/access-policies.md) - control who can see this server in the catalog
