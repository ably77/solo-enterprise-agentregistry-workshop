# Approval Workflows

When you grant a non-admin group `registry:publish` / `registry:edit`, those users can submit new
catalog assets. A stricter setup requires an **admin approval** on every submission before it lands
in the catalog. Agentregistry gates this with one Helm knob: `config.requireCreateApproval=true`.
Once on, every `Agent`, `MCPServer`, `Skill`, and `Prompt` a non-admin submits goes into an
**Administrative Requests** queue that an admin reviews with one of three methods: the AgentRegistry
UI, curl against the `/v0/approve` HTTP API, or a custom integration built on that same API. The UI
calls rejecting a request **Withdraw**.

> **Scope:** approval gating covers catalog assets (`Agent`, `MCPServer`, `Skill`, `Prompt`).
> `Deployment` resources are **not** approval-gated.

## Lab Objectives

- Enable `config.requireCreateApproval=true`
- Grant `are-readers` writer access
- Submit an `Agent` as the non-admin `reader` and confirm it's staged, not committed
- Approve it via one of three methods: the AgentRegistry UI, curl, or a custom integration
- Verify the approved asset is in the catalog

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- Familiarity with [AccessPolicy](access-policies.md)
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
export KC_IP=$(kubectl get svc keycloak -n keycloak \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')

# token helpers for acting as each user without clobbering the keychain
token_for() {
  curl -s -X POST "http://${KC_IP}:8080/realms/agentregistry-enterprise/protocol/openid-connect/token" \
    -d grant_type=password -d client_id="${ARE_CLI_CLIENT_ID}" \
    -d username="$1" -d password="$1" -d "scope=openid profile" | jq -r .access_token
}
```

## 1. Enable the Feature Flag

`--reuse-values` preserves the OIDC/telemetry settings from install:

```bash
helm upgrade --install agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.7.0 \
  --namespace agentregistry-system \
  --reuse-values \
  --set config.requireCreateApproval=true
kubectl rollout status -n agentregistry-system deploy/agentregistry-enterprise-server
```

Verify:

```bash
kubectl -n agentregistry-system get configmap agentregistry-enterprise \
  -o jsonpath='{.data.REQUIRE_CREATE_APPROVAL}{"\n"}'
```

```
true
```

## 2. Grant `are-readers` Writer Access

Approval is only interesting when a non-admin can *submit* but not *commit*. Grant the group
`registry:publish` + `registry:edit` (Keycloak path uses the group **name**):

```bash
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: AccessPolicy
metadata:
  name: are-readers-catalog-write
spec:
  description: "Publish/edit access for are-readers; submissions are approval-gated"
  principals:
    - kind: Role
      name: "are-readers"
  rules:
    - actions: ["registry:read", "registry:publish", "registry:edit"]
      resources:
        - kind: agent
          name: "*"
        - kind: server
          name: "*"
EOF
```

## 3. Submit an Agent as the Non-Admin User

Act as `reader` via `ARCTL_API_TOKEN`:

```bash
ARCTL_API_TOKEN=$(token_for reader) arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: Agent
metadata:
  name: approval-test-agent
  tag: "1.0.0"
spec:
  title: approval-test-agent
  description: "Test agent for approval workflow validation"
  modelProvider: anthropic
  modelName: claude-sonnet-4-6
  source:
    image: docker.io/python:3.13-slim
EOF
```

The asset is **staged**, not committed:

```
✓ Agent/approval-test-agent (1.0.0) staged
```

Confirm it's not a normal catalog item yet:

```bash
ARCTL_API_TOKEN=$(token_for reader) arctl get agent approval-test-agent --tag 1.0.0
# → Error: getting agent "approval-test-agent": resource not found
```

## 4. Approve the Pending Request

Three ways to review and approve or reject a pending submission. All three operate
on the same `/v0/approve` resource.

### Method 1 (recommended): AgentRegistry UI

Log in to the AgentRegistry UI as `admin` at `http://${AR_IP}:12121`. A 🔔 badge
appears on the top-nav Notifications button once a request is pending. Open the
**Catalog** page. The pending item shows up in an **Administrative Requests**
panel above the catalog grid, with **Approve** and **Withdraw** buttons. Withdraw
is the UI's name for reject.

### Method 2: curl

List the pending request:

```bash
curl -s -H "Authorization: Bearer $(token_for reader)" \
  "${ARCTL_API_BASE_URL}/v0/approve" | jq '.items[] | {kind,namespace,name,tag,state}'
```

```json
{ "kind": "Agent", "namespace": "default", "name": "approval-test-agent", "tag": "1.0.0", "state": "pending" }
```

Approve it. This requires a superuser token, and the exact tuple from the list call:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $(token_for admin)" \
  -H "Content-Type: application/json" \
  -d '{"action":"approve","items":[{"kind":"Agent","namespace":"default","name":"approval-test-agent","tag":"1.0.0"}]}' \
  "${ARCTL_API_BASE_URL}/v0/approve" | jq .
```

```json
{ "results": [ { "kind": "Agent", "name": "approval-test-agent", "tag": "1.0.0", "status": "approved" } ] }
```

> `action` also accepts `reject`, which removes the request without committing. The UI calls this **Withdraw**.

### Method 3: integrate into your own UI

`/v0/approve` isn't special-cased to the product UI. Any internal tool can call it
directly: `GET /v0/approve` for the pending list, then `POST /v0/approve` with
`{"action": "approve" | "reject", "items": [...]}` for the selected tuples.

## 5. Verify the Asset Is in the Catalog

```bash
ARCTL_API_TOKEN=$(token_for admin) arctl get agent approval-test-agent --tag 1.0.0
```

```
NAME                  TAG     PROVIDER    MODEL
approval-test-agent   1.0.0   anthropic   claude-sonnet-4-6
```

## Cleanup

```bash
arctl delete agent approval-test-agent --tag 1.0.0 2>/dev/null || true
arctl delete accesspolicy are-readers-catalog-write 2>/dev/null || true

# disable the flag (does not retroactively release queued requests; reject those first)
helm upgrade --install agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.7.0 \
  --namespace agentregistry-system \
  --reuse-values \
  --set config.requireCreateApproval=false
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `REQUIRE_CREATE_APPROVAL` still empty after upgrade | Wrong release/namespace. `helm list -n agentregistry-system`, then `kubectl rollout status -n agentregistry-system deploy/agentregistry-enterprise-server`. |
| Non-admin commits directly (no staging) | They're a superuser. `arctl get accesspolicies` / check group membership - admins bypass the queue. |
| `/v0/approve` POST returns 404 / empty result | The `kind`/`namespace`/`name`/`tag` tuple doesn't match what `GET /v0/approve` listed (often `namespace`: `default`). |
| Submitted asset never appears in the queue | The submitter lacks `registry:publish` (just `registry:read` isn't enough). Re-check the policy in step 2. |

## Next

- [AccessPolicy / RBAC](access-policies.md) - the foundation this builds on
- [Solo Docs MCP through Agentgateway](../mcp/solo-docs-mcp.md)
