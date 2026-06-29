# Image list for Enterprise Agentregistry

Every artifact the baseline pulls. Mirror all of these into your private registry / internal artifact
host before running the [air-gap install lab](airgap/001-airgap.md). Tags below are the validated
companions for **Agentregistry Enterprise `v2026.6.2`** + **Enterprise Agentgateway `v2026.6.1`**.

> **Mirror it automatically:** [`mirror-images.sh`](mirror-images.sh) copies every image and chart
> below into your registry (default `docker.io/ably7`) with `docker buildx imagetools create` (full
> multi-arch). To update, bump the version vars and re-run. The ARE-family image tags (server,
> ClickHouse, Postgres, OTel) are discovered by rendering the chart, so they stay correct across
> version bumps.

## CLI + backend binaries (internal artifact host)

The `arctl` CLI and the server's managed-backend binaries are **not** container images — they are
downloaded over HTTP from `storage.googleapis.com`. A container registry (Docker Hub included) only
serves OCI artifacts, so **these cannot be mirrored to your image registry** — you must host them on
your own HTTP/object server (S3/GCS bucket, Nginx, Artifactory, …) and set `global.binaryHost` /
`global.binaryBucket` to it; paths resolve as `<host>/<bucket>/<version>/<name>`.

> **What to do:** `./mirror-images.sh --binaries-dir ./binaries` downloads everything below into
> `./binaries/<version>/`; upload that directory to your host. On a **connected** cluster you may skip
> this and leave `global.binaryHost=https://storage.googleapis.com` — then these binaries are the only
> outbound dependency left after the images + charts are mirrored.

### `arctl` CLI

```bash
# install.sh resolves to this layout (plus a .sha256 sibling for each binary):
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/arctl-linux-amd64
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/arctl-linux-arm64
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/arctl-darwin-amd64
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/arctl-darwin-arm64
```

### Managed-backend binaries (downloaded by the server pod)

```bash
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/agw-sync
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/agentgateway
https://storage.googleapis.com/agentregistry-enterprise/v2026.6.2/agentregistry-sts
```

## Helm Charts

### Agentregistry Enterprise

```bash
helm pull oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise --version 2026.6.2
```

### Enterprise Agentgateway CRDs + chart

```bash
helm pull oci://us-docker.pkg.dev/solo-public/enterprise-agentgateway/charts/enterprise-agentgateway-crds --version v2026.6.1
helm pull oci://us-docker.pkg.dev/solo-public/enterprise-agentgateway/charts/enterprise-agentgateway --version v2026.6.1
```

## Images

### OIDC — Keycloak

```bash
quay.io/keycloak/keycloak:26.0
```

### Agentregistry Enterprise (chart `2026.6.2`)

```bash
# server (image.registry/repository/name/tag)
us-docker.pkg.dev/solo-public/agentregistry-enterprise/server:v2026.6.2
# bundled PostgreSQL (dev/eval)
docker.io/library/postgres:18
# ClickHouse (tag defaults to the subchart appVersion when left empty; this is the v2026.6.2 companion)
docker.io/clickhouse/clickhouse-server:26.2.5-alpine
# OpenTelemetry collector
docker.io/otel/opentelemetry-collector-contrib:0.148.0
```

### Enterprise Agentgateway (chart `v2026.6.1`)

```bash
us-docker.pkg.dev/solo-public/enterprise-agentgateway/enterprise-agentgateway-controller:2026.6.1
us-docker.pkg.dev/solo-public/enterprise-agentgateway/agentgateway-enterprise:2026.6.1
```

> The shared extensions (`ext-auth-service`, `rate-limiter`, `ext-cache`/`redis`) are also published
> under `us-docker.pkg.dev/solo-public/enterprise-agentgateway/<name>:2026.6.1`, but this workshop
> doesn't enable them, so they aren't part of the baseline mirror. Add them if you turn them on.

> **Third-party MCP images:** the MCP labs that self-host a server in-cluster (e.g. the arXiv / FRED /
> demo MCPs) pull their own public images. Mirror those too if you intend to run those labs air-gapped.
