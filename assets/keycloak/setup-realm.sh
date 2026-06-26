#!/usr/bin/env bash
# setup-realm.sh
#
# DEPRECATED / UNUSED. The realm is now imported declaratively from
# agentregistry-enterprise.json via `kubectl apply -k assets/keycloak/`
# (Keycloak --import-realm). This script is kept only for reference and is no
# longer invoked by 001-installation.md or e2e-test.sh. Safe to delete.
#
# End-to-end Keycloak realm configuration for the agentregistry workshop.
# Idempotent: safe to re-run. Fetches a fresh admin token on every API call
# (so token timeouts don't matter even on a slow connection).
#
# Usage:
#   export KC_IP=<keycloak-loadbalancer-ip-or-hostname>
#   ./assets/keycloak/setup-realm.sh
#
# Output:
#   Writes the OIDC variables the install consumes to ~/.are-keycloak-env
#   Source it into your shell:  source ~/.are-keycloak-env
#
# Requires: curl, jq

set -euo pipefail

: "${KC_IP:?KC_IP is required - set it to your Keycloak Service LoadBalancer IP or hostname}"
: "${KC_ADMIN_USER:=admin}"
: "${KC_ADMIN_PASS:=admin123}"
: "${KC_REALM:=agentregistry-enterprise}"

KC_URL="http://${KC_IP}:8080"
ENV_OUT="${HOME}/.are-keycloak-env"

# ---------------------------------------------------------------------------
# Helper: fetch a fresh admin token every time so 60-second token expiry
# never bites us mid-script.
# ---------------------------------------------------------------------------
admin_token() {
  curl -sS -X POST "${KC_URL}/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" \
    -d "username=${KC_ADMIN_USER}" \
    -d "password=${KC_ADMIN_PASS}" \
    | jq -r '.access_token'
}

# Wrapper around curl that fetches a fresh token first
api() {
  local method=$1; shift
  local path=$1; shift
  local token
  token=$(admin_token)
  curl -sS -X "${method}" -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    "${KC_URL}${path}" "$@"
}

# Adds the standard `groups` claim mapper to a client by its internal UUID.
# Idempotent. The mapper emits the plain group NAME (full.path=false), e.g.
# "are-admins" - which is exactly what agentregistry matches `roleClaim` and
# `AccessPolicy` Role principals against.
add_groups_mapper() {
  local CLIENT_UUID=$1
  local CLIENT_NAME=$2
  local EXISTING
  EXISTING=$(api GET "/admin/realms/${KC_REALM}/clients/${CLIENT_UUID}/protocol-mappers/models" \
    | jq -r '.[] | select(.name=="groups") | .id // empty')
  if [ -n "${EXISTING}" ]; then
    echo "    ${CLIENT_NAME}: groups mapper already exists"
  else
    api POST "/admin/realms/${KC_REALM}/clients/${CLIENT_UUID}/protocol-mappers/models" \
      --data-raw '{"name":"groups","protocol":"openid-connect","protocolMapper":"oidc-group-membership-mapper","config":{"claim.name":"groups","full.path":"false","id.token.claim":"true","access.token.claim":"true","userinfo.token.claim":"true"}}' >/dev/null
    echo "    ${CLIENT_NAME}: groups mapper created"
  fi
}

# ---------------------------------------------------------------------------
# Wait for Keycloak to be reachable. The Service may be live before Keycloak
# itself finishes its first-boot import.
# ---------------------------------------------------------------------------
echo "==> Waiting for Keycloak at ${KC_URL} ..."
for i in $(seq 1 60); do
  if curl -sSf "${KC_URL}/realms/master" >/dev/null 2>&1; then
    echo "    Keycloak is up."
    break
  fi
  sleep 5
  if [ "${i}" -eq 60 ]; then
    echo "ERROR: Keycloak never came up at ${KC_URL}" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# 1. Allow non-SSL cookies on the master realm (HTTP-only POC).
