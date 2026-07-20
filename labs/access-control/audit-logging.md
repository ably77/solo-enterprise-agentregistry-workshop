# Audit Logging — Who Did What in the Registry

RBAC and approval workflows decide **who is allowed** to act on catalog assets. Audit logging is
the matching evidence layer: a structured, tamper-evident record of **who did what**. It covers
every resource lifecycle change, approval decision, and selected authorization check on the control
plane. Agentregistry Enterprise exports these as OpenTelemetry logs over OTLP/gRPC, so they land in
whatever SIEM or log platform your org already runs.

This lab does the **simple, local-testing case**: stand up a throwaway debug collector that prints
events to `stdout`, turn audit on, trigger an event, and read it back with `kubectl logs`. No SIEM
required. A pointer to the production setup is at the end.

## Lab Objectives

- Deploy a lightweight debug OTel collector that receives audit events and prints them to `stdout`
- Enable audit export on the registry with the `audit.*` Helm values
- Trigger a `lifecycle` event and read the full audit record from the collector logs
- Understand the audit event scopes and schema

## Pre-requisites

- [001 — Installation](../../001-installation.md) complete, on **Agentregistry Enterprise
  `v2026.7.0` or newer**. Audit logging did not exist before `v2026.7.0`; check with
  `arctl version` (server side) if unsure.
- Logged in as the `admin` (superuser), since enabling audit is a Helm/cluster operation.
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

## What Gets Audited

Every audit event lands on one of two OpenTelemetry **scopes** and carries an `event.activity`
category:

| Scope | `event.activity` | What it captures |
|---|---|---|
| `audit.resource_activity` | `lifecycle` | Create / update / delete of catalog resources (MCP servers, agents, skills, prompts, `AccessPolicy`, …) |
| `audit.resource_activity` | `approval` | Submissions staged, approved, or rejected in the approval workflow |
| `audit.resource_activity` | `applied_resource` | Materialization of applied resources (e.g. a `Deployment` being reconciled) |
| `audit.authz` | `authorization` | Permission checks. Denials and errors always emit; `audit.authz.allowedDecisions` controls which successful allows do |

> Audit events record **identity, action, and resource**. They **exclude** secrets, tokens, and
> full request/response payloads.

## 1. Deploy the Debug Collector

This collector listens for OTLP/gRPC events on port `4317` and prints each one to `stdout`. It has
no persistent storage; use it for development and testing only.

```bash
kubectl apply -f- <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: audit-debug-collector
  namespace: agentregistry-system
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: "0.0.0.0:4317"
    exporters:
      debug:
        verbosity: detailed
    service:
      pipelines:
        logs:
          receivers: [otlp]
          exporters: [debug]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: audit-debug-collector
  namespace: agentregistry-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: audit-debug-collector
  template:
    metadata:
      labels:
        app: audit-debug-collector
    spec:
      containers:
        - name: collector
          image: otel/opentelemetry-collector-contrib:0.148.0
          args: ["--config=/conf/config.yaml"]
          volumeMounts:
            - name: config
              mountPath: /conf
      volumes:
        - name: config
          configMap:
            name: audit-debug-collector
---
apiVersion: v1
kind: Service
metadata:
  name: audit-debug-collector
  namespace: agentregistry-system
spec:
  selector:
    app: audit-debug-collector
  ports:
    - name: otlp-grpc
      port: 4317
EOF
```

Verify it comes up:

```bash
kubectl get pods -n agentregistry-system | grep debug
```

```
audit-debug-collector-77c4bf9964-mt6h2   1/1   Running   0   30s
```

## 2. Enable Audit on the Registry

Audit is disabled by default. Enable it by upgrading the release with the `audit.*` values.
`--reuse-values` keeps everything already set on your install (OIDC, ClickHouse, telemetry, image
tag) and merges in only the audit settings, so there's no values file to hand-maintain. The
endpoint points at the debug collector's in-cluster Service:

```bash
helm upgrade agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.7.0 \
  --namespace agentregistry-system \
  --reuse-values \
  --set audit.enabled=true \
  --set-string audit.destination.otlp.endpoint=audit-debug-collector.agentregistry-system.svc.cluster.local:4317 \
  --set audit.destination.otlp.insecure=true \
  --wait --timeout 5m
```

> `--reuse-values` reuses the values from your **current** release, which is what you want at a
> fixed `2026.7.0` baseline. One caveat: if you enable audit *and* bump the chart version in the
> same command, `--reuse-values` won't pull in the new version's defaults. Bump first, then enable
> audit.

The server restarts to pick up the new config. Wait for it, then confirm it's ready:

