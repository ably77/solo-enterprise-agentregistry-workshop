# Playwright Browser MCP (package-based stdio)

The [demo-tools](local-stdio-mcp.md) lab registered an stdio server whose code lives in a Git repo
(`source.repository`), so you could `arctl pull` the source and run it. This lab covers the other
common stdio case: a server published to a **package registry**. Playwright ships its MCP server as
the npm package `@playwright/mcp`, so you register it by package identifier instead of a repo, and
run it with `npx`.

Playwright's MCP gives an agent a real browser: navigate, click, type, snapshot the page, take
screenshots. It's the same server Claude and other MCP clients use for browser automation.

This is a stdio server, so there's no gateway route and no `curl` endpoint (those are for
remote/HTTP MCPs - see [Solo Docs](solo-docs-mcp.md), [arXiv](in-cluster-mcp.md)). An stdio server
is spawned as a subprocess by whatever hosts it, so to exercise it we run it on the laptop and an
agent would spawn it the same way.

## Lab Objectives

- Register an `MCPServer` whose source is an **npm package** (`source.package`, not
  `source.repository` or `remote`)
- Understand why `arctl pull` doesn't apply to a package-based entry
- Run the server locally over stdio - your laptop as the runtime - and call a real browser tool

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- `node` and `npx` on your PATH (Node 18+). The first browser tool call downloads a headless
  Chromium build if you don't already have one (Playwright manages its own browser binaries; if it
  complains, run `npx playwright install chromium`).
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

> **Third-party image notice:** `@playwright/mcp` is published by Microsoft. As with any MCP server
> you didn't write, pin a version (this lab uses `0.0.76`) and review it before relying on it.

## 1. Inspect the Manifest

[`assets/mcp/playwright/playwright-mcp.yaml`](../../assets/mcp/playwright/playwright-mcp.yaml)
registers the server by its npm coordinates. The key block is `source.package`:

```yaml
spec:
  source:
    package:
      origin:
        type: npm
        identifier: "@playwright/mcp"
        npm:
          serverName: "io.github.microsoft/playwright-mcp"
          version: "0.0.76"
      transport:
        type: stdio
```

An `MCPServer` spec must set exactly one of `remote`, `source.repository`, or `source.package`:

| Field | Means | Examples in this workshop |
|---|---|---|
| `remote` | an already-running server at a URL | [Solo Docs](solo-docs-mcp.md), [arXiv](in-cluster-mcp.md) |
| `source.repository` | clone a Git repo and run it | [demo-tools](local-stdio-mcp.md) |
| `source.package` | a server published to npm / PyPI / OCI | **this lab** |

Because the source is a package, there's nothing to clone, so **`arctl pull` doesn't apply here** -
the npm registry is the distribution. (`pull` is for `source.repository` entries.)

## 2. Register It

```bash
arctl apply -f assets/mcp/playwright/playwright-mcp.yaml
```

```
✓ MCPServer/playwright (latest) created
```

Verify it's in the catalog and the package coordinates round-tripped:

```bash
arctl get mcps
arctl get mcp playwright --tag latest -o yaml | sed -n '/source:/,/tools:/p'
```

## 3. Run It Locally and Call a Browser Tool

The catalog entry records *what* to run (`@playwright/mcp@0.0.76`, stdio). To actually exercise it,
run that package on your laptop and talk MCP to it over stdin/stdout - exactly what an agent runtime
does when it spawns the server, just by hand. `--headless` runs with no visible window; `--isolated`
uses a fresh browser profile each run.

First, list the tools (no browser needed yet):

```bash
( printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"laptop","version":"0.0.1"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  sleep 6
) | npx -y @playwright/mcp@0.0.76 --headless --isolated 2>/dev/null \
  | jq -rc 'select(.id==2) | .result.tools[].name'
```

You'll see the browser toolset: `browser_navigate`, `browser_click`, `browser_type`,
`browser_snapshot`, `browser_take_screenshot`, `browser_fill_form`, and more.

> **Why the trailing `sleep`?** Browser tool calls are asynchronous - the server launches Chromium
> and only then replies. A bare `printf | npx ...` closes stdin the instant the last line is
> written, which can tear the server down before it answers. Holding stdin open with a short `sleep`
> keeps the process alive long enough to respond. This is a quick way to script a stdio server by
> hand; for interactive use, point an MCP client (or `arctl run --inspector` on a scaffolded
> project) at it instead.

Now call a real browser tool - navigate to a page and read back what loaded:

```bash
( printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"laptop","version":"0.0.1"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"browser_navigate","arguments":{"url":"https://example.com"}}}'
  sleep 18
) | npx -y @playwright/mcp@0.0.76 --headless --isolated 2>/dev/null \
  | jq -rc 'select(.id==2) | .result.content[].text'
```

The result reports the page it loaded:

```
### Ran Playwright code
` ` `js
await page.goto('https://example.com');
` ` `
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
...
```

That round trip - laptop spawns the npm package, drives a headless browser, returns the page - is
the whole point: the catalog told you exactly what to run, and the server runs wherever you (or an
agent) spawn it.

## How an Agent Uses It

You don't normally drive an stdio server by hand. An Agent references it by catalog name under
`spec.mcpServers`, and the agent runtime spawns `@playwright/mcp` as a subprocess and offers its
tools to the model:

```yaml
# (illustrative) inside an Agent spec
spec:
  mcpServers:
    - name: playwright
```

Where that subprocess runs depends on the runtime: on your laptop during local development
(`arctl run`), or inside a managed container when deployed. Package-based servers like this one are
what a Kubernetes/kagent runtime provisions from the recorded npm coordinates - that deployment path
is its own topic, out of scope for this catalog-and-run lab.

## Cleanup

```bash
arctl delete mcp playwright --tag latest
```

The local runs leave nothing behind - `--isolated` uses a throwaway profile, and no server keeps
running after the `sleep` ends.

## Next

- [Local stdio MCP Server (demo-tools)](local-stdio-mcp.md) - the Git-source variant of stdio, with `arctl pull`
- [Solo Docs MCP through Agentgateway](solo-docs-mcp.md) - remote MCP, gateway-fronted
- [AccessPolicy / RBAC](../access-control/access-policies.md) - control who can see this server in the catalog
