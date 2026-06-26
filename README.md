# Enterprise Agentregistry Workshop

A hands-on workshop for **Solo.io Enterprise Agentregistry** — the agent/MCP catalog
and control plane driven by `arctl` and the `ar.dev/v1alpha1` API. One install lab gets you a full
baseline; every other lab is short, self-contained, and returns the cluster to that baseline when
you're done.

## Prerequisites

- A Kubernetes cluster (≥ 1.29) with a default `StorageClass` and a working `LoadBalancer` Service controller
- `kubectl`, `helm` v3, `openssl`, `envsubst`, `jq`

# Table of Contents

- [Installation](#installation)
- [MCP (Model Context Protocol)](#mcp-model-context-protocol)
- [Catalog](#catalog)
- [Access Control](#access-control)

---

## Installation

> **Start here.** Everything else assumes this baseline.

- [001 — Installation](001-installation.md) — `arctl` + in-cluster Keycloak (OIDC) + Agentregistry Enterprise + Enterprise Agentgateway + login

---

## MCP (Model Context Protocol)

- [Solo.io Docs MCP through Agentgateway](labs/mcp/solo-docs-mcp.md) — **recommended first lab.** Catalog the public `search.solo.io` MCP, expose it through a `Virtual` runtime + Agentgateway, and call its `search` tool end-to-end (no token required)
- [DeepWiki MCP through Agentgateway](labs/mcp/deepwiki-mcp.md) — a second public remote MCP (GitHub-repo Q&A) on the same gateway at its own path (no token)
- [In-Cluster MCP Server (Bring Your Own)](labs/mcp/in-cluster-mcp.md) — self-host an MCP server (`Deployment`+`Service`) and register it by its in-cluster Service URL
- [In-Cluster MCP Server with a Credential (FRED)](labs/mcp/fred-mcp.md) — self-host an MCP server that needs an API key; keep the secret in a k8s `Secret`, out of the catalog
- [Local stdio MCP Server](labs/mcp/local-stdio-mcp.md) — register the in-tree `demo-tools` stdio MCP (Git source; `arctl pull` + run it locally)
- [Playwright Browser MCP](labs/mcp/playwright-mcp.md) — register a **package-based** stdio MCP (npm `@playwright/mcp`) and drive a real headless browser locally
- [MCP Client UI](labs/mcp/mcp-client-ui.md) — a local Streamlit app to call the gateway-fronted MCPs from a browser (live/not-deployed status, Connect, tool dropdowns, gateway logs) instead of hand-written `curl`

## Catalog

- [Prompts (Catalog Quickstart)](labs/catalog/prompts.md) — `Prompt` CRUD via `arctl` (~5 min)

## Access Control

- [AccessPolicy / RBAC](labs/access-control/access-policies.md) — grant a non-admin group catalog read access; prove it with the `reader` user
- [Approval Workflows](labs/access-control/approval-workflows.md) — gate every catalog submission behind admin approval (`requireCreateApproval`)

---

# Use Cases

- Install Agentregistry Enterprise on Kubernetes with OIDC (in-cluster Keycloak)
- Register MCP servers as catalog assets — `stdio` (local, in-tree), public `streamable-http` (remote), and self-hosted in-cluster servers (registered by Service URL), including servers that need their own API key (kept in a k8s `Secret`, out of the catalog)
- Expose remote and in-cluster MCP servers through Enterprise Agentgateway via a `Virtual` runtime — one gateway endpoint, many backends at distinct paths, with gateway-managed TLS to the upstream
- Manage versioned `Prompt` catalog assets independently of agents
- Enforce catalog RBAC with `AccessPolicy` against Keycloak group names
- Gate catalog submissions behind admin approval and approve/reject via the `/v0/approve` API

## Repo Layout

```
fe-enterprise-agentregistry-workshop/
├── README.md
├── 001-installation.md                  # full baseline in one lab
├── labs/
│   ├── mcp/
│   │   ├── solo-docs-mcp.md             # remote MCP through Agentgateway (start here)
│   │   ├── deepwiki-mcp.md              # second remote MCP, same gateway
│   │   ├── in-cluster-mcp.md            # self-hosted MCP server, registered by Service URL
│   │   ├── local-stdio-mcp.md           # in-tree stdio MCP (Git source)
│   │   ├── playwright-mcp.md            # package-based stdio MCP (npm @playwright/mcp)
│   │   └── mcp-client-ui.md             # local Streamlit client for the gateway MCPs
│   ├── catalog/
│   │   └── prompts.md
│   └── access-control/
│       ├── access-policies.md
│       └── approval-workflows.md
├── assets/
│   ├── keycloak/                        # kustomize stack: deployment + agentregistry-enterprise.json (--import-realm)
│   ├── prompts/                         # Prompt manifest
│   └── mcp/
│       ├── demo-mcp/                    # stdio MCP source (server.py) + manifest
│       ├── playwright/                  # package-based (npm) stdio MCP manifest
│       ├── in-cluster/                  # self-hosted arXiv + FRED MCP: Deployment/Service + catalog/deploy
│       └── agentgateway/                # parent Gateway/Route + Solo Docs & DeepWiki catalog/deploy
├── mcp-client/                          # local Streamlit MCP client (./run.sh) for the gateway MCPs
└── e2e-test.sh                          # end-to-end test: install baseline + every lab, with pass/fail
```

## Validated On

- Agentregistry Enterprise + `arctl` `v2026.6.1`
- Enterprise Agentgateway `v2026.6.1`
- Keycloak `quay.io/keycloak/keycloak:26.0`
- Kubernetes 1.29+