```bash
kubectl rollout status deployment/agentregistry-enterprise-server -n agentregistry-system
```

## 3. Generate an Event

Any catalog change now emits a `lifecycle` event. Create a throwaway `AccessPolicy`, the same
resource kind from the [AccessPolicy lab](access-policies.md):

```bash
arctl apply -f- <<EOF
apiVersion: ar.dev/v1alpha1
kind: AccessPolicy
metadata:
  name: audit-test
spec:
  principals:
    - kind: Role
      name: are-readers
  rules:
    - actions:
        - "registry:read"
      resources:
        - kind: agent
          name: "*"
EOF
```

## 4. Read the Audit Event

Tail the collector and filter for the **lifecycle** event you triggered. Filter on
`agentregistry.audit.lifecycle`, not the bare `agentregistry.audit` prefix: if you deployed MCP
servers or agents in earlier labs, the registry keeps reconciling them and emits `system`
`applied_resource` events that bury your record.

```bash
kubectl logs deployment/audit-debug-collector -n agentregistry-system --since=10m \
  | grep -A 15 'EventName: agentregistry.audit.lifecycle'
```

The `debug` exporter prints each record in OpenTelemetry's field format (not JSON). You'll see the
`create` event for the `audit-test` policy, similar to:

```
EventName: agentregistry.audit.lifecycle
Attributes:
     -> event.name: Str(agentregistry.audit.lifecycle)
     -> event.schema_version: Str(v1)
     -> event.activity: Str(lifecycle)
     -> event.action: Str(create)
     -> actor.subject: Str(f4f46a76-0e4a-452a-b62d-3650fa72248d)
     -> actor.type: Str(user)
     -> actor.roles: Slice(["are-admins"])
     -> actor.email: Str(admin@example.com)
     -> actor.name: Str(admin user)
     -> resource.kind: Str(AccessPolicy)
     -> resource.namespace: Str(default)
     -> resource.name: Str(audit-test)
```

That field format is how the local `debug` exporter renders logs to `stdout`. Delivered over OTLP
to a real audit backend, the same event arrives as a structured record: the `scope`
(`audit.resource_activity`) and every attribute above map to the fields your SIEM ingests and
indexes.

If nothing shows up, confirm the server rollout finished (step 2), then trigger the event again.
`arctl delete accesspolicy audit-test` followed by re-applying it emits a `delete` then a `create`.

## The Event Schema

Every audit record carries these key fields:

| Field | Purpose |
|---|---|
| `event.name` | SIEM-friendly event identifier (e.g. `agentregistry.audit.lifecycle`) |
| `event.activity` | Category: `lifecycle`, `approval`, `authorization`, `applied_resource` |
| `event.action` | Specific action: `create`, `update`, `delete`, `submit`, `approve`, `read`, … |
| `actor.*` | Who acted: `subject` (OIDC sub), `email`, `name`, `type`, and `roles` |
| `resource.*` | What was affected: `kind`, `namespace`, `name` |
| `log.record.uid` | Unique record ID for downstream deduplication |

> **Want to see authorization events too?** The `audit.authz` scope emits *successful* allows only
> when you opt in. Re-run the step 2 upgrade with `--set audit.authz.allowedDecisions=all`. Options:
> `sensitive` (default: successful reads of sensitive resources only), `all` (every successful
> allow), and `none`. Denials and errors always emit.

## Cleanup

```bash
# Remove the test policy
arctl delete accesspolicy audit-test 2>/dev/null || true

# Remove the debug collector
kubectl delete deployment,service,configmap audit-debug-collector -n agentregistry-system \
  --ignore-not-found
```

To turn audit off again, re-run the upgrade with `--reuse-values --set audit.enabled=false`:

```bash
helm upgrade agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.7.0 \
  --namespace agentregistry-system \
  --reuse-values \
  --set audit.enabled=false \
  --wait --timeout 5m
```

## Going to Production

The debug collector is stdout-only and drops events on restart, which is fine for a lab. In
production, set `audit.collector.enabled=true` to deploy the **bundled relay collector**: it buffers
events in a persistent write-ahead log and forwards them to your own OTLP-compatible audit platform
(Splunk, Microsoft Sentinel, Loki, OpenSearch, …) with retry and backoff, so you lose nothing if the
backend goes down. Point `audit.destination.otlp.endpoint` at your SIEM instead of the debug
collector. See the
[production audit setup](https://docs.solo.io/agentregistry/latest/observability/audit-logging/#production)
in the docs.

## Next

- [Approval Workflows](approval-workflows.md) — gate submissions behind admin approval (each
  approve/reject you make here shows up as an `approval` audit event)
