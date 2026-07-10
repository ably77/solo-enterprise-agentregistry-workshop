#!/usr/bin/env bash
# =============================================================================
# Enterprise Agentregistry Workshop — AgentCore E2E Module
# =============================================================================
# Covers the labs/runtimes/ AWS Bedrock AgentCore series, Parts 1 + 3:
# IAM/CloudFormation integration, Runtime registration, publish + deploy
# econresearch, live round-trip. Opt-in only (real AWS resources, real cost).
#
# Sourced by e2e-test.sh (./e2e-test.sh agentcore | agentcore-cleanup |
# --include-agentcore); reuses its helpers. Never run directly.
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "this module is sourced by e2e-test.sh — run: ./e2e-test.sh agentcore" >&2
  exit 2
fi

# ---------- module config ----------------------------------------------------
AR_USER_PREFIX="${AR_USER_PREFIX:-$(whoami)}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AR_DEPLOYER_USER="${AR_USER_PREFIX}-agentregistry-deployer"
AR_ROLE_NAME="${AR_USER_PREFIX}-AgentRegistryAccessRole"
AR_STACK_NAME="${AR_USER_PREFIX}-agentregistry-access-role"
AGENTCORE_POLICIES=(
  "${AR_USER_PREFIX}-AgentRegistryGeneralAccess:assets/runtimes/agentcore/general-access-policy.json"
  "${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart1:assets/runtimes/agentcore/bedrock-agentcore-policy-part1.json"
  "${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart2:assets/runtimes/agentcore/bedrock-agentcore-policy-part2.json"
)

# =============================================================================
# AgentCore Phase 0 — AWS Preflight (every miss is a FAIL with remediation;
# the module was explicitly opted into, so a missing prereq is an error)
# =============================================================================
agentcore_preflight() {
  phase "AgentCore Phase 0 — AWS Preflight"
  local ok=1

  step "AWS CLI"
  if require_cmd aws; then
    pass "aws CLI present"
  else
    fail "aws CLI missing"
    info "install: brew install awscli   (or: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)"
    ok=0
  fi

  step "AWS credentials (operator)"
  local ident=""
  if [ "$ok" = 1 ] && ident=$(aws sts get-caller-identity 2>&1); then
    export AWS_ACCOUNT_ID
    AWS_ACCOUNT_ID=$(printf '%s' "$ident" | jq -r .Account)
    pass "authenticated as $(printf '%s' "$ident" | jq -r .Arn) (account ${AWS_ACCOUNT_ID})"
  else
    fail "aws sts get-caller-identity failed"
    info "access keys: run 'aws configure' (prompts: Access Key ID, Secret Access Key, region, output format)"
    info "SSO orgs:    run 'aws configure sso' once, then 'aws sso login'"
    ok=0
  fi

  step "Bedrock model availability (${AWS_REGION})"
  if [ "$ok" = 1 ]; then
    local models
    models=$(aws bedrock list-foundation-models --region "${AWS_REGION}" --by-provider anthropic \
      --query 'modelSummaries[].modelId' --output text 2>/dev/null)
    if printf '%s' "$models" | grep -q 'anthropic\.'; then
      pass "anthropic.* models visible in ${AWS_REGION}"
    else
      fail "no anthropic.* Bedrock models visible in ${AWS_REGION}"
      info "the region must carry both Bedrock AgentCore and Claude models; us-east-1 has both: export AWS_REGION=us-east-1"
      ok=0
    fi
  else
    skip "Bedrock check (no AWS credentials)"
  fi

  step "arctl session"
  # not `arctl user whoami`: it exits 0 even when the API returns 401
  # (falls back to local token info); `get runtimes` is a real API round-trip
  if _arctl get runtimes >/dev/null 2>&1; then
    pass "arctl authenticated"
  else
    fail "arctl not authenticated"
    info "log in, then re-run this mode:"
    info "  export PATH=\$HOME/.arctl/bin:\$PATH"
    info "  source ~/.are-keycloak-env"
    info "  arctl user login --oidc-issuer-url \"${OIDC_ISSUER:-\$OIDC_ISSUER}\" --oidc-client-id \"${ARE_CLI_CLIENT_ID:-\$ARE_CLI_CLIENT_ID}\""
    info "or non-interactively: ARCTL_LOGIN=token ./e2e-test.sh agentcore"
    ok=0
  fi

  [ "$ok" = 1 ]
}

