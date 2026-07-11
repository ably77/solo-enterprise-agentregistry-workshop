# Cleanup

> **AWS Bedrock AgentCore series**
> [Part 1: Integrate Agentregistry and AgentCore](agentcore-01-integration.md) ·
> [Part 2: Create Agents](agentcore-02-create-agents.md) ·
> [Part 3: Register and Deploy Agents to AgentCore](agentcore-03-deploy-agents.md) ·
> [Part 4: Approval-Gated Agent Onboarding](agentcore-04-approval-onboarding.md) ·
> [Part 5: Route LLM and Registry-Managed MCP Through Agentgateway](agentcore-05-agentgateway-llm-mcp.md) ·
> **Cleanup** (this doc)

Every teardown step for the series, in one place. Run the sections below **top to bottom**, and
skip any section for a part you never did.

> **Order matters.** Deployments and catalog entries (Parts 3–5) must go before the Runtime
> and AWS integration they depend on (Part 1) — a `Deployment` can't be deleted cleanly once its
> `Runtime` is gone, and Part 1's cross-account role is what Parts 3–5's deploys assumed to
> exist. If you're only part-way through the series, just run the sections for the parts you
> completed, in this order.

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
  --version 2026.6.2 \
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
```

> AgentCore also leaves behind each runtime's CloudWatch log group; remove them with
> `aws logs delete-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT" --region "${AWS_REGION}"`
> if you want a fully clean account.

## If you completed Part 1 (Integrate Agentregistry and AgentCore)

This tears down the AgentCore integration itself: the `agentcore` Runtime, the cross-account role
stack, the deployer IAM user, and the `aws.*` helm values. Run it only once everything in the
sections above (if applicable) is gone — a `Deployment` still targeting this Runtime will block or
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
  --version 2026.6.2 \
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

> **Shared AWS account, or cleaning up an older install?** As of this revision, Part 1 prefixes
> every fixed name with `AR_USER_PREFIX` (`$(whoami)`), so two people in the same AWS account get
> `alice-agentregistry-deployer` and `bob-agentregistry-deployer` instead of colliding on one
> `agentregistry-deployer`. If you (or a teammate) set this up **before** that change, the
> unprefixed names may still exist and may be shared — before deleting anything named exactly
> `agentregistry-deployer`, `AgentRegistryGeneralAccess`,
`AgentRegistryBedrockAgentCoreAccess`/`Part1`/`Part2`, or
> `agentregistry-access-role` (no prefix), confirm with whoever else might have a `Runtime`
> pointing at that role. Deleting it removes AgentCore access for everyone whose Runtime
> references that `roleArn`, not just you.