# ---------------------------------------------------------------------------
echo "==> Configuring master realm (sslRequired=none)"
api PUT "/admin/realms/master" \
  -d '{"realm":"master","sslRequired":"none"}'

# ---------------------------------------------------------------------------
# 2. Create the agentregistry-enterprise realm (or update if it exists).
# ---------------------------------------------------------------------------
echo "==> Creating realm ${KC_REALM}"
if api GET "/admin/realms/${KC_REALM}" | jq -e '.realm' >/dev/null 2>&1; then
  echo "    realm already exists, skipping create"
else
  api POST "/admin/realms" \
    --data-raw "{\"realm\":\"${KC_REALM}\",\"enabled\":true,\"sslRequired\":\"none\"}"
fi

# ---------------------------------------------------------------------------
# 3. Create groups: are-admins, are-readers, are-writers.
# ---------------------------------------------------------------------------
echo "==> Creating groups"
for GROUP in are-admins are-readers are-writers; do
  EXISTING=$(api GET "/admin/realms/${KC_REALM}/groups" \
    | jq -r --arg n "${GROUP}" '.[] | select(.name==$n) | .id')
  if [ -n "${EXISTING}" ]; then
    echo "    ${GROUP}: exists ${EXISTING}"
  else
    api POST "/admin/realms/${KC_REALM}/groups" \
      --data-raw "{\"name\":\"${GROUP}\"}" >/dev/null
    echo "    ${GROUP}: created"
  fi
done

GROUPS_JSON=$(api GET "/admin/realms/${KC_REALM}/groups")
GROUP_ADMINS=$(echo "${GROUPS_JSON}"  | jq -r '.[] | select(.name=="are-admins")  | .id')
GROUP_READERS=$(echo "${GROUPS_JSON}" | jq -r '.[] | select(.name=="are-readers") | .id')
GROUP_WRITERS=$(echo "${GROUPS_JSON}" | jq -r '.[] | select(.name=="are-writers") | .id')

# ---------------------------------------------------------------------------
# 4. Create users: admin / reader / writer (password = username, demo only).
# ---------------------------------------------------------------------------
echo "==> Creating users"
create_user() {
  local USERNAME=$1
  local GROUP_ID=$2
  local USER_ID
  local EXISTING

  EXISTING=$(api GET "/admin/realms/${KC_REALM}/users?username=${USERNAME}" \
    | jq -r '.[0].id // empty')
  if [ -n "${EXISTING}" ]; then
    USER_ID="${EXISTING}"
    echo "    ${USERNAME}: exists ${USER_ID}"
  else
    api POST "/admin/realms/${KC_REALM}/users" \
      --data-raw "{\"username\":\"${USERNAME}\",\"enabled\":true,\"email\":\"${USERNAME}@example.com\",\"emailVerified\":true,\"firstName\":\"${USERNAME}\",\"lastName\":\"user\"}" >/dev/null
    USER_ID=$(api GET "/admin/realms/${KC_REALM}/users?username=${USERNAME}" \
      | jq -r '.[0].id')
    echo "    ${USERNAME}: created ${USER_ID}"
  fi

  api PUT "/admin/realms/${KC_REALM}/users/${USER_ID}/reset-password" \
    --data-raw "{\"type\":\"password\",\"value\":\"${USERNAME}\",\"temporary\":false}" >/dev/null
  api PUT "/admin/realms/${KC_REALM}/users/${USER_ID}/groups/${GROUP_ID}" >/dev/null
}

create_user admin  "${GROUP_ADMINS}"
create_user reader "${GROUP_READERS}"
create_user writer "${GROUP_WRITERS}"

# ---------------------------------------------------------------------------
# 5. Create OIDC clients: are-backend (confidential) + are-cli (public).
# ---------------------------------------------------------------------------
echo "==> Creating OIDC clients"
create_client() {
  local CLIENT_ID=$1
  local PAYLOAD=$2
  local EXISTING

  EXISTING=$(api GET "/admin/realms/${KC_REALM}/clients?clientId=${CLIENT_ID}" \
    | jq -r '.[0].id // empty')
  if [ -n "${EXISTING}" ]; then
    echo "    ${CLIENT_ID}: exists ${EXISTING}"
  else
    api POST "/admin/realms/${KC_REALM}/clients" --data-raw "${PAYLOAD}" >/dev/null
    echo "    ${CLIENT_ID}: created"
  fi
}

