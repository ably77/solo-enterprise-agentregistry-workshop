# Air-Gap Install Lab — Net-New User Run: UX Issues & Improvements

Running `labs/installation/airgap/001-airgap.md` end-to-end on a fresh 2-node cluster
(`cluster1`, k8s v1.33.5, `local-path` default StorageClass, cloud-provider-kind LoadBalancer),
as a net-new user. Using the documented connected-cluster path: `PRIVATE_REGISTRY=docker.io/ably7`,
`BINARY_HOST=https://storage.googleapis.com`.

Findings are ordered by the step where they surfaced. Severity: 🔴 blocker · 🟡 friction · 🔵 polish.

**Outcome:** the baseline came up fully working end-to-end — all pods `1/1 Running` from the mirror,
`arctl` authenticated as a superuser admin, 3 built-in runtimes listed. No blockers. The friction
below is about confidence and copy-paste correctness, not whether the install ultimately works.

| # | Step | Sev | Summary | Status |
|---|------|-----|---------|--------|
| 1.1 | 1 | 🟡 | LB smoke test pulls `docker.io/ably7/nginx`, which doesn't exist → `ErrImagePull` | ✅ fixed (Service-only test) |
| 1.2 | 1 | 🟡 | Mirror script called `mirror-images.sh` in 8 docs; real file was `mirror-images-to-private-repo.sh` → dead links | ✅ fixed (renamed to `mirror-images.sh`) |
| 3.1 | 3 | 🟡 | Air-gap edit mutates `assets/keycloak/kustomization.yaml` shared by connected install + e2e | ✅ fixed (`assets/keycloak-airgap/` overlay) |
| 4.1 | 4 | 🟡 | Helm NOTES says `port-forward svc/agentregistry-enterprise`; real Service is `…-server` | open (chart `NOTES.txt`, upstream) |
| 4.2 | 4 | 🟡 | ARE server logs a red `LICENSE ERROR` stacktrace; lab sends you into those logs with no warning | ✅ fixed (`licensing` added to values) |
| 4.3 | 4 | 🟡 | "Confirm binary downloads" grep returns nothing at baseline (binaries fetch lazily later) | ✅ fixed (moved to solo-docs-mcp lab) |

> **Fixes applied this session:** 1.1, 1.2, 3.1, 4.2, 4.3. Each was validated — overlay renders the
> mirrored image while the base stays on `quay.io`; the `licensing` block flips the server log to
> `VALID LICENSE` on a fresh pod. **4.1 is upstream** in the chart's `NOTES.txt`, so it's left open
> for an upstream issue.

---

## Step 1 — Confirm the Cluster

### 🟡 1.1 — LoadBalancer smoke test uses an image that isn't in the stand-in registry  ✅ FIXED

> **Resolved in this run.** Replaced the deployment+nginx smoke test with a bare `LoadBalancer`
> Service (`kubectl create service loadbalancer lb-smoke --tcp=80:80`) — the LB controller assigns
> an EXTERNAL-IP independently of backing pods, so no image is pulled and nothing needs mirroring.
> Verified on this cluster: IP `172.18.255.249` assigned in ~2s. See `001-airgap.md` §1.

The smoke test runs:

```bash
kubectl create deployment lb-smoke --image=$PRIVATE_REGISTRY/nginx
```

With the lab's stand-in `PRIVATE_REGISTRY=docker.io/ably7`, this resolves to
`docker.io/ably7/nginx:latest`, which **does not exist**:

```
Failed to pull image "docker.io/ably7/nginx": ... docker.io/ably7/nginx:latest: not found
```

The pod goes straight to `ErrImagePull` / `ImagePullBackOff`. The Service *does* still get an
`EXTERNAL-IP` (172.18.255.249), which is the actual thing the smoke test checks — but a net-new
user copy-pasting the lab verbatim sees a broken pod and has no way to know whether the LB test
"passed."

**Why it matters:** This is the very first command that pulls an image. Failing here erodes
confidence before the real install starts, and `nginx` is not in `image-list.md` / `ably7-image-list.md`
or `mirror-images.sh`, so the stand-in repo can never satisfy it.

**Suggested fixes (pick one):**
- Add `nginx` (or a tiny `pause`/`hello-world`) to `mirror-images.sh` + the image lists so
  `$PRIVATE_REGISTRY/nginx` actually resolves, **or**
