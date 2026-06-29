# Ably7 Mirrored Image List

The [canonical image list](../image-list.md) mirrored to `docker.io/ably7` — a **public Docker Hub repo
that really hosts these images** (populated by [`mirror-images.sh`](../mirror-images.sh)), standing in
for the private registry you'd use in a real air-gap. Swap `ably7` for your own. These are the exact
references the [air-gap install lab](001-airgap.md) pulls.

> Regenerate / update with: `cd labs/installation && ./mirror-images.sh`
> (bump `ARE_VERSION` / `AGW_VERSION` to move to a new release).

## CLI + backend binaries (internal artifact host)

Not container images — mirror the bucket layout `<host>/<bucket>/<version>/<name>` to your internal
artifact host (the lab uses `http://artifacts.internal.example.com` as a stand-in):

```
http://artifacts.internal.example.com/agentregistry-enterprise/v2026.6.2/arctl-linux-amd64   (+ .sha256)
http://artifacts.internal.example.com/agentregistry-enterprise/v2026.6.2/agw-sync
http://artifacts.internal.example.com/agentregistry-enterprise/v2026.6.2/agentgateway
http://artifacts.internal.example.com/agentregistry-enterprise/v2026.6.2/agentregistry-sts
```

## Helm charts (OCI)

Docker Hub uses a flat `namespace/repo` layout, so charts mirror to top-level repos (no `/helm/` or
`/charts/` path segment):

```
oci://docker.io/ably7/agentregistry-enterprise:2026.6.2
oci://docker.io/ably7/enterprise-agentgateway-crds:v2026.6.1
oci://docker.io/ably7/enterprise-agentgateway:v2026.6.1
```

## OIDC — Keycloak

```
docker.io/ably7/keycloak:26.0
```

## Agentregistry Enterprise (2026.6.2)

### server
```
docker.io/ably7/server:v2026.6.2
```

### bundled PostgreSQL
```
docker.io/ably7/postgres:18
```

### ClickHouse
```
docker.io/ably7/clickhouse-server:26.2.5-alpine
```

### OpenTelemetry collector
```
docker.io/ably7/opentelemetry-collector-contrib:0.148.0
```

## Enterprise Agentgateway (v2026.6.1)

### controller
```
docker.io/ably7/enterprise-agentgateway-controller:2026.6.1
```

### agentgateway proxy
```
docker.io/ably7/agentgateway-enterprise:2026.6.1
```

> Shared extensions (`ext-auth-service`, `rate-limiter`, `redis`) are not enabled by this workshop, so
> they aren't mirrored here. Enable them on a Gateway? Add them to `mirror-images.sh` and re-run.