# =============================================================================
# AgentCore Phase 1 — Integration (IAM + CloudFormation + Runtime)
# Idempotent: EntityAlreadyExists / existing stack / aws.enabled=true are all
# treated as "reuse", so a rerun against standing state passes.
# =============================================================================
_iam_create_policy() {
  local name="$1" file="$2" out
  if out=$(aws iam create-policy --policy-name "$name" --policy-document "file://$file" 2>&1); then
    pass "policy $name created"
  elif printf '%s' "$out" | grep -q EntityAlreadyExists; then
    pass "policy $name already exists — reusing"
  else
    fail "create policy $name: $(printf '%s' "$out" | head -1)"
    return 1
  fi
}

_stack_status() {
  aws cloudformation describe-stacks --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null
}

_helm_aws_enabled() {
  helm get values agentregistry-enterprise -n agentregistry-system -o json 2>/dev/null \
    | jq -e '.aws.enabled == true' >/dev/null 2>&1
}

agentcore_integration() {
  phase "AgentCore Phase 1 — Integration (IAM + CloudFormation + Runtime)"
  AGENTCORE_RAN=1

  step "IAM policies"
  local entry name file
  for entry in "${AGENTCORE_POLICIES[@]}"; do
    name="${entry%%:*}"; file="${entry#*:}"
    _iam_create_policy "$name" "$file" || return 1
  done

  step "Deployer IAM user (${AR_DEPLOYER_USER})"
  local out
  if out=$(aws iam create-user --user-name "$AR_DEPLOYER_USER" 2>&1); then
    pass "user created"
  elif printf '%s' "$out" | grep -q EntityAlreadyExists; then
    pass "user already exists — reusing"
  else
    fail "create user: $(printf '%s' "$out" | head -1)"
    return 1
  fi
  for entry in "${AGENTCORE_POLICIES[@]}"; do
    name="${entry%%:*}"
    assert "attach ${name}" aws iam attach-user-policy --user-name "$AR_DEPLOYER_USER" \
      --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${name}" || return 1
  done

  step "Registry AWS credentials (helm)"
  if _helm_aws_enabled && kubectl rollout status deployment/agentregistry-enterprise-server \
       -n agentregistry-system --timeout=60s >/dev/null 2>&1; then
    skip "registry already holds AWS credentials (aws.enabled=true, server healthy)"
  else
    # IAM caps users at 2 access keys; sweep old ones before minting
    local k keys
    keys=$(aws iam list-access-keys --user-name "$AR_DEPLOYER_USER" \
      --query 'AccessKeyMetadata[].AccessKeyId' --output text 2>/dev/null)
    for k in $keys; do
      aws iam delete-access-key --user-name "$AR_DEPLOYER_USER" --access-key-id "$k" >/dev/null 2>&1 || true
      info "deleted stale access key $k"
    done
    local key_out
    key_out=$(aws iam create-access-key --user-name "$AR_DEPLOYER_USER" 2>/dev/null)
    AR_AWS_ACCESS_KEY_ID=$(printf '%s' "$key_out" | jq -r '.AccessKey.AccessKeyId' 2>/dev/null)
    AR_AWS_SECRET_ACCESS_KEY=$(printf '%s' "$key_out" | jq -r '.AccessKey.SecretAccessKey' 2>/dev/null)
    if [ -z "${AR_AWS_ACCESS_KEY_ID:-}" ] || [ "$AR_AWS_ACCESS_KEY_ID" = null ]; then
      fail "could not mint deployer access key"
      return 1
    fi
    pass "minted fresh deployer access key"
    if helm upgrade agentregistry-enterprise \
         oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
         --version "$ARE_HELM_VERSION" \
         --namespace agentregistry-system \
         --reuse-values \
         --set aws.enabled=true \
         --set-string aws.accountId="$AWS_ACCOUNT_ID" \
         --set-string aws.region="$AWS_REGION" \
         --set-string aws.accessKeyId="$AR_AWS_ACCESS_KEY_ID" \
         --set-string aws.secretAccessKey="$AR_AWS_SECRET_ACCESS_KEY" \
         --wait --timeout 5m >/dev/null 2>&1; then
      pass "helm upgrade applied aws.* values"
    else
      fail "helm upgrade with aws.* values failed"
      return 1
    fi
    assert "server rollout complete" kubectl rollout status \
      deployment/agentregistry-enterprise-server -n agentregistry-system --timeout=300s || return 1
  fi

  step "Cross-account role stack (${AR_STACK_NAME})"
  local st; st=$(_stack_status)
  case "$st" in
    CREATE_COMPLETE|UPDATE_COMPLETE)
      pass "stack already exists (${st}) — reusing"
      ;;
    *)
      # arctl quirk: `runtime setup` ignores the keychain session and
      # authenticates only via ARCTL_API_TOKEN/--registry-token (401 otherwise),
      # so mint an admin token when the env doesn't already carry one
      ARCTL_API_TOKEN="${ARCTL_API_TOKEN:-$(_token_for admin)}" \
        _arctl runtime setup bedrock-agent-core \
        --aws-account-id "$AWS_ACCOUNT_ID" \
        --role-name "$AR_ROLE_NAME" > /tmp/agentregistry-cf.yaml 2>/tmp/agentcore-rtsetup.err
      if [ ! -s /tmp/agentregistry-cf.yaml ]; then
        fail "arctl runtime setup produced no CloudFormation template ($(head -1 /tmp/agentcore-rtsetup.err 2>/dev/null))"
        return 1
      fi
      # v2026.6.2 trusts the account root gated by ExternalId (covers any
      # principal); older/newer shapes naming the literal default user get the
      # lab's sed patch so AssumeRole trusts our prefixed deployer
      if grep -qE 'arn:aws:iam::[0-9]+:root' /tmp/agentregistry-cf.yaml; then
        info "trust policy trusts account root — OK"
      elif grep -q 'user/agentregistry-deployer' /tmp/agentregistry-cf.yaml; then
        case "$(uname)" in
          Darwin) sed -i '' "s#user/agentregistry-deployer#user/${AR_DEPLOYER_USER}#" /tmp/agentregistry-cf.yaml ;;
          *)      sed -i "s#user/agentregistry-deployer#user/${AR_DEPLOYER_USER}#" /tmp/agentregistry-cf.yaml ;;
        esac
        info "patched trust principal to ${AR_DEPLOYER_USER}"
      fi
      assert "create-stack accepted" aws cloudformation create-stack \
        --stack-name "$AR_STACK_NAME" \
        --template-body file:///tmp/agentregistry-cf.yaml \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" || return 1
      assert "stack CREATE_COMPLETE (~1m)" aws cloudformation wait stack-create-complete \
        --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" || return 1
      ;;
  esac

  step "Stack outputs"
  AWS_ROLE_ARN=$(aws cloudformation describe-stacks --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" --output text 2>/dev/null)
  AWS_EXTERNAL_ID=$(aws cloudformation describe-stacks --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='ExternalId'].OutputValue" --output text 2>/dev/null)
  if [ -n "${AWS_ROLE_ARN:-}" ] && [ "$AWS_ROLE_ARN" != None ]; then
    pass "RoleArn: ${AWS_ROLE_ARN}"
  else
    fail "RoleArn missing from stack outputs"
    return 1
  fi
  if [ -n "${AWS_EXTERNAL_ID:-}" ] && [ "$AWS_EXTERNAL_ID" != None ]; then
    pass "ExternalId captured"
  else
    fail "ExternalId missing from stack outputs (grep -i externalid /tmp/agentregistry-cf.yaml)"
    return 1
  fi

  step "Register agentcore Runtime"
  cat > /tmp/agentcore-runtime.yaml <<EOF
apiVersion: ar.dev/v1alpha1
kind: Runtime
metadata:
  name: agentcore
spec:
  type: BedrockAgentCore
  config:
    roleArn: "${AWS_ROLE_ARN}"
    externalId: "${AWS_EXTERNAL_ID}"
    region: "${AWS_REGION}"
EOF
  assert "arctl apply Runtime" _arctl apply -f /tmp/agentcore-runtime.yaml || return 1
  assert_contains "agentcore in runtimes" "agentcore" "$(_arctl get runtimes 2>/dev/null)"
}

