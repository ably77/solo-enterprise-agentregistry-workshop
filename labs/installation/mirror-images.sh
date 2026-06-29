#!/usr/bin/env bash
#
# mirror-images.sh — mirror every Enterprise Agentregistry baseline artifact into a
# private container registry (default: docker.io/ably7) for the air-gap install lab.
#
# WHAT IT MIRRORS
#   • Container images  : Keycloak, ARE server, bundled Postgres, ClickHouse, OTel
#                         collector, and the Agentgateway controller + runtime-provisioned
#                         proxy (agentgateway-enterprise).
#   • Helm charts (OCI) : agentregistry-enterprise, enterprise-agentgateway-crds,
#                         enterprise-agentgateway.
#
# This workshop does not enable the Agentgateway shared extensions (ext-auth-service,
# rate-limiter, ext-cache/redis), so they are NOT mirrored. If you enable them, add their
# images (us-docker.pkg.dev/solo-public/enterprise-agentgateway/<name>:$AGW_TAG) to AGW_REPOS.
#
# The ARE-family image set is DISCOVERED by rendering the chart, so ClickHouse / OTel /
# Postgres / server tags stay correct automatically when you bump ARE_VERSION. The
# Agentgateway proxy is provisioned by the controller at runtime (not in the chart
# templates), so it is listed explicitly and pinned to AGW_VERSION.
#
# WHAT IT CANNOT MIRROR (Docker Hub limitation)
#   The arctl CLI and the server's managed-backend binaries (agw-sync, agentgateway,
#   agentregistry-sts) are HTTP-served, not container images — Docker Hub can't host them.
#   Use --binaries-dir DIR to download them locally so you can serve them from your own
#   internal artifact host (the air-gap lab's BINARY_HOST). See image-list.md.
#
# UPDATE TO LATEST
#   Bump the version variables below (or pass them as env), then re-run:
#     ARE_VERSION=2026.7.0 AGW_VERSION=v2026.7.0 ./mirror-images.sh
#   Run with --print-latest-arctl to see the newest published arctl version.
#
# USAGE
#   ./mirror-images.sh [--dry-run] [--no-charts] [--images-only]
#                      [--binaries-dir DIR] [--print-latest-arctl]
#   DEST_REGISTRY=docker.io/myorg ./mirror-images.sh
#
# REQUIREMENTS
#   docker (with buildx), helm v3, curl. You must be logged in to the destination
#   registry:  docker login   (and, if helm push fails, `helm registry login docker.io`).
#
set -euo pipefail

# ---- Configuration (override via env) ---------------------------------------
DEST_REGISTRY="${DEST_REGISTRY:-docker.io/ably7}"
ARE_VERSION="${ARE_VERSION:-2026.6.2}"          # Agentregistry Enterprise chart version
AGW_VERSION="${AGW_VERSION:-v2026.6.1}"         # Enterprise Agentgateway chart version
KEYCLOAK_VERSION="${KEYCLOAK_VERSION:-26.0}"

# Public source registries / chart locations
ARE_CHART="oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise"
AGW_REPO="us-docker.pkg.dev/solo-public/enterprise-agentgateway"
AGW_CRDS_CHART="oci://${AGW_REPO}/charts/enterprise-agentgateway-crds"
AGW_CHART="oci://${AGW_REPO}/charts/enterprise-agentgateway"
KEYCLOAK_IMAGE="quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}"
BINARY_HOST_SRC="https://storage.googleapis.com"
BINARY_BUCKET="agentregistry-enterprise"

# ---- Flags ------------------------------------------------------------------
DRY_RUN=false
MIRROR_CHARTS=true
MIRROR_IMAGES=true
BINARIES_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)             DRY_RUN=true ;;
    --no-charts)           MIRROR_CHARTS=false ;;
    --images-only)         MIRROR_CHARTS=false ;;
    --charts-only)         MIRROR_IMAGES=false ;;
    --binaries-dir)        BINARIES_DIR="${2:?--binaries-dir needs a path}"; shift ;;
    --print-latest-arctl)
        curl -fsSL "${BINARY_HOST_SRC}/${BINARY_BUCKET}/releases.txt" | grep -Ev '\-' | tail -1
        exit 0 ;;
    -h|--help)             sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

AGW_TAG="${AGW_VERSION#v}"          # image tags drop the leading 'v'
RETRIES="${RETRIES:-4}"             # attempts per artifact (Docker Hub blob PUTs can be flaky)
FAILURES=()
log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
run()  { if $DRY_RUN; then echo "    [dry-run] $*"; else eval "$@"; fi; }

# Retry a command with backoff; returns non-zero after RETRIES failures.
retry() {
  local n=1
  until "$@"; do
    if [ "$n" -ge "$RETRIES" ]; then return 1; fi
    echo "    attempt $n failed; retrying in $((n*5))s..." >&2
    sleep $((n*5)); n=$((n+1))
  done
}

