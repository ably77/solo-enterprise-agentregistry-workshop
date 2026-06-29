# Changelog

0.0.4 - (6-29-26)
---
- Update Agentregistry version to `v2026.6.2`
- Added airgap installation lab at `solo-enterprise-agentregistry-workshop/labs/installation/airgap`
- Add image-list.md at `solo-enterprise-agentregistry-workshop/labs/installation/image-list.md`
- Add airgapped image list at `solo-enterprise-agentregistry-workshop/labs/installation/airgap/ably7-image-list.md`
- Provide a script to update air-gapped image repo `solo-enterprise-agentregistry-workshop/labs/installation/mirror-images-to-private-repo.sh`

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
