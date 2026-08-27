# Cleanup

> **AWS Bedrock AgentCore series**
> [Part 1: Integrate Agentregistry and AgentCore](agentcore-01-integration.md) ·
> [Part 2: Create Agents](agentcore-02-create-agents.md) ·
> [Part 3: Register and Deploy Agents to AgentCore](agentcore-03-deploy-agents.md) ·
> [Part 4: Approval-Gated Agent Onboarding](agentcore-04-approval-onboarding.md) ·
> [Part 5: Route LLM and Registry-Managed MCP Through Agentgateway](agentcore-05-agentgateway-llm-mcp.md) ·
> [Part 6: Gateway-Bound Runtime: Policy Enforcement and Tracing](agentcore-06-gateway-policy-tracing.md) ·
> **Cleanup** (this doc)

Every teardown step for the series, in one place. Run the sections below **top to bottom**, and
skip any section for a part you never did.

> **Order matters.** Deployments and catalog entries (Parts 3–5) and the Gateway binding
> (Part 6) must go before the Runtime and AWS integration they depend on (Part 1): a `Deployment`
> can't be deleted cleanly once its `Runtime` is gone, a bound `Runtime` should be unbound before
> its Gateway disappears, and Part 1's cross-account role is what Parts 3–6 all assumed to
> exist. If you're only part-way through the series, just run the sections for the parts you
> completed, in this order.

## If you completed Part 6 (Gateway-Bound Runtime: Policy Enforcement and Tracing)

Run this section before Part 5's below it: `Runtime/agentcore` should be unbound from this lab's
Gateway before that Gateway disappears out from under it. Order within the section is policy →
binding → Gateway, the same dependency order the lab itself builds in, unwound.

> Fresh shell? `AR_USER_PREFIX` isn't re-derived anywhere else in this doc until the Part 1
> section; if you haven't already got it set this session, `export AR_USER_PREFIX="$(whoami)"`
> first. This lab's Gateway and RuntimeAccessPolicy are named `${AR_USER_PREFIX}-part6-gateway`
> and `${AR_USER_PREFIX}-part6-rap`.

```bash
# 1. The policy: delete it first so nothing is still being gated by a rule
#    that's about to point at an unbound Gateway anyway
arctl delete runtimeaccesspolicy "${AR_USER_PREFIX}-part6-rap"

# 2. Unbind the Runtime: re-apply with spec.config.gatewayRef omitted
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: Runtime
metadata: {name: agentcore}
spec:
  type: BedrockAgentCore
  config:
    region: "${AWS_REGION}"
    roleArn: "${AWS_ROLE_ARN}"
    externalId: "${AWS_EXTERNAL_ID}"
EOF

# 3. Delete the Gateway
arctl delete gateway "${AR_USER_PREFIX}-part6-gateway"
```

Two states you'll see here are expected, not failures:

- **`AgentEgressReady: False`, `reason: GatewayRefRemoved`** on `Runtime/agentcore` the moment
  step 2 lands. This is the registry correctly reporting that any RAP destinations bound through
  this Gateway are now unreachable until you redeploy or rebind, not a bug.
- **A stale `lastForceToken` on the RAP's former target Deployment** (e.g. `fred-incluster-agw`,
  if you pointed the lab's `RuntimeAccessPolicy` at it). Deleting the RAP does not clear
  `status.details.deploymentController.lastForceToken` on the Deployment it referenced: that
  field is a historical audit marker ("what last forced a reconcile on this object"), not current
  desired state. It keeps pointing at your deleted RAP's name and token indefinitely, harmlessly,
  until some other force-reconcile event overwrites it. The Deployment's health
  (`Ready: True`, `DeployedViaAgentgateway`) is unaffected throughout; this residue is not a
  cleanup failure.

**Optional: remove the AppConfig application.** The steps above delete the Gateway and unbind
the Runtime, but they don't touch the AWS AppConfig application the registry provisioned when
you bound the Gateway (Lab Objectives, "Bind `Runtime/agentcore` to the Gateway"). It's inert
and free-tier-scale, so leaving it is safe; if you want AWS fully clean, delete its hosted
configuration versions and configuration profile before the application itself:

