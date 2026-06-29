# Install Enterprise Agentregistry (Air-Gap / Private Registry)

This is the air-gapped twin of [`001-installation.md`](../../../001-installation.md). It takes you from a
bare Kubernetes cluster to the same working **Solo.io Enterprise Agentregistry** baseline — the
`arctl` CLI, an in-cluster OIDC provider (Keycloak), the Agentregistry control plane + catalog, and
Enterprise Agentgateway — but with **every image and binary pulled from a private registry / internal
artifact host** instead of the public Solo, Docker Hub, Quay, and `storage.googleapis.com` endpoints.

> [!IMPORTANT]
> **Air-gap has two mirror surfaces, on two different hosts.** This lab fills both with stand-ins —
> swap each for your own to reproduce a true air-gap. Full artifact list:
> [canonical image list](../image-list.md) · [mirrored-tag view](ably7-image-list.md).
>
> | Surface | What | Stand-in → your host | How |
> |---|---|---|---|
> | **Container images + Helm charts** | Keycloak, ARE server, Postgres, ClickHouse, OTel, Agentgateway controller + proxy; the 3 OCI charts | `docker.io/ably7` → your **private container registry** | [`mirror-images.sh`](../mirror-images.sh) pushes all of them |
> | **CLI + backend binaries** | `arctl`, and the `agw-sync` / `agentgateway` / `agentregistry-sts` the server downloads at runtime | `http://artifacts.internal.example.com` → an **HTTP/object host you provide** (NOT the container registry) | `mirror-images.sh --binaries-dir DIR` downloads them; you upload `DIR` |
>
> **Why two hosts:** binaries are plain HTTP-served files, and a container registry (Docker Hub
> included) only serves OCI artifacts — they can't live next to the images. The server fetches them at
> runtime via `global.binaryHost`; if it's unreachable the server pod starts but its managed gateway
> backends never come up.
>
> **What you must do:** point `BINARY_HOST` (below) at your host. On a **connected** cluster you may
> instead leave `BINARY_HOST=https://storage.googleapis.com` — then the binaries are the single
> remaining outbound dependency (images + charts still come from your registry). A true air-gap
> requires your own host.

## Lab Objectives

- Confirm cluster prerequisites (Kubernetes ≥ 1.29, default `StorageClass`, working `LoadBalancer`)
- Install the `arctl` CLI **from a mirrored artifact host** (no `storage.googleapis.com` at runtime)
- Stand up Keycloak in-cluster from a **mirrored image** and configure the `agentregistry-enterprise` realm
- Install Agentregistry Enterprise with **all images and backend binaries pointed at private mirrors**
- Install Enterprise Agentgateway with a **single `image.registry` override** covering every chart-managed image
- Log in with `arctl` and confirm your admin user is recognized

## Pre-requisites