# dest image name = DEST_REGISTRY/<last path segment of repo>:<tag>
dest_for() { local s="$1"; printf '%s/%s:%s' "$DEST_REGISTRY" "$(basename "${s%:*}")" "${s##*:}"; }

mirror_image() {
  local src="$1" dst; dst="$(dest_for "$src")"
  log "image  $src"
  echo "        -> $dst"
  $DRY_RUN && { echo "    [dry-run] docker buildx imagetools create --tag $dst $src"; return 0; }
  if ! retry docker buildx imagetools create --tag "$dst" "$src"; then
    echo "    !! FAILED after ${RETRIES} attempts: $dst" >&2; FAILURES+=("image $dst")
  fi
}

mirror_chart() {
  local oci="$1" version="$2" tmp; tmp="$(mktemp -d)"
  log "chart  $oci ($version)"
  if $DRY_RUN; then
    echo "    [dry-run] helm pull $oci --version $version && helm push -> oci://${DEST_REGISTRY}/<chart>:$version"
    rm -rf "$tmp"; return 0
  fi
  if retry helm pull "$oci" --version "$version" -d "$tmp"; then
    local tgz; tgz="$(ls "$tmp"/*.tgz)"
    echo "        -> oci://${DEST_REGISTRY}/$(basename "$tgz" | sed -E 's/-[0-9].*//')"
    retry helm push "$tgz" "oci://${DEST_REGISTRY}" || { echo "    !! push FAILED: $oci" >&2; FAILURES+=("chart $oci"); }
  else
    echo "    !! pull FAILED: $oci" >&2; FAILURES+=("chart $oci")
  fi
  rm -rf "$tmp"
}

# ---- Discover the ARE-family images by rendering the chart ------------------
discover_are_images() {
  helm template are "$ARE_CHART" --version "$ARE_VERSION" \
      --set database.postgres.type=bundled \
      --set clickhouse.enabled=true --set telemetry.enabled=true \
      --set oidc.issuer=http://x --set oidc.clientId=x --set oidc.publicClientId=x 2>/dev/null \
    | awk '/[[:space:]]image:[[:space:]]/ {gsub(/"/,"",$2); print $2}' | sort -u
}

# ---- Build the full image list ----------------------------------------------
log "Resolving image set (ARE ${ARE_VERSION}, AGW ${AGW_VERSION}, Keycloak ${KEYCLOAK_VERSION})"
IMAGES=()
while IFS= read -r img; do [ -n "$img" ] && IMAGES+=("$img"); done < <(discover_are_images)
# Agentgateway controller + runtime-provisioned proxy (not in chart templates).
# Shared extensions (ext-auth-service, rate-limiter, redis) are not used by this
# workshop; add them here if you enable sharedExtensions on a Gateway.
AGW_REPOS="enterprise-agentgateway-controller agentgateway-enterprise"
for repo in $AGW_REPOS; do
  IMAGES+=("${AGW_REPO}/${repo}:${AGW_TAG}")
done
IMAGES+=("$KEYCLOAK_IMAGE")

echo
log "Will mirror ${#IMAGES[@]} images to ${DEST_REGISTRY}:"
for i in "${IMAGES[@]}"; do echo "    $i  ->  $(dest_for "$i")"; done
echo

# ---- Mirror images ----------------------------------------------------------
if $MIRROR_IMAGES; then
  for i in "${IMAGES[@]}"; do mirror_image "$i"; done
fi

# ---- Mirror charts ----------------------------------------------------------
if $MIRROR_CHARTS; then
  echo
  mirror_chart "$ARE_CHART"      "$ARE_VERSION"
  mirror_chart "$AGW_CRDS_CHART" "$AGW_VERSION"
  mirror_chart "$AGW_CHART"      "$AGW_VERSION"
fi

# ---- Optionally download backend binaries (cannot live on Docker Hub) -------
if [ -n "$BINARIES_DIR" ]; then
  echo
  log "Downloading CLI + backend binaries to ${BINARIES_DIR} (host these on your internal artifact server)"
  mkdir -p "$BINARIES_DIR/$ARE_VERSION"
  for f in arctl-linux-amd64 arctl-linux-arm64 arctl-darwin-amd64 arctl-darwin-arm64 \
           agw-sync agentgateway agentregistry-sts; do
    url="${BINARY_HOST_SRC}/${BINARY_BUCKET}/v${ARE_VERSION#v}/${f}"
    echo "    $url"
    run curl -fsSL "$url" -o "$BINARIES_DIR/$ARE_VERSION/$f" '||' echo "      (skip: $f not found)"
  done
fi

echo
if [ "${#FAILURES[@]}" -gt 0 ]; then
  log "Completed WITH ${#FAILURES[@]} failure(s):"
  for f in "${FAILURES[@]}"; do echo "    !! $f"; done
  echo "    Re-run the script to retry only the failures (already-mirrored artifacts copy quickly)."
  exit 1
fi
log "Done. Verify a sample:  docker buildx imagetools inspect ${DEST_REGISTRY}/server:v${ARE_VERSION#v}"