ARE_BACKEND_PAYLOAD='{"clientId":"are-backend","enabled":true,"publicClient":false,"standardFlowEnabled":true,"directAccessGrantsEnabled":true,"serviceAccountsEnabled":true,"redirectUris":["*"],"webOrigins":["*"]}'
ARE_CLI_PAYLOAD='{"clientId":"are-cli","enabled":true,"publicClient":true,"standardFlowEnabled":true,"directAccessGrantsEnabled":true,"redirectUris":["*"],"webOrigins":["*"],"attributes":{"oauth2.device.authorization.grant.enabled":"true","pkce.code.challenge.method":""}}'

create_client "are-backend" "${ARE_BACKEND_PAYLOAD}"
create_client "are-cli"     "${ARE_CLI_PAYLOAD}"

ARE_BACKEND_ID=$(api GET "/admin/realms/${KC_REALM}/clients?clientId=are-backend" \
  | jq -r '.[0].id')
ARE_CLI_ID=$(api GET "/admin/realms/${KC_REALM}/clients?clientId=are-cli" \
  | jq -r '.[0].id')

# ---------------------------------------------------------------------------
# 6. Add the "groups" claim mapper to BOTH clients so group memberships show
#    up in tokens.
#
#    IMPORTANT: arctl AND the UI both authenticate via the PUBLIC `are-cli`
#    client. If the mapper is only on `are-backend`, the token arctl/UI carry
#    has no `groups` claim, the registry resolves zero roles, and your admin
#    user is never a superuser (every admin/write op 403s). So the mapper must
#    be on are-cli too. This is the single most important line in this script.
# ---------------------------------------------------------------------------
echo "==> Adding groups claim mapper to clients"
add_groups_mapper "${ARE_BACKEND_ID}" "are-backend"
add_groups_mapper "${ARE_CLI_ID}"     "are-cli"

# ---------------------------------------------------------------------------
# 7. Read the are-backend client secret.
#    Use GET (read the existing secret), NOT POST (which REGENERATES it).
#    POST would rotate the secret on every re-run, breaking idempotency and
#    desyncing from the secret already baked into the deployed Helm release.
# ---------------------------------------------------------------------------
echo "==> Fetching are-backend client secret"
BACKEND_CLIENT_SECRET=$(api GET "/admin/realms/${KC_REALM}/clients/${ARE_BACKEND_ID}/client-secret" \
  | jq -r '.value')

# ---------------------------------------------------------------------------
# 8. Write all the values the install consumes into ~/.are-keycloak-env.
# ---------------------------------------------------------------------------
echo "==> Writing ${ENV_OUT}"
cat > "${ENV_OUT}" <<EOF
# Generated by setup-realm.sh on $(date -u +'%Y-%m-%dT%H:%M:%SZ')
# Source into your shell:  source ${ENV_OUT}
export OIDC_PROVIDER=keycloak
export OIDC_ISSUER="${KC_URL}/realms/${KC_REALM}"
export OIDC_BACKEND=are-backend
export OIDC_PUBLIC_CLIENT=are-cli
export ARE_CLI_CLIENT_ID=are-cli
export BACKEND_CLIENT_SECRET="${BACKEND_CLIENT_SECRET}"
export GROUP_ADMINS="${GROUP_ADMINS}"
export GROUP_READERS="${GROUP_READERS}"
export GROUP_WRITERS="${GROUP_WRITERS}"
EOF
chmod 600 "${ENV_OUT}"

echo ""
echo "==> Done. Source the env file:"
echo "        source ${ENV_OUT}"
echo ""
echo "==> Values the install will consume:"
grep '^export' "${ENV_OUT}" | sed 's/^export /    /'