- Change the smoke test to reuse an image already guaranteed in the mirror (e.g.
  `$PRIVATE_REGISTRY/keycloak:26.0`), **or**
- Drop the pod entirely and test LB allocation with a Service-only check, since the deployment's
  readiness is irrelevant to whether the LB controller assigns an external IP. Add a one-line note:
  "the pod image is unimportant — you're only checking that EXTERNAL-IP populates."

`$PRIVATE_REGISTRY/nginx` is referenced in exactly one place (`001-airgap.md:104`) and in none of
the image lists or the mirror script — so on the stand-in registry it can never resolve.

### 🟡 1.2 — Mirror script filename doesn't match what every doc calls it

The docs reference the mirror helper as **`mirror-images.sh`** in 8 spots — including clickable
links — across `README.md`, `image-list.md`, `ably7-image-list.md`, and `001-airgap.md`
(e.g. `[mirror-images.sh](../mirror-images.sh)`, `./mirror-images.sh --binaries-dir ./binaries`).

The actual file on disk is **`mirror-images-to-private-repo.sh`**. Consequences:
- Every `[mirror-images.sh](...)` markdown link **404s on GitHub**.
- Every copy-paste `./mirror-images.sh ...` command fails with "No such file or directory".
- Only `CHANGELOG.md` references the real filename.

This is upstream of the whole air-gap flow: a real air-gap user's *first* action is running the
mirror script, and they can't find it from any link or command in the lab.

**Suggested fix:** rename the file to `mirror-images.sh` (matches all docs + the README repo-layout
diagram), or update all 8 references to `mirror-images-to-private-repo.sh`. The former is far less
churn and matches the name users already expect.

---

## Step 2 — Install `arctl` (from your mirror)

No issues. `arctl-darwin-arm64` downloaded from `https://storage.googleapis.com/...` and
`arctl version --json` reported `v2026.6.2` cleanly.

---

## Step 3 — Stand Up Keycloak

Happy path worked: Kustomize `images:` override pulled `docker.io/ably7/keycloak:26.0`, realm
imported, LB IP assigned (172.18.255.252), and the `groups: ["are-admins"]` claim verified on an
`are-cli` token on the first try. One footgun, though:

### 🟡 3.1 — Air-gap edit mutates a kustomization shared with the connected install + e2e test

Step 3 instructs: *"Append to assets/keycloak/kustomization.yaml"* an `images:` transform
repointing Keycloak to `docker.io/ably7/keycloak`. But that exact file is **also** applied by:

- `001-installation.md:103` — the **connected** install (`kubectl apply -k assets/keycloak/`), which
  expects the default `quay.io/keycloak/keycloak:26.0` and pins no image, and
- `e2e-test.sh:150` — `kubectl apply -k assets/keycloak/ ...`

So a user who follows the air-gap lab and commits / keeps the edit silently repoints the connected
install and the e2e test at `docker.io/ably7` too. Conversely, anyone running the air-gap lab from
a clean checkout has to remember to undo the edit afterward. Editing a shared source file in place
is fragile.

**Suggested fix:** make the air-gap override non-destructive to the shared file — e.g. ship a
separate `assets/keycloak/kustomization.airgap.yaml` (or an overlay dir
`assets/keycloak/overlays/airgap/`) that does `resources: [../..]` + the `images:` transform, and
have the lab `kubectl apply -k` *that* path instead of mutating the base. Then the connected lab and
e2e test keep using the unmodified base.

> Note: I reverted my own append to `kustomization.yaml` after this run so the repo isn't left in
> the silently-repointed state. The running Keycloak in-cluster is unaffected (it no longer depends
> on the file).

---

## Step 5 — Install Enterprise Agentgateway

No issues. Gateway API CRDs applied server-side, both OCI charts installed from the mirror, and the
controller came up `1/1 Running` with image `docker.io/ably7/enterprise-agentgateway-controller:2026.6.1`.
The single `image.registry` override worked as described.

---

## Step 6 — Authenticate `arctl`

No issues. Used the documented headless `--oidc-flow password-credentials` path (no browser
available); it printed `token stored successfully` and all three confirmations passed:

- `arctl get runtimes` → `kubernetes-default`, `local`, `virtual-default`
- `arctl version --json` → `server` block present (`version: dev`, as the lab predicts)
- `arctl get accesspolicies` → `No accesspolicies found.` (not a 403 → admin/superuser confirmed)