- A running Kubernetes cluster (≥ 1.29) with a default `StorageClass` and a `LoadBalancer`-capable Service controller (managed clusters: yes; bare-metal: MetalLB/kube-vip; `kind`: `cloud-provider-kind`)
- `kubectl`, `helm` v3, `openssl`, `envsubst`, `jq`
- A **Solo trial license key**. Get one free at [solo.io](https://www.solo.io/) or from your Solo account team. Export it as `SOLO_TRIAL_LICENSE_KEY` — the same trial key works for Enterprise Agentgateway.
- A **private container registry** reachable from the cluster, pre-loaded with the [image list](../image-list.md), and an **internal artifact host** serving the `arctl` CLI and backend binaries.

### Configure air-gap variables

Set these once; every step below reads from them. Swap the placeholders for your real mirrors.

```bash
export SOLO_TRIAL_LICENSE_KEY=$SOLO_TRIAL_LICENSE_KEY

# --- Private container registry (stand-in: docker.io/ably7) ---
export PRIVATE_REGISTRY=docker.io/ably7

# --- Internal artifact host that mirrors storage.googleapis.com ---
# For a connected demo cluster you can leave this as the public host;
# in a true air-gap it must be your own mirror.
export BINARY_HOST=http://artifacts.internal.example.com
export BINARY_BUCKET=agentregistry-enterprise

# --- Pinned versions (match what you mirrored) ---
export ARCTL_VERSION=v2026.6.2
export ARE_VERSION=2026.6.2            # Agentregistry Enterprise chart + image
export ENTERPRISE_AGW_VERSION=v2026.6.1

# --- Optional: name of a pull Secret you created in each namespace ---
# export IMAGE_PULL_SECRET=my-registry-secret
```

> **Pull secrets:** if your private registry requires auth, create an `imagePullSecret` in **each**
> namespace the workload lands in (`keycloak`, `agentregistry-system`, `agentgateway-system`) and
> uncomment the `imagePullSecrets` lines flagged in each step:
> ```bash
> kubectl create namespace agentregistry-system 2>/dev/null || true
> kubectl create secret docker-registry my-registry-secret \
>   --docker-server=docker.io --docker-username=<user> --docker-password=<token> \
>   -n agentregistry-system
> # repeat for the keycloak and agentgateway-system namespaces
> ```

---

## 1. Confirm the Cluster

Same as the connected install — no images pulled yet.

```bash
kubectl get nodes
kubectl get storageclass
```

You need at least one `StorageClass` marked `(default)` — Agentregistry's bundled PostgreSQL and
ClickHouse both request PVs. If none is default:

```bash
kubectl annotate storageclass <name> storageclass.kubernetes.io/is-default-class=true
```

**Confirm a `LoadBalancer` Service can actually get an external address.** OIDC redirects and the
`arctl`/UI endpoints all depend on this, so test it now rather than discovering it later. Use a
mirrored image even for the smoke test so you don't accidentally reach Docker Hub:

```bash
kubectl create deployment lb-smoke --image=$PRIVATE_REGISTRY/nginx
kubectl expose deployment lb-smoke --port=80 --type=LoadBalancer
kubectl get svc lb-smoke -w
# Wait for EXTERNAL-IP to be populated (not <pending>), then Ctrl-C
kubectl delete deployment lb-smoke && kubectl delete svc lb-smoke
```

If `EXTERNAL-IP` stays `<pending>`, install/fix your LoadBalancer provider before continuing.

---

## 2. Install the `arctl` CLI (from your mirror)

The public installer (`curl … storage.googleapis.com/agentregistry-enterprise/install.sh | sh`) reaches
the internet at runtime, so it won't work in an air-gap. Instead, download the mirrored binary
directly. The CLI lives at `<host>/<bucket>/<version>/arctl-<os>-<arch>` (with a `.sha256` sibling) —
the same layout the public installer uses, so mirroring the bucket path 1:1 is all you need.

```bash
OS=$(uname -s | tr '[:upper:]' '[:lower:]'); [ "$OS" = "darwin" ] || OS=linux
ARCH=$([ "$(uname -m)" = "arm64" ] || [ "$(uname -m)" = "aarch64" ] && echo arm64 || echo amd64)

mkdir -p "$HOME/.arctl/bin"
curl -fsSL "$BINARY_HOST/$BINARY_BUCKET/$ARCTL_VERSION/arctl-$OS-$ARCH" -o "$HOME/.arctl/bin/arctl"
chmod +x "$HOME/.arctl/bin/arctl"

export PATH=$HOME/.arctl/bin:$PATH
echo 'export PATH="$HOME/.arctl/bin:$PATH"' >> ~/.zshrc   # adjust for bash/fish
```

Verify:

```bash
arctl version --json
```

Expected (server is empty until step 4 — that's fine):

```json
{
  "cli": {
    "version": "v2026.6.2",
    "git_commit": "...",
    "build_time": "..."
  }
}
```

---

## 3. Stand Up Keycloak (OIDC) from a mirrored image

The realm is **fully declarative** — see [`assets/keycloak/agentregistry-enterprise.json`](../../../assets/keycloak/agentregistry-enterprise.json),
which defines the `agentregistry-enterprise` realm, three groups (`are-admins` / `are-readers` /
`are-writers`), three users (`admin` / `reader` / `writer`, password = username), the two OIDC clients
(`are-backend` confidential, `are-cli` public + device-code), and the `groups` claim mapper on **both**
clients. Keycloak imports it on first boot (`--import-realm`).

The kustomize stack pins `quay.io/keycloak/keycloak:26.0`. To pull it from your private registry
instead, add a Kustomize `images:` transform to [`assets/keycloak/kustomization.yaml`](../../../assets/keycloak/kustomization.yaml)
— this rewrites the image without editing the Deployment:

```yaml
# Append to assets/keycloak/kustomization.yaml
images:
  - name: quay.io/keycloak/keycloak
    newName: docker.io/ably7/keycloak   # = $PRIVATE_REGISTRY/keycloak
    newTag: "26.0"
```

> If your registry needs a pull secret, add it to the Keycloak pod by patching the Deployment in the
> same kustomization (`patches:`) or by attaching the secret to the namespace's `default`
> ServiceAccount: `kubectl patch serviceaccount default -n keycloak -p '{"imagePullSecrets":[{"name":"my-registry-secret"}]}'`.

Apply the whole stack (Kustomize builds the realm ConfigMap from the JSON):

```bash
kubectl apply -k ../../../assets/keycloak/
kubectl rollout status deployment/keycloak -n keycloak
```

> **Why the `groups` mapper is on `are-cli` too:** `arctl` and the UI both log in through the public
> `are-cli` client. If the mapper only existed on `are-backend`, their token would carry no `groups`
> claim, the registry would resolve zero roles, and your `admin` user would never be a superuser. The
> realm JSON puts the mapper on both clients so admin works out of the box.

Wait for the LoadBalancer address, then capture it:

```bash
kubectl get svc keycloak -n keycloak -w
# Wait for EXTERNAL-IP, then Ctrl-C

export KC_IP=$(kubectl get svc keycloak -n keycloak \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
echo "Keycloak: http://${KC_IP}:8080  (admin / admin123)"
```

> **No hostname pinning needed.** Keycloak runs with `hostname-strict=false`, so it derives its issuer
> URL from the request host. Because `arctl`, the browser, and the in-cluster registry all reach
> Keycloak through this same `KC_IP`, the issuer stays consistent.

Write the OIDC variables the rest of the install (and every later lab) consumes. Every value except
the issuer is a constant baked into the realm JSON:

```bash
cat > ~/.are-keycloak-env <<EOF
export OIDC_PROVIDER=keycloak
export OIDC_ISSUER="http://${KC_IP}:8080/realms/agentregistry-enterprise"
export OIDC_BACKEND=are-backend
export OIDC_PUBLIC_CLIENT=are-cli
export ARE_CLI_CLIENT_ID=are-cli
export BACKEND_CLIENT_SECRET="aRe3nt3rpr1seWorkshopBackendSecret"
export GROUP_ADMINS="00000000-0000-0000-0000-00000000a001"
export GROUP_READERS="00000000-0000-0000-0000-00000000a002"
export GROUP_WRITERS="00000000-0000-0000-0000-00000000a003"
EOF
source ~/.are-keycloak-env
```

**Verify the `groups` claim is present on an `are-cli` token:**

```bash
curl -s -X POST "http://${KC_IP}:8080/realms/agentregistry-enterprise/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=are-cli \
  -d username=admin -d password=admin -d "scope=openid profile" \
  | jq -r .access_token | cut -d. -f2 \
  | base64 -d 2>/dev/null | jq '{preferred_username, groups}'
```

Expected (the claim is the plain group **name**, no `/` prefix):

```json
{
  "preferred_username": "admin",
  "groups": ["are-admins"]
}
```

| Username | Password | Group | Role |
|---|---|---|---|
| admin  | admin  | are-admins  | superuser |
| reader | reader | are-readers | read-only |
| writer | writer | are-writers | publish/edit |

---

## 4. Install Agentregistry Enterprise (images + binaries mirrored)

This is the step that differs most from the connected install. Two override surfaces:

1. **Container images** — the server, the bundled PostgreSQL, ClickHouse, and the OpenTelemetry
   collector. Each takes a `registry`/`repository`/`name`/`tag` (ClickHouse embeds the registry in
   `repository`).
2. **Backend binaries** — the server downloads `agw-sync`, `agentgateway`, and `agentregistry-sts` at
   runtime from `<global.binaryHost>/<global.binaryBucket>/<version>/<name>`. Point `global.binaryHost`
   / `global.binaryBucket` at your internal artifact host or these never download and the managed
   gateway backends never start.

```bash
cat > /tmp/are-values.yaml <<EOF
global:
  # --- Backend binary downloads (agw-sync, agentgateway, agentregistry-sts) ---
  binaryHost: "${BINARY_HOST}"
  binaryBucket: "${BINARY_BUCKET}"
  #--- Pull secret propagated to all subcharts (uncomment if your registry needs auth) ---
  #imagePullSecrets:
  #  - name: my-registry-secret

# --- Agentregistry Enterprise server image ---
image:
  registry: docker.io          # = host portion of \$PRIVATE_REGISTRY
  repository: ably7            # = org/path portion of \$PRIVATE_REGISTRY
  name: server
  tag: v${ARE_VERSION}
  pullPolicy: IfNotPresent

service:
  type: LoadBalancer

oidc:
  issuer: "${OIDC_ISSUER}"
  clientId: "${OIDC_BACKEND}"
  publicClientId: "${OIDC_PUBLIC_CLIENT}"
  clientSecret: "${BACKEND_CLIENT_SECRET}"
  roleClaim: "groups"
  superuserRole: "are-admins"
  insecureSkipVerify: false

database:
  postgres:
    type: bundled
    bundled:
      image:
        registry: docker.io
        repository: ably7
        name: postgres
        tag: "18"
        pullPolicy: IfNotPresent

clickhouse:
  enabled: true
  image:
    # ClickHouse embeds the registry in repository; pin the exact tag your mirror
    # holds (the chart's default empty tag resolves to the subchart appVersion).
    repository: docker.io/ably7/clickhouse-server
    tag: "26.2.5-alpine"

telemetry:
  enabled: true
  collector:
    image:
      repository: docker.io/ably7/opentelemetry-collector-contrib
      tag: "0.148.0"
      pullPolicy: IfNotPresent

extraEnvVars:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://agentregistry-enterprise-telemetry-collector:4317"
  - name: OTEL_SERVICE_NAME
    value: "agentregistry-enterprise"
EOF

helm upgrade --install agentregistry-enterprise \
  oci://${PRIVATE_REGISTRY}/agentregistry-enterprise \
  --version ${ARE_VERSION} \
  --namespace agentregistry-system --create-namespace \
  -f /tmp/are-values.yaml \
  --wait --timeout 5m
```

> **Chart source:** the OCI chart itself
> (`oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise`) must
> also be mirrored — [`mirror-images.sh`](../mirror-images.sh) does this with `helm pull` + `helm push`.
> Docker Hub uses a flat `namespace/repo` layout, so the chart lands at
> `oci://${PRIVATE_REGISTRY}/agentregistry-enterprise` (no `/helm/` segment). A deeper-path registry
> (Harbor/ECR/Artifactory/GAR) can keep the nested path. If you'd rather pull the chart from the public
> URL and override only images, swap the `oci://...` line for the public URL and keep the values above.

> **Confirm the binary downloads succeeded.** Unlike a missing image (which `CrashLoopBackOff`s
> loudly), a missing backend binary lets the server pod run but leaves managed gateway backends down.
> Check the logs for download errors against `$BINARY_HOST`:
> ```bash
> kubectl logs -n agentregistry-system deploy/agentregistry-enterprise-server | grep -i -E "download|binary|agw-sync|agentgateway|sts"
> ```

> **Re-running against an existing install?** On a fresh cluster, skip this. If the registry is already
> installed and you re-ran step 3 (so `BACKEND_CLIENT_SECRET`/`OIDC_ISSUER` changed), the running pod
> still holds the old value in memory — a `Secret` change alone doesn't restart it. Force a rollout:
> ```bash
> kubectl rollout restart deployment/agentregistry-enterprise-server -n agentregistry-system
> kubectl rollout status  deployment/agentregistry-enterprise-server -n agentregistry-system
> ```

Verify all pods are `1/1 Running`:

```bash
kubectl get pods -n agentregistry-system
```

Expected:

```
NAME                                                           READY   STATUS    RESTARTS   AGE
agentregistry-enterprise-clickhouse-shard0-0                   1/1     Running   0          90s
agentregistry-enterprise-postgresql-<hash>                     1/1     Running   0          90s
agentregistry-enterprise-server-<hash>                         1/1     Running   0          90s
agentregistry-enterprise-telemetry-collector-<hash>            1/1     Running   0          90s
```

**Confirm the pods are pulling from your mirror, not the public registries:**

```bash
kubectl get pods -n agentregistry-system \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}'
# every image should start with docker.io/ably7 (your $PRIVATE_REGISTRY)
```

Grab the external IP and point `arctl` at the server:

```bash
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
echo "Agentregistry API + UI: ${ARCTL_API_BASE_URL}"
```

---

## 5. Install Enterprise Agentgateway (single registry override)

Required for the MCP-through-gateway labs. A single top-level `image.registry` override covers the
chart-managed images this workshop uses — the controller and the agentgateway proxy (provisioned when
a Gateway is created). They inherit the registry and are pinned to the chart-version tag (`2026.6.1`),
matching the mirrored tags in [`ably7-image-list.md`](ably7-image-list.md).

> The chart can also auto-provision shared extensions (`ext-auth-service`, `rate-limiter`,
> `ext-cache`/`redis`), which inherit the same `image.registry`. This workshop doesn't enable them, so
> they aren't mirrored. If you turn them on, add their images to your mirror and the script's image list.

```bash
# Kubernetes Gateway API CRDs (mirror the manifest internally; it is plain YAML)
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/standard-install.yaml

# Agentgateway CRDs (mirror the OCI chart to your registry)
helm upgrade --install agentgateway-crds \
  oci://${PRIVATE_REGISTRY}/enterprise-agentgateway-crds \
  --version ${ENTERPRISE_AGW_VERSION} \
  --namespace agentgateway-system --create-namespace

# Agentgateway controller — one image.registry override covers the controller and the proxy
helm upgrade --install enterprise-agentgateway \
  oci://${PRIVATE_REGISTRY}/enterprise-agentgateway \
  --version ${ENTERPRISE_AGW_VERSION} \
  --namespace agentgateway-system \
  --set-string licensing.licenseKey="${SOLO_TRIAL_LICENSE_KEY}" \
  -f -<<EOF
# --- Point all chart-managed images at the private registry (air-gap) ---
# The top-level 'image' block is the GLOBAL default for the controller and the
# agentgateway proxy. The tag defaults to the chart version, so you normally do
# not set it here.
image:
  registry: ${PRIVATE_REGISTRY}
  pullPolicy: IfNotPresent
#imagePullSecrets:
#- name: my-registry-secret
EOF
```

Verify the controller is Ready:

```bash
kubectl get pods -n agentgateway-system
```

```
NAME                                       READY   STATUS    RESTARTS   AGE
enterprise-agentgateway-<hash>             1/1     Running   0          30s
```

---

## 6. Authenticate `arctl`

`arctl user login` uses the OIDC **device-authorization** flow: it prints a URL and a code, then waits.
It does **not** auto-open a browser. This flow only talks to your in-cluster Keycloak, so no internet
access is required.

```bash
arctl user login \
  --oidc-issuer-url "${OIDC_ISSUER}" \
  --oidc-client-id "${ARE_CLI_CLIENT_ID}"
```

You'll see:

```
To complete the login process, please:
    1. Open: http://<KC_IP>:8080/realms/agentregistry-enterprise/device
    2. Enter the code: XXXX-XXXX
Waiting for authentication...
```

Open that URL in a browser, enter the code, sign in as **`admin` / `admin`**, and approve. The CLI
prints `token stored in keychain successfully`.

> **Headless / CI login (no browser):** `arctl` also supports the non-interactive
> password-credentials flow against the same `are-cli` client — handy for automated validation:
> ```bash
> arctl user login --oidc-issuer-url "${OIDC_ISSUER}" --oidc-client-id "${ARE_CLI_CLIENT_ID}" \
>   --oidc-flow password-credentials --oidc-username admin --oidc-password admin
> ```

| 1. Sign in (`admin` / `admin`) | 2. Grant access | 3. Success |
|---|---|---|
| ![Keycloak sign-in](../../../assets/screenshots/01-keycloak-signin.png) | ![Grant access to are-cli](../../../assets/screenshots/02-keycloak-grant.png) | ![Device login success](../../../assets/screenshots/03-keycloak-success.png) |

Confirm the baseline works:

```bash
# 3 built-in runtimes ship out of the box
arctl get runtimes
```

```
NAME                 TYPE
kubernetes-default   Kubernetes
local                Local
virtual-default      Virtual
```

```bash
arctl version --json
```

The `server` block now populates, which confirms `arctl` is talking to the registry. (The server
reports its own build metadata — currently `dev`/`unknown` — rather than the chart version; what
matters is that the `server` object is present, not the exact string.)

```json
{ "cli": { "version": "v2026.6.2", ... }, "server": { "version": "dev", "git_commit": "unknown", ... } }
```

> **Confirm admin privileges.** Your `admin` user should be a superuser. The most reliable check is
> that admin-only listings succeed:
> ```bash
> arctl get accesspolicies   # should NOT 403 "registry admin required"
> ```
> If this 403s, the `groups` claim isn't reaching the registry. Re-check the `are-cli` token with the
> verification `curl` in step 3; if the claim is missing,
> `kubectl rollout restart deployment/keycloak -n keycloak` to re-import the realm, then
> `arctl user login` again.

---

## What's in Place After This Lab

| Component | Namespace | Image source | Role |
|---|---|---|---|
| `arctl` CLI | local | `$BINARY_HOST` mirror | Authenticated against your agentregistry server |
| Keycloak | `keycloak` | `$PRIVATE_REGISTRY/keycloak` | In-cluster OIDC (realm `agentregistry-enterprise`) |
| Agentregistry Enterprise | `agentregistry-system` | `$PRIVATE_REGISTRY` + `$BINARY_HOST` | Catalog + control plane |
| Enterprise Agentgateway | `agentgateway-system` | `$PRIVATE_REGISTRY` | MCP / LLM gateway |

Keep these running for every lab. The later labs pull no additional Solo images, but any **third-party
MCP images** you self-host (e.g. the in-cluster MCP labs) must also be mirrored to `$PRIVATE_REGISTRY`.

---

## Uninstall

```bash
helm uninstall enterprise-agentgateway -n agentgateway-system 2>/dev/null || true
helm uninstall agentgateway-crds       -n agentgateway-system 2>/dev/null || true
helm uninstall agentregistry-enterprise -n agentregistry-system 2>/dev/null || true
kubectl delete namespace agentgateway-system agentregistry-system keycloak --ignore-not-found
rm -f /tmp/are-values.yaml ~/.are-keycloak-env
# (Optional) remove the Gateway API CRDs if nothing else uses them:
# kubectl delete -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.0/standard-install.yaml
```

## Next

Start with the recommended first lab:

- [Solo Docs MCP through Agentgateway](../../mcp/solo-docs-mcp.md)