```bash
# Find the application (named ar-<hash>) and its profile
aws appconfig list-applications --region "${AWS_REGION}"
aws appconfig list-configuration-profiles --application-id <app-id> --region "${AWS_REGION}"

# Delete every hosted configuration version first: AppConfig refuses to delete
# a profile (and a profile blocks deleting the application) while versions remain
aws appconfig list-hosted-configuration-versions \
  --application-id <app-id> --configuration-profile-id <profile-id> \
  --region "${AWS_REGION}" --query 'Items[].VersionNumber' --output text | \
  tr '\t' '\n' | xargs -I{} aws appconfig delete-hosted-configuration-version \
  --application-id <app-id> --configuration-profile-id <profile-id> \
  --version-number {} --region "${AWS_REGION}"

# Then the profile, then the application
aws appconfig delete-configuration-profile --application-id <app-id> \
  --configuration-profile-id <profile-id> --region "${AWS_REGION}"
aws appconfig delete-application --application-id <app-id> --region "${AWS_REGION}"
```

## If you completed Part 5 (Route LLM and Registry-Managed MCP Through Agentgateway)

```bash
# Agent + its agent-facing FRED entry
arctl delete deployment econresearch-agw
arctl delete agent econresearch-agw --tag 1.0.0
arctl delete mcp fred-gateway-mcp --tag latest

# OpenAI route (stop exposing your key's spend!)
kubectl delete -f assets/mcp/agentgateway/openai-backend-and-route.yaml
kubectl delete secret openai-secret -n agentgateway-system

# FRED (skip if you set it up in the FRED MCP lab and want to keep it)
arctl delete deployment fred-incluster-agw
arctl delete mcp fred-incluster-mcp --tag latest
kubectl delete -f assets/mcp/in-cluster/fred-deployment.yaml
kubectl delete secret fred-api-key -n mcp
```

> The `mcp` namespace is intentionally left in place: the
> [In-Cluster MCP lab](../mcp/in-cluster-mcp.md)'s arXiv server shares it. Only delete the
> namespace if nothing else of yours lives there.

> AgentCore leaves the runtime's CloudWatch log group behind; remove it with
> `aws logs delete-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT" --region "${AWS_REGION}"`.
> The parent Gateway is shared with the MCP labs; remove it only if you're done with those (see
> the [FRED MCP lab](../mcp/fred-mcp.md) cleanup).

## If you completed Part 4 (Approval-Gated Agent Onboarding)

```bash
arctl delete deployment ithelpdesk
arctl delete agent ithelpdesk --tag 1.0.0

# safety net if you skipped the lab's "Restore Defaults" step
arctl delete accesspolicy are-readers-agent-onboarding 2>/dev/null || true
helm upgrade --install agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.8.0 \
  --namespace agentregistry-system \
  --reuse-values \
  --set config.requireCreateApproval=false
```

> Like Part 3's runtimes, `ithelpdesk`'s CloudWatch log group
> (`/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`) is left behind; remove it with
> `aws logs delete-log-group` if you want a fully clean account.

## If you completed Part 3 (Register and Deploy Agents to AgentCore)

```bash
arctl delete deployment econresearch
arctl delete agent econresearch --tag 1.0.0
arctl delete deployment claimsupport
arctl delete agent claimsupport --tag 1.0.0
arctl delete deployment bankingsupport
arctl delete agent bankingsupport --tag 1.0.0

# last: every Part 3-5 Deployment references this Model
arctl delete model default --tag latest
```

> AgentCore also leaves behind each runtime's CloudWatch log group; remove them with
> `aws logs delete-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT" --region "${AWS_REGION}"`
> if you want a fully clean account.

## If you completed Part 1 (Integrate Agentregistry and AgentCore)

This tears down the AgentCore integration itself: the `agentcore` Runtime, the cross-account role
stack, the deployer IAM user, and the `aws.*` helm values. Run it only once everything in the
sections above (if applicable) is gone; a `Deployment` still targeting this Runtime will block or
orphan when the Runtime disappears.

