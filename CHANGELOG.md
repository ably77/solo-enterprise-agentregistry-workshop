# Changelog

0.1.3 - (7-10-26)
---
- Fix to `e2e-agentcore.sh`

0.1.2 - (7-10-26)
---
- Added an opt-in AgentCore e2e mode (`./e2e-test.sh agentcore` / `agentcore-cleanup` / `--include-agentcore`): new `e2e-agentcore.sh` module automating the AgentCore labs Parts 1 + 3, plus optional gitignored `./secrets` sourcing and a billing banner for left-running AWS resources
- Documented + worked around an `arctl` auth quirk: `arctl runtime setup` authenticates only via `ARCTL_API_TOKEN` (device-login session ignored → `401`), so `agentcore-01-integration.md` step 2 gained a mint-a-token callout + troubleshooting row and the e2e module mints the token itself

0.1.1 - (7-10-26)
---
- Docs fix in `labs/runtimes/agentcore-04-agentgateway-llm-mcp.md`

0.1.0 - (7-10-26)
---
- Added `labs/runtimes/agentcore-cleanup.md` — consolidated teardown for all four AgentCore labs; each lab's inline Cleanup section now points here instead of repeating commands, with breadcrumb nav and cost-note cross-references updated across `agentcore-01/02/03/04-*.md` and `README.md` (Agent Runtimes list + repo layout tree)
- `agentcore-01-integration.md`: prefix every fixed-name AWS resource with `AR_USER_PREFIX=$(whoami)` — IAM policies, deployer user, cross-account role (via `--role-name`), CloudFormation stack — so concurrent installs in a shared AWS account don't collide on the same names; added a guarded `sed` patch for the trust policy principal (`arctl` exposes no flag for it) and updated `agentcore-cleanup.md`'s Part 1 teardown and shared-account callout to match
- Fixes to `/labs/runtimes/agentcore-04-agentgateway-llm-mcp.md`

0.0.9 - (7-9-26)
---
- Added `labs/runtimes/agentcore-04-agentgateway-llm-mcp.md` — Part 4 of the AgentCore series: extend `econresearch` into `econresearch-agw`, with LLM calls (OpenAI `gpt-5.4-nano` via an Agentgateway `/openai` route, key in a k8s `Secret` at the gateway) and live FRED data (via `spec.mcpServers` and an agent-facing `fred-gateway-mcp` catalog entry carrying the public gateway URL — the registry rejects `deploymentRefs` to remote MCPs with `ErrMCPSetMismatch`) both routed through the workshop's Agentgateway; requires a publicly reachable gateway LB. The agent ships a `requirements.txt` pinning `litellm` because the AgentCore builder installs from it and ignores `Dockerfile`/`pyproject.toml`
- Added `assets/mcp/agentgateway/openai-backend-and-route.yaml` — unpinned OpenAI `AgentgatewayBackend` + `/openai` `HTTPRoute` on the shared `agentregistry-gateway` (expects an `openai-secret` created imperatively, never checked in)

0.0.8 - (7-9-26)
---
- Added a three-part AWS Bedrock AgentCore lab series at `labs/runtimes/`:
  - `agentcore-01-integration.md` — teaches the external dependencies from zero (step 0): operator AWS CLI setup, region choice, Bedrock model availability, and the two-identity model (operator vs registry deployer credentials + cross-account role); registers the `agentcore` Runtime
  - `agentcore-02-create-agents.md` — high-level walkthrough of how the four example agents were created (`arctl init agent` ADK/Bedrock scaffold, one customized `agent.py`, Git-sourced catalog entry); the agents are already checked in, so no push-to-GitHub step
  - `agentcore-03-deploy-agents.md` — publish + deploy `econresearch` (and the three other agents) to AgentCore, chat from the UI, tail CloudWatch; deploy-scoped troubleshooting and cleanup