🔵 Minor: the lab's device-flow section says success prints `token stored in keychain successfully`;
the password-credentials flow prints `token stored successfully` (no "in keychain"). Harmless, but
the two strings differ if anyone greps for the exact message in automation.

---

## Final cluster state

```
keycloak/                 keycloak 1/1                         docker.io/ably7/keycloak:26.0
agentregistry-system/     server, postgres, clickhouse, otel   all 1/1, all docker.io/ably7/*
agentgateway-system/      enterprise-agentgateway 1/1          docker.io/ably7/...-controller:2026.6.1
arctl                     authenticated as admin (superuser)   v2026.6.2
```

Every image resolved to the `docker.io/ably7` mirror — the air-gap image-override story holds up.
The remaining open items are documentation/packaging fixes, not install blockers.

---

## Step 4 — Install Agentregistry Enterprise

All four pods came up `1/1 Running` and every image resolved to `docker.io/ably7` as intended.
The server LB got 172.18.255.251 and `/openapi.json` returns HTTP 200. But three things will
confuse a net-new user:

### 🟡 4.1 — Helm NOTES tells you to port-forward a Service that doesn't exist

The chart's post-install NOTES (printed right after `helm install`) says:

```
kubectl -n agentregistry-system port-forward svc/agentregistry-enterprise 12121:12121
```

But the Service is actually named **`agentregistry-enterprise-server`**:

```
$ kubectl get svc agentregistry-enterprise -n agentregistry-system
Error from server (NotFound): services "agentregistry-enterprise" not found
```

A user who copy-pastes the helm output (the most natural next action) gets a `NotFound`. The lab
body itself correctly uses `agentregistry-enterprise-server`, so this is a **chart `NOTES.txt`
bug**, not a lab bug — but it directly hits workshop users.

**Suggested fix:** file upstream against the chart to fix `NOTES.txt`. In the lab, optionally add a
one-liner: "the chart's NOTES print `svc/agentregistry-enterprise`; the real Service is
`agentregistry-enterprise-server` — use that."

### 🟡 4.2 — ARE server logs a `LICENSE ERROR` stacktrace, and the lab tells you to read these logs

Step 4 configures **no license** for Agentregistry Enterprise (only Agentgateway in Step 5 takes
`SOLO_TRIAL_LICENSE_KEY`). At startup the ARE server logs:

```
level=error msg="LICENSE ERROR: no licenses found"  ...stacktrace...
level=warn  msg="license status evaluated" valid=false message="agentregistry enterprise license missing or invalid"
```

The server is nonetheless fully functional (Ready 1/1, `/openapi.json` → 200, admin works in
Step 6). The problem is **Step 4 explicitly directs the user into these logs** to verify binary
downloads — so the first thing they see is a red `LICENSE ERROR` with a Go stacktrace, with no
note that it's expected. Net-new users will reasonably think the install is broken.

**Suggested fix:** add a note to Step 4 — "the ARE server logs a benign `LICENSE ERROR: no
licenses found` at startup; the trial/eval baseline does not require an ARE license and the server
runs normally." Or, if ARE *should* carry the trial license, add `licensing.licenseKey` to the
values block so the log is clean.

### 🟡 4.3 — The "confirm the binary downloads succeeded" check surfaces nothing at baseline

Step 4's callout says to run:

```bash
kubectl logs -n agentregistry-system deploy/agentregistry-enterprise-server | grep -i -E "download|binary|agw-sync|agentgateway|sts"
```

On a fresh baseline this returns **only** noise like `"started agentgateway executor"` — there are
no `download` / `agw-sync` / `agentregistry-sts` log lines at all, because the managed-backend
binaries aren't fetched until a Gateway/backend is actually provisioned (the later MCP labs). So
the check the lab frames as "confirm the binaries downloaded" can neither confirm nor deny anything
at this point — a careful user greps, sees nothing matching, and can't tell if that's good or bad.

**Suggested fix:** either move this verification to the first lab that provisions a managed backend
(where a real download log line exists), or reword it: "at baseline no backend binaries have
downloaded yet — they fetch lazily when you create your first Gateway. You'll verify this in the
MCP labs." If there's a deterministic startup-time signal that `global.binaryHost` is reachable,
grep for that instead.