> Running this in a fresh shell? Re-run [Part 1](agentcore-01-integration.md)'s Pre-requisites
> shell context (this recomputes `AR_USER_PREFIX=$(whoami)`, so it reproduces the same
> `AR_DEPLOYER_USER`/`AR_STACK_NAME` without you needing to have saved them) and step 0.3
> (`AWS_REGION`, `AWS_ACCOUNT_ID`), then recover the deployer's access-key ID with
> `aws iam list-access-keys --user-name "${AR_DEPLOYER_USER}"`, exporting it as
> `AR_AWS_ACCESS_KEY_ID` before running the IAM cleanup block.

```bash
export AR_DEPLOYER_USER="${AR_USER_PREFIX}-agentregistry-deployer"
export AR_STACK_NAME="${AR_USER_PREFIX}-agentregistry-access-role"

# Registry side: the runtime
arctl delete runtime agentcore

# AWS side: the cross-account role stack
aws cloudformation delete-stack \
  --stack-name "${AR_STACK_NAME}" \
  --region "${AWS_REGION}"
aws cloudformation wait stack-delete-complete \
  --stack-name "${AR_STACK_NAME}" \
  --region "${AWS_REGION}"

# AWS side: the registry's IAM user + policies
aws iam delete-access-key --user-name "${AR_DEPLOYER_USER}" \
  --access-key-id "${AR_AWS_ACCESS_KEY_ID}"
aws iam detach-user-policy --user-name "${AR_DEPLOYER_USER}" \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryGeneralAccess"
aws iam detach-user-policy --user-name "${AR_DEPLOYER_USER}" \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart1"
aws iam detach-user-policy --user-name "${AR_DEPLOYER_USER}" \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart2"
aws iam delete-user --user-name "${AR_DEPLOYER_USER}"
aws iam delete-policy \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryGeneralAccess"
aws iam delete-policy \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart1"
aws iam delete-policy \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${AR_USER_PREFIX}-AgentRegistryBedrockAgentCoreAccessPart2"

# Cluster side: drop the aws.* helm values (re-applies the 001 baseline values;
# if /tmp/are-values.yaml is gone, recreate it from 001 step 4 first)
helm upgrade agentregistry-enterprise \
  oci://us-docker.pkg.dev/solo-public/agentregistry-enterprise/helm/agentregistry-enterprise \
  --version 2026.8.0 \
  --namespace agentregistry-system \
  -f /tmp/are-values.yaml \
  --wait --timeout 5m
kubectl rollout restart deployment/agentregistry-enterprise-server -n agentregistry-system
kubectl rollout status  deployment/agentregistry-enterprise-server -n agentregistry-system

# Local temp files + env vars
rm -f /tmp/agentregistry-cf.yaml /tmp/agentcore-runtime.yaml
unset AWS_ACCOUNT_ID AWS_REGION AWS_ROLE_ARN AWS_EXTERNAL_ID AR_AWS_ACCESS_KEY_ID AR_AWS_SECRET_ACCESS_KEY
unset AR_USER_PREFIX AR_DEPLOYER_USER AR_STACK_NAME AR_ROLE_NAME
```

> **Shared AWS account?** Part 1 prefixes every fixed name with `AR_USER_PREFIX` (`$(whoami)`),
> so two people in the same AWS account get `alice-agentregistry-deployer` and
> `bob-agentregistry-deployer` instead of colliding on one `agentregistry-deployer`. If the
> account also carries **unprefixed** resources (e.g. from a teammate's setup outside this
> workshop), they may be shared. Before deleting anything named exactly
> `agentregistry-deployer`, `AgentRegistryGeneralAccess`,
`AgentRegistryBedrockAgentCoreAccess`/`Part1`/`Part2`, or
> `agentregistry-access-role` (no prefix), confirm with whoever else might have a `Runtime`
> pointing at that role. Deleting it removes AgentCore access for everyone whose Runtime
> references that `roleArn`, not just you.
