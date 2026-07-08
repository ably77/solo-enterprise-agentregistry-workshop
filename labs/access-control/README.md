# Access Control — What the Registry Governs

Agentregistry Enterprise is the **control plane for who can discover, submit, change, and use**
agentic assets — MCP servers, agents, skills, and prompts. It governs those assets **once they
exist** in the catalog. It does not validate or risk-classify the models behind them; that belongs
to whatever model/AI-governance process clears an asset *before* it's published here.

| The Registry governs | Handled upstream (not the Registry) |
|---|---|
| **Agent & MCP asset governance** — who can see, submit, edit, and use catalog assets | **AI / model governance** — model validation, approval, and risk classification |
| Client/consumer access · RBAC · submission gating | Done before an asset is cleared to publish to the catalog |

## The governance surface

Everything the Registry enforces reduces to a few controls, most of which the labs in this section
prove hands-on:

1. **Centralized catalog** — one Kubernetes-native source of truth for every MCP server, agent,
   skill, and prompt, each with a known owner, version, and identity. Driven by the
   `ar.dev/v1alpha1` API and the `arctl` CLI. *(Established across the MCP and Catalog labs.)*
2. **Identity & authentication (OIDC)** — all access is tied to a verified identity; group/role
   claims from the IdP drive every authorization decision. *(Set up in [Installation](../../001-installation.md).)*
3. **RBAC — `AccessPolicy`** — maps an OIDC principal to allowed actions
   (`registry:read` / `registry:publish` / `registry:edit`) on specific catalog resources. This is
   how "who's allowed to use it" is enforced after an asset lands in the catalog.
   → [AccessPolicy / RBAC](access-policies.md)
4. **Approval workflows** — with `config.requireCreateApproval=true`, non-admin submissions are
   *staged, not committed*, and an admin clears them from an Administrative Requests queue.
   → [Approval Workflows](approval-workflows.md)
5. **Single governed entry point** — registered MCP servers and agents are fronted by Enterprise
   Agentgateway, so access is enforced at one controlled endpoint rather than per-client wiring.
   *(Built in the MCP labs.)*
6. **Versioned assets** — skills and prompts are published as versioned, pullable catalog assets, so
   a consumer uses an explicit, approved version rather than an arbitrary snapshot.
   *(Built in the Catalog labs.)*

## Labs in this section

- [AccessPolicy / RBAC](access-policies.md) — grant a non-admin group catalog read access; prove it
  with the `reader` user, and see why the principal must be the Keycloak group **name**, not its GUID
- [Approval Workflows](approval-workflows.md) — gate every catalog submission behind admin approval
  (`requireCreateApproval`) and approve/reject via the UI, `/v0/approve` API, or a custom integration

> Start with **AccessPolicy** — approval workflows build directly on it.