- New **Agent Runtimes** section in `README.md` (TOC, use cases, repo layout updated)
- Added three agent examples in `assets/agents/` — `claimsupport`, `bankingsupport`, and `ithelpdesk`, insurance claim, personal banking, and IT helpdesk support assistants matching econresearch's ADK/Bedrock scaffold, wired into the AgentCore labs and README

0.0.7 - (7-8-26)
---
- Added `labs/access-control/README.md` — Access Control section overview: the governance surface (catalog, OIDC identity, `AccessPolicy` RBAC, approval workflows, single gateway entry point, versioned assets) and the scope boundary between Registry asset governance and upstream AI/model governance
- Linked the new overview as the first item under the Access Control section of `README.md`

0.0.6 - (7-8-26)
---
- Updates to `labs/access-control/approval-workflows.md`. Add multiple methods of approving a registry addition (AR UI, curl, BYO UI)
- Renamed the parent Gateway `mcp-gateway` → `agentregistry-gateway` across labs, `mcp-client/`, `assets/mcp/agentgateway/`, and `e2e-test.sh`
- Recaptured `assets/screenshots/06-are-ui-gateways.png` and `09-mcp-client-gateway-logs.png` to show the renamed gateway

0.0.5 - (6-29-26)
---
- Air-gap lab fixes:
  - Renamed `mirror-images-to-private-repo.sh` -> `mirror-images.sh` to match all doc references/links
  - Keycloak image override moved to an `assets/keycloak/overlays/airgap/` overlay so the shared base (used by the connected install + `e2e-test.sh`) is left untouched
  - Added `licensing` to the Agentregistry Enterprise values so the server no longer logs a `LICENSE ERROR` at startup

0.0.4 - (6-29-26)
---
- Update Agentregistry version to `v2026.6.2`
- Added airgap installation lab at `solo-enterprise-agentregistry-workshop/labs/installation/airgap`
- Add image-list.md at `solo-enterprise-agentregistry-workshop/labs/installation/image-list.md`
- Add airgapped image list at `solo-enterprise-agentregistry-workshop/labs/installation/airgap/ably7-image-list.md`
- Provide a script to update air-gapped image repo `solo-enterprise-agentregistry-workshop/labs/installation/mirror-images.sh`

0.0.3 - (6-26-26)
---
- Updates to `e2e-test.sh`

0.0.2 - (6-26-26)
---
- Quick updates to `README.md`

0.0.1 - (6-26-26)
---
- Initial commit. Enterprise Agentregistry Workshop which covers the following labs:
  - **Installation** — `arctl` + in-cluster Keycloak (OIDC) + Agentregistry Enterprise + Enterprise Agentgateway + login
  - **MCP (Model Context Protocol)**
    - Solo.io Docs MCP through Agentgateway — catalog the public `search.solo.io` MCP, expose via a `Virtual` runtime + Agentgateway, call its `search` tool
    - DeepWiki MCP through Agentgateway — a second public remote MCP on the same gateway at its own path
    - In-Cluster MCP Server (Bring Your Own) — self-host a `Deployment`+`Service` and register it by in-cluster Service URL
    - In-Cluster MCP Server with a Credential (FRED) — API key kept in a k8s `Secret`, out of the catalog
    - Local stdio MCP Server — register the in-tree `demo-tools` stdio MCP (Git source; `arctl pull` + run locally)
    - Playwright Browser MCP — register a package-based stdio MCP (npm `@playwright/mcp`)
    - MCP Client UI — local Streamlit app to call gateway-fronted MCPs from a browser
  - **Catalog**
    - Prompts — `Prompt` CRUD via `arctl`
    - Field RFE Skill — scaffold with `arctl init skill`, publish a versioned `Skill`, ship a second tag, and `arctl pull` it as a consumer
    - Changelog Skill — same skill flow using the `/changelog` skill: publish, version, and `arctl pull` it as a consumer
  - **Access Control**
    - AccessPolicy / RBAC — grant a non-admin group catalog read access
    - Approval Workflows — gate catalog submissions behind admin approval (`requireCreateApproval`)
- `e2e-test.sh` — end-to-end test covering the install baseline plus every lab, with pass/fail