# =============================================================================
# AgentCore Phase 2 — Deploy econresearch
# Rerun-safe: arctl apply of an existing Agent/Deployment is a no-op
# ("unchanged") and the deployed-state poll passes immediately.
# =============================================================================
# Deployed-state probe: AgentCore deployments report a "deployed" state/
# condition; filter out "deploying" lines first so the in-progress state
# never false-positives.
_agentcore_dep_deployed() {
  _arctl get deployment "$1" -o yaml 2>/dev/null | grep -vi 'deploying' | grep -qiE '\bdeployed\b'
}

agentcore_deploy() {
  phase "AgentCore Phase 2 — Deploy econresearch"
  AGENTCORE_RAN=1

  step "Publish econresearch to the catalog"
  assert "arctl apply agent.yaml" _arctl apply -f assets/agents/econresearch/agent.yaml || return 1
  assert_contains "econresearch in agents" "econresearch" "$(_arctl get agents 2>/dev/null)"

  step "Deploy to the agentcore runtime"
  cat > /tmp/agentcore-econresearch-deployment.yaml <<EOF
apiVersion: ar.dev/v1alpha1
kind: Deployment
metadata:
  name: econresearch
spec:
  targetRef:
    kind: Agent
    name: econresearch
    tag: "1.0.0"
  runtimeRef:
    kind: Runtime
    name: agentcore
  runtimeConfig:
    region: ${AWS_REGION}
    workdir: assets/agents/econresearch
EOF
  assert "arctl apply Deployment" _arctl apply -f /tmp/agentcore-econresearch-deployment.yaml || return 1

  step "Wait for deployed (clone + image build + AgentCore rollout; up to 15m)"
  if poll 900 15 _agentcore_dep_deployed econresearch; then
    pass "deployment econresearch reached deployed"
  else
    fail "deployment econresearch not deployed within 15m"
    info "status.conditions:"
    _arctl get deployment econresearch -o yaml 2>/dev/null | sed -n '/conditions:/,$p' | sed 's/^/    /'
    return 1
  fi

  step "CloudWatch log group (proves AgentCore created the runtime)"
  local groups
  groups=$(aws logs describe-log-groups --region "$AWS_REGION" \
    --log-group-name-prefix /aws/bedrock-agentcore/runtimes/ \
    --query 'logGroups[].logGroupName' --output text 2>/dev/null)
  assert_contains "econresearch runtime log group exists" "econresearch" "$groups"

  step "Live round-trip (best-effort; deployed state + log group are the hard signals)"
  local rt_arn
  rt_arn=$(_arctl get deployment econresearch -o yaml 2>/dev/null \
    | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[A-Za-z0-9_-]+' | head -1)
  if [ -z "$rt_arn" ]; then
    skip "live invoke (no runtime ARN found in deployment status)"
  elif ! aws bedrock-agentcore invoke-agent-runtime help >/dev/null 2>&1; then
    skip "live invoke (installed aws CLI lacks bedrock-agentcore invoke-agent-runtime)"
  else
    rm -f /tmp/agentcore-invoke-out.json
    if aws bedrock-agentcore invoke-agent-runtime \
         --region "$AWS_REGION" \
         --agent-runtime-arn "$rt_arn" \
         --qualifier DEFAULT \
         --cli-binary-format raw-in-base64-out \
         --payload '{"prompt":"In one sentence: where are 30-year mortgage rates relative to the 10-year treasury?"}' \
         /tmp/agentcore-invoke-out.json >/dev/null 2>&1 \
       && [ -s /tmp/agentcore-invoke-out.json ]; then
      pass "live invoke returned a response payload"
    else
      skip "live invoke returned no parseable response"
    fi
  fi
}

# =============================================================================
# AgentCore Cleanup — ./e2e-test.sh agentcore-cleanup (never automatic)
# Order matters: registry Deployment before Runtime before the AWS stack/IAM.
# Every step tolerates already-gone resources, so re-running is safe.
# =============================================================================
_agentcore_dep_gone() { ! _arctl get deployment "$1" >/dev/null 2>&1; }

agentcore_cleanup() {
  phase "AgentCore Cleanup"

  AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}"
  if [ -z "${AWS_ACCOUNT_ID:-}" ]; then
    fail "cannot determine AWS account — authenticate the aws CLI first (aws configure / aws sso login)"
    return 1
  fi

  # `get runtimes` not `user whoami` — whoami exits 0 even on a 401
  if ! _arctl get runtimes >/dev/null 2>&1; then
    fail "arctl not authenticated — registry objects can't be deleted"
    info "log in, then re-run this mode:"
    info "  export PATH=\$HOME/.arctl/bin:\$PATH"
    info "  source ~/.are-keycloak-env"
    info "  arctl user login --oidc-issuer-url \"${OIDC_ISSUER:-\$OIDC_ISSUER}\" --oidc-client-id \"${ARE_CLI_CLIENT_ID:-\$ARE_CLI_CLIENT_ID}\""
    info "or non-interactively: ARCTL_LOGIN=token ./e2e-test.sh agentcore-cleanup"
    return 1
  fi

  step "Registry: deployment, agent, runtime"
  local rt_id
  rt_id=$(_arctl get deployment econresearch -o yaml 2>/dev/null \
    | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[A-Za-z0-9_-]+' | head -1 | sed 's#.*/##')
  if _arctl delete deployment econresearch >/dev/null 2>&1; then
    info "deleted deployment econresearch"
    poll 300 10 _agentcore_dep_gone econresearch || info "deployment still listed after 5m — continuing"
  else
    info "deployment econresearch already gone"
  fi
  _arctl delete agent econresearch --tag 1.0.0 >/dev/null 2>&1 \
    && info "deleted agent econresearch" || info "agent econresearch already gone"
  _arctl delete runtime agentcore >/dev/null 2>&1 \
    && info "deleted runtime agentcore" || info "runtime agentcore already gone"
  if _agentcore_dep_gone econresearch && ! _arctl get runtimes 2>/dev/null | grep -qw agentcore; then
    pass "registry objects removed"
  else
    fail "registry objects still present after delete — aborting before AWS teardown (fix arctl session/server and re-run)"
    return 1
  fi

  step "CloudFormation stack (${AR_STACK_NAME})"
  aws cloudformation delete-stack --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" >/dev/null 2>&1 || true
  aws cloudformation wait stack-delete-complete --stack-name "$AR_STACK_NAME" --region "$AWS_REGION" >/dev/null 2>&1 || true
  pass "stack deleted (or already gone)"

  step "Deployer IAM user + policies"
  local k keys entry name
  keys=$(aws iam list-access-keys --user-name "$AR_DEPLOYER_USER" \
    --query 'AccessKeyMetadata[].AccessKeyId' --output text 2>/dev/null)
  for k in $keys; do
    aws iam delete-access-key --user-name "$AR_DEPLOYER_USER" --access-key-id "$k" >/dev/null 2>&1 || true
  done
  for entry in "${AGENTCORE_POLICIES[@]}"; do
    name="${entry%%:*}"
    aws iam detach-user-policy --user-name "$AR_DEPLOYER_USER" \
      --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${name}" >/dev/null 2>&1 || true
  done
  aws iam delete-user --user-name "$AR_DEPLOYER_USER" >/dev/null 2>&1 \
    && info "deleted user ${AR_DEPLOYER_USER}" || info "user ${AR_DEPLOYER_USER} already gone"
  for entry in "${AGENTCORE_POLICIES[@]}"; do
    name="${entry%%:*}"
    aws iam delete-policy \
      --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${name}" >/dev/null 2>&1 \
      && info "deleted policy ${name}" || info "policy ${name} already gone"
  done
  pass "IAM principals removed"

  step "CloudWatch log group (best-effort; this deployment's runtime only)"
  if [ -n "${rt_id:-}" ]; then
    aws logs delete-log-group \
      --log-group-name "/aws/bedrock-agentcore/runtimes/${rt_id}-DEFAULT" \
      --region "$AWS_REGION" >/dev/null 2>&1 \
      && info "deleted /aws/bedrock-agentcore/runtimes/${rt_id}-DEFAULT" \
      || info "log group for ${rt_id} already gone"
    pass "log group swept"
  else
    skip "log-group sweep (no runtime id in deployment status; remove /aws/bedrock-agentcore/runtimes/<id>-DEFAULT manually if present)"
  fi

  step "Drop aws.* helm values"
  if _helm_aws_enabled; then
    if helm upgrade agentregistry-enterprise \
         oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
         --version "$ARE_HELM_VERSION" \
         --namespace agentregistry-system \
         --reuse-values --set aws.enabled=false \
         --wait --timeout 5m >/dev/null 2>&1; then
      pass "aws.enabled=false applied"
      assert "server rollout complete" kubectl rollout status \
        deployment/agentregistry-enterprise-server -n agentregistry-system --timeout=300s
    else
      fail "helm upgrade to disable aws.* failed"
    fi
  else
    skip "aws.* values already disabled"
  fi

  step "Local temp files"
  rm -f /tmp/agentregistry-cf.yaml /tmp/agentcore-runtime.yaml \
        /tmp/agentcore-econresearch-deployment.yaml /tmp/agentcore-invoke-out.json
  pass "temp files removed"

  info "Removed: registry deployment/agent/runtime, stack ${AR_STACK_NAME}, user ${AR_DEPLOYER_USER} + 3 policies, runtime log group (targeted), aws.* helm values"
}
