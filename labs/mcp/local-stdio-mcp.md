# Local stdio MCP Server (`demo-tools`)

Register a small in-tree MCP server with Agentregistry. The server is a zero-dependency Python
script exposing three tools (`get_time`, `random_number`, `reverse_string`) over `stdio`.
Agentregistry clones it from a repo and treats it as a catalog asset that agents can reference.

This is the simplest MCP lab - there's no `Deployment` and no gateway route. Catalog-only doesn't
mean you can't run it, though. A stdio server has no network endpoint; it's spawned as a subprocess
by whatever hosts it. Once it's in the catalog you can consume it two ways:

- Reference `demo-tools` in an Agent's `spec.mcpServers` block. The agent runtime spawns the server
  in-process; in-cluster that's inside the agent's pod.
- Pull the source out of the catalog with `arctl pull` and run it on your own machine, as step 4
  does. No agent and no infra; your laptop is the runtime.

## Lab Objectives

- Register an `MCPServer` with `transport: stdio` and `source: repository`
- Verify the catalog entry shows up in `arctl get mcps`
- Pull the server back out of the catalog with `arctl pull` and run it locally - your laptop as the runtime

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

## 1. Inspect the Files

[`assets/mcp/demo-mcp/`](../../assets/mcp/demo-mcp/) holds `mcpserver.yaml` (the catalog manifest)
and `server.py` (a ~120-line stdio JSON-RPC MCP server).

## 2. Register the MCP Server

Inspect the manifest, then register it:

```bash
cat assets/mcp/demo-mcp/mcpserver.yaml
arctl apply -f assets/mcp/demo-mcp/mcpserver.yaml
```

```
✓ MCPServer/demo-tools (1.0.0) created
```

## 3. Verify

```bash
arctl get mcps
```

```
NAME         TAG     DESCRIPTION
demo-tools   1.0.0   A minimal MCP server with simple tools: get_time, random_...
```

Inspect the full record. This asset is tagged `1.0.0`, and a single-tag asset is **not**
auto-aliased to `latest` - use the declared tag (or `--all-tags`):

```bash
arctl get mcp demo-tools --tag 1.0.0 -o yaml
arctl get mcp demo-tools --all-tags
```

> `arctl get mcp demo-tools --tag latest` (and the bare `arctl get mcp demo-tools`, which defaults
> to `latest`) return `resource not found` here - there is no `latest` tag on this asset.

## 4. Pull It Down and Run It Locally

Registering the server stored a pointer, not the code. The catalog record keeps the repo URL,
subfolder, and tag under `spec.source.repository` - enough for `arctl` to fetch the source and run
it on any machine. You don't have to know where the code lives or copy it around by hand.

`arctl pull` clones the source from the catalog record into a local directory. Run it from anywhere,
including outside this repo:

```bash
arctl pull mcp demo-tools --tag 1.0.0 ./demo-tools
ls ./demo-tools          # server.py + mcpserver.yaml
```

> Use the declared tag. `demo-tools` exists only at `1.0.0`, with no `latest` alias, so a bare
> `arctl pull mcp demo-tools` returns `resource not found`. Pass `--tag 1.0.0`.

The server is zero-dependency Python over stdio, so you can drive it directly: pipe
newline-delimited JSON-RPC into `python3 server.py` and read the responses. No agent, no gateway.

```bash
cd ./demo-tools
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"laptop","version":"0.0.1"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"reverse_string","arguments":{"text":"pulled-from-registry"}}}' \
  | python3 server.py | jq -c .
```

You get the `initialize` result, the three-tool list, and `reverse_string` returning
`yrtsiger-morf-dellup` - all from the copy you just pulled, with nothing preinstalled.

`arctl pull` only clones source. This server needs no dependencies; one that ships a
`requirements.txt` or `package.json` needs its install step first. A project scaffolded with
`arctl init` pairs the source with an `arctl.yaml` that declares the framework's build and run
commands, so `arctl run` handles setup for you: for an Agent it starts the runtime and opens an
interactive chat; for an MCPServer it runs in the foreground (add `--inspector` to call tools from a
browser).

This is the value of a catalog entry even with no deployment: publish a server once, and anyone with
`arctl` and registry access can find it (`arctl get mcps`), pull it (`arctl pull`), and run it
locally. The registry is the discovery and distribution layer; Git stays the artifact store. `pull`
works the same way for `agent` and `skill` resources.

## Where the Server Runs

Unlike a remote MCP (see [Solo Docs MCP](solo-docs-mcp.md)), the stdio variant runs **inside** the
agent's container: when an agent references `demo-tools` under `spec.mcpServers`, the agent runtime
spawns `python3 server.py` as a subprocess and talks to it over stdin/stdout. So there's no
`Deployment` for an stdio MCP - just the catalog entry.

The same thing happens when you run it yourself (step 4): your shell is the host that spawns the
subprocess. The host can be an agent's pod, a CI job, or your laptop - the catalog entry is
identical in every case.

## Cleanup

```bash
arctl delete mcp demo-tools --tag 1.0.0
rm -rf ./demo-tools   # the local copy pulled in step 4
```

## Next

- [Solo Docs MCP through Agentgateway](solo-docs-mcp.md) - remote MCP, gateway-fronted
- [AccessPolicy / RBAC](../access-control/access-policies.md) - restrict who can see this MCP
