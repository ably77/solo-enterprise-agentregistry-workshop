# Workshop MCP Client (local UI)

A small [Streamlit](https://streamlit.io/) app for making **live MCP requests to the
gateway-fronted MCP servers** from this workshop — without hand-writing the `curl`
JSON-RPC handshake. It connects over Streamable HTTP, lists tools, renders parameter
inputs from each tool's JSON Schema, calls tools, and shows the gateway's request logs.

It's the same embedded MCP-client widget used by the Enterprise Agentgateway demo UI,
vendored here (`mcp_client.py`) and wrapped with a workshop-specific endpoint picker.

## Prerequisites

- The workshop baseline is installed and at least one MCP lab is deployed (so a
  `/registry/<name>` endpoint exists) — see [`../001-installation.md`](../001-installation.md)
  and the [MCP labs](../labs/mcp/).
- `kubectl` pointed at the workshop cluster (used only to auto-detect the gateway
  address and stream its logs — you can also enter the address manually).
- Python 3.9+.

## Run

```bash
./run.sh
# → open http://localhost:8501
```

`run.sh` creates a local `.venv`, installs `streamlit` + `requests`, and launches the app.
Change the port with `PORT=8600 ./run.sh`.

## Using it

1. **Gateway address** (sidebar) is auto-detected from
   `kubectl -n agentgateway-system get gateway agentregistry-gateway`. If detection fails
   (e.g. kubectl isn't configured here), type the LoadBalancer IP/hostname in. The
   listener is HTTP/80, so leave **Port** blank.
2. Pick an **Endpoint** (Solo Docs, DeepWiki, arXiv, FRED, or a custom path). Each is
   probed and badged 🟢 live / ⚪ not deployed / 🔴 unreachable so you know what's callable;
   not-live endpoints show a hint to the lab that deploys them. **Re-check endpoints**
   (sidebar) refreshes after you deploy one.
3. Click **Connect** — runs `initialize` + `notifications/initialized`, then `tools/list`.
4. Choose a **Tool** from the dropdown; parameters are pre-filled with a working example.
5. **Call Tool** — the result renders below, and every call is kept in **Call History**.
6. Expand **View Gateway Logs** to watch the `POST /registry/<name>` requests land.

The **Custom HTTP Headers** expander lets you add/toggle headers (e.g. an
`Authorization` bearer) — handy for endpoints that require caller auth.

## Scope

This client speaks MCP over HTTP, so it only covers the **gateway-fronted** servers
(`/registry/...`). The workshop's `demo-tools` (stdio) MCP and the `Prompt` asset are
**catalog-only** — they have no HTTP endpoint and are inspected with `arctl get mcps` /
`arctl get prompts`, not here.

## Files

| File | Purpose |
|---|---|
| `Homepage.py` | Endpoint picker, sidebar address override, client + logs |
| `mcp_client.py` | Vendored MCP-over-Streamable-HTTP widget (`render_mcp_client`) |
| `cluster.py` | Gateway-address detection + gateway-log viewer (`agentregistry-gateway`) |
| `run.sh` | venv bootstrap + launch |
