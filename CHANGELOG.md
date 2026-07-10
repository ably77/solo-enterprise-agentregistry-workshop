# Changelog

0.0.8 - (7-9-26)
---
- Added a three-part AWS Bedrock AgentCore lab series at `labs/runtimes/`:
  - `agentcore-01-integration.md` — teaches the external dependencies from zero (step 0): operator AWS CLI setup, region choice, Bedrock model access enablement, and the two-identity model (operator vs registry deployer credentials + cross-account role); registers the `agentcore` Runtime
  - `agentcore-02-create-agents.md` — high-level walkthrough of how the four example agents were created (`arctl init agent` ADK/Bedrock scaffold, one customized `agent.py`, Git-sourced catalog entry); the agents are already checked in, so no push-to-GitHub step
  - `agentcore-03-deploy-agents.md` — publish + deploy `econresearch` (and the three other agents) to AgentCore, chat from the UI, tail CloudWatch; deploy-scoped troubleshooting and cleanup
- Added `assets/agents/econresearch/` — a new vertical-use-case agent (FSI economic research assistant): Google ADK Python on Bedrock Claude (`us.anthropic.claude-sonnet-4-6`) with tools over a curated FRED-style indicator snapshot
- Added `assets/runtimes/agentcore/` — the two IAM policies the registry server needs for AgentCore (from the docs quickstart)
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
