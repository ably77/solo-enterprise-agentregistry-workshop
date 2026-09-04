# Gateway-Bound Runtime: Policy Enforcement and Tracing

> **AWS Bedrock AgentCore series, Part 6 of 6**
> [Part 1: Integrate Agentregistry and AgentCore](agentcore-01-integration.md) ·
> [Part 2: Create Agents](agentcore-02-create-agents.md) ·
> [Part 3: Register and Deploy Agents to AgentCore](agentcore-03-deploy-agents.md) ·
> [Part 4: Approval-Gated Agent Onboarding](agentcore-04-approval-onboarding.md) ·
> [Part 5: Route LLM and Registry-Managed MCP Through Agentgateway](agentcore-05-agentgateway-llm-mcp.md) ·
> **Part 6: Gateway-Bound Runtime: Policy Enforcement and Tracing** (this lab) ·
> [Cleanup](agentcore-cleanup.md)

Part 5 pointed one agent's LLM and MCP traffic at an in-cluster Agentgateway you deployed by
hand with a plain Kubernetes manifest. This lab is a different mechanism: the registry can
**own and run a Gateway of its own**, bind an entire AgentCore `Runtime` to it, and use that
binding as a policy chokepoint. A `RuntimeAccessPolicy` gates which deployments an agent may
reach, and a tracing path rides the same bound connection with no code or env-var changes to
the agent. You'll create the registry-managed Gateway, bind `Runtime/agentcore` to it, author a
`RuntimeAccessPolicy`, and inspect the built-in tracing pipeline it unlocks.

This is a **read-heavy** lab. The full enforcement and tracing experience (an agent calling
through the bound gateway, a denied tool call, a trace landing in the collector) requires AWS
to be able to reach your gateway's LoadBalancer, exactly like Part 5's "requires a publicly
reachable gateway" stance. On a managed cluster with a public LB (EKS/GKE/AKS) every step in
this lab completes end-to-end. On a local cluster (kind, vcluster) the registry-side mechanics
(Gateway creation, Runtime binding, policy authoring, the tracing wiring) all work identically;
you just won't see AWS-side traffic land, because AWS can't dial back in. Steps that depend on
that reachability are called out explicitly, with the state you'll actually observe on a local
cluster instead of invented output.

> **Cost note:** this lab makes no new AWS-billable calls beyond what Parts 1–5 already run:
> no new Bedrock/OpenAI invocations, no new AgentCore runtimes. It reuses `Runtime/agentcore`
> from Part 1 and (optionally) `econresearch-agw`/`fred-incluster-agw` from Part 5. The only new
> AWS-side object is a small AWS AppConfig application the registry provisions automatically
> when you bind the Gateway; it costs nothing meaningful, but [Cleanup](agentcore-cleanup.md)
> does not remove it: the application and its configuration profile persist after teardown,
> inert and free-tier-scale. See Part 6 in [Cleanup](agentcore-cleanup.md) for an optional
> manual removal.

## Lab Objectives

- Create a registry-managed `Gateway` (`mode: discover`) and read its status: LB address,
  listeners (including the `connect` tunnel acceptor and the `otlp-http` collector route)
- Understand how this Gateway differs from Part 5's Helm-manifest workshop gateway: same
  `gatewayClass`, different owner and lifecycle
- Bind `Runtime/agentcore` to the Gateway via `spec.config.gatewayRef` and read the AWS
  AppConfig egress payload the bind pushes, live, with no redeploy
- Author a `RuntimeAccessPolicy` gating a deployment behind the bound Gateway, see it accepted,
  edit it, and understand exactly when (and when not) it enforces
- Trace the built-in, ClickHouse-backed telemetry pipeline the bound Gateway's `otlp-http`
  listener feeds, and see why there is no `OTEL_EXPORTER_OTLP_*` env var to look for
- Unbind and tear down cleanly, and recognize the two harmless "what you'll see" states cleanup
  leaves behind

## Pre-requisites

- [Part 1: Integrate Agentregistry and AgentCore](agentcore-01-integration.md) complete and
  **not cleaned up**: `arctl get runtimes` shows `agentcore`.
- [Part 3: Register and Deploy Agents to AgentCore](agentcore-03-deploy-agents.md) complete:
  at least one AgentCore Deployment exists to reason about.
- [Part 5: Route LLM and Registry-Managed MCP Through Agentgateway](agentcore-05-agentgateway-llm-mcp.md)
  **recommended**, not required: it supplies `econresearch-agw` and `fred-incluster-agw`, which
  this lab's `RuntimeAccessPolicy` example targets. Without Part 5, read section 3 for the
  schema and substitute your own `Deployment` names.
- A **publicly reachable** Agentgateway LoadBalancer, same requirement as Part 5, if you want
  the enforcement and tracing outcomes to happen rather than just be described. Local
  clusters: read along, every command still runs, section 3's denial callouts and section 4's
  trace-arrival callout won't complete.
- Your shell context (re-run in every new shell you use for this lab):

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"

export AWS_REGION=us-east-1   # must match the region you used in Part 1
export AR_USER_PREFIX=$(whoami)   # matches the prefix Part 1 used for shared-account naming
```

**Time:** ~25–35 minutes. Mostly reading and cluster-side `apply`/`get` commands; no new
AWS resources beyond a small AppConfig application, and no new build/deploy cycle.

## 1. The Gateway You Run

Every prior lab used a Gateway you created by hand with a plain Kubernetes manifest
(`kubectl apply -f parent-gateway-and-route.yaml` in Part 5). The registry can also **create and
own a Gateway itself**, reconciling it the same way it reconciles Agents and Deployments. That's
the `Gateway` catalog kind, `mode: discover`: point it at a `Runtime` and a Kubernetes
`gatewayClass`, and the registry stands up an Agentgateway deployment for you.

```bash
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: Gateway
metadata:
  name: ${AR_USER_PREFIX}-part6-gateway
spec:
  mode: discover
  runtimeId: agentcore
  kubernetes:
    gatewayClass: enterprise-agentgateway
  selector:
    labels:
      agentregistry.solo.io/gateway: ${AR_USER_PREFIX}-part6-gateway
EOF
```

`mode: discover` is one of two accepted values (`discover` | `managed`; `managed` is the
AWS EC2-hosted path with its own `sts`/`aws` config block, out of scope here). On the `discover`
path, `kubernetes.gatewayClass` + `selector.labels` stand in for the `networkId`/`subnetId` pair
that AWS-mode Gateways require: the registry doesn't need a VPC to reconcile a Kubernetes
object.

Within a few seconds, `arctl get gateway ${AR_USER_PREFIX}-part6-gateway -o yaml` reports
`status.phase: ready` with a full `GatewayAPIGatewayStatus`:

```yaml
status:
  phase: ready
  platform: kubernetes
  kubernetes:
    addresses:
      - type: IPAddress
        value: <gateway-lb-address>
    conditions:
      - type: Accepted
        status: "True"
        reason: Accepted
      - type: Programmed
        status: "True"
        reason: Programmed
        message: Successfully programmed Gateway
    listeners:
      - name: connect
        attachedRoutes: 0
        supportedKinds: [HTTPRoute, GRPCRoute]
      - name: https
        attachedRoutes: 0
      - name: http
        attachedRoutes: 0
      - name: otlp-http
        attachedRoutes: 1
```

The `connect` and `otlp-http` listeners have no counterpart on Part 5's gateway, and the rest
of this lab runs through them:

- **`connect`** (port 8443, TLS): the tunnel acceptor. This is what an AWS-side AgentCore
  runtime dials into once its egress is redirected here, the mechanism you'll see the wiring
  for in section 2.
- **`otlp-http`** (port 4318): already has one attached route the moment the Gateway comes up,
  the telemetry route covered in section 4.

`kubectl get pods -A | grep part6-gateway` shows the agentgateway pod the registry spun up,
running in `agentregistry-system`.

> **Two planes, same `gatewayClass`.** This Gateway and Part 5's `agentregistry-gateway` share
> `gatewayClassName: enterprise-agentgateway`, but they are two independent Gateway API objects
> with different owners and lifecycles: Part 5's is a plain manifest you `kubectl apply`/`delete`
> yourself, lives in `agentgateway-system`, and exposes only an `http` listener. This one is
> **registry-owned**: the registry's reconciler created it, it lands in `agentregistry-system`,
> carries the extra `connect`/`otlp-http` listeners this lab needs, and is provisioned with
> internet-facing AWS load-balancer annotations (`aws-load-balancer-scheme: internet-facing`) on
> a real cluster, because it's designed to be dialed into from AWS. Pointing `selector.labels`
> at the same label the Part 5 gateway carries does **not** adopt it: you get a second Gateway
> API object, not a shared one. Treat these as two separate gateways serving two separate labs'
> traffic, even on the same cluster.

## 2. Bind the Runtime

A `Gateway` existing on its own does nothing for `Runtime/agentcore`. The link is one field on
the Runtime, `spec.config.gatewayRef`:

**Before** (`arctl get runtime agentcore -o yaml`, `spec.config` has no `gatewayRef`):

```yaml
spec:
  type: BedrockAgentCore
  config:
    region: us-east-1
    roleArn: arn:aws:iam::<account-id>:role/${AR_USER_PREFIX}-AgentRegistryAccessRole
    externalId: <external-id>
```

Patch it in:

```bash
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: Runtime
metadata:
  name: agentcore
spec:
  type: BedrockAgentCore
  config:
    region: ${AWS_REGION}
    roleArn: arn:aws:iam::<account-id>:role/${AR_USER_PREFIX}-AgentRegistryAccessRole
    externalId: <external-id>       # unchanged from Part 1
    gatewayRef:
      name: ${AR_USER_PREFIX}-part6-gateway
EOF
```

`gatewayRef` is a small object (`LocalObjectRef`: `name`, optional `namespace`/`kind`), not a
plain string; a bare string value fails apply with a Go unmarshal error. **After**, the Runtime
gains an explicit condition:

```yaml
status:
  conditions:
    - type: AgentEgressReady
      status: "True"
      reason: PolicyPublished
      message: Runtime egress policy is published
```

The bind is picked up immediately: the registry server logs the gateway pipeline noticing a new
bound runtime the moment the patch lands:

```
{"level":"warn","msg":"gateway has no actor-JWT policy: no bound runtime advertises an actor IdP","component":"gateway-pipeline","gateway_ref":"default/<gateway-name>","bound_runtimes":1}
```

(`bound_runtimes` flips `0` → `1` on the patch. The warning itself is about a separate
actor-identity feature this lab doesn't configure, not a failure.)

The bind pushes a real AWS AppConfig hosted configuration version, with no agent redeploy:

```bash
aws appconfig list-applications --region "${AWS_REGION}" --query "Items[*].[Id,Name]" --output table
# one application, named ar-<hash>: "Agentregistry configuration for namespace agentregistry-system"

aws appconfig list-configuration-profiles --region "${AWS_REGION}" --application-id <app-id>
# one profile per bound Runtime: runtime-<runtime-uid>-egress
```

```bash
aws appconfig get-hosted-configuration-version --region "${AWS_REGION}" \
  --application-id <app-id> --configuration-profile-id <profile-id> \
  --version-number <n> out.json
```

```json
{
  "egress": {
    "defaultGateway": { "address": "<gateway-lb-address>", "port": 8443 },
    "defaultAction": "passthrough",
    "rules": [
      { "hosts": ["telemetry.agentregistry.internal"], "action": "redirect", "protocols": ["http"] }
    ]
  },
  "gatewayTLS": { "serverName": "<gateway-name>.default" }
}
```

`defaultGateway.address` is exactly this Gateway's own LB address from section 1, on the
`connect` listener's port (8443). This one payload is the whole egress mechanism: it tells the
AWS-side agent-proxy fronting every AgentCore runtime "any traffic that isn't otherwise routed,
and specifically anything to `telemetry.agentregistry.internal`, goes through this gateway
instead of straight out to the internet." Re-binding to a differently-named Gateway bumps the
hosted configuration version and rewrites the address/`serverName`: this is live per-bind
state, not something cached from install time.

Unbinding (re-`apply` the Runtime with `gatewayRef` omitted) reverts the AppConfig payload to
`{"egress":{"defaultAction":"passthrough"}}` and flips the condition:

```yaml
- type: AgentEgressReady
  status: "False"
  reason: GatewayRefRemoved
  message: gatewayRef was removed; RAP destinations are denied until capture-enabled Agents
    are redeployed
```

Keep that message in mind for section 5: it's expected, not a bug, when you tear this lab down.

## 3. RuntimeAccessPolicy

With the Runtime bound to a Gateway, you can author a `RuntimeAccessPolicy` (RAP): a rule that
says which deployment (or role) may reach which destination, and restricts a destination so
it's only reachable **through** the bound gateway.

`RuntimeAccessPolicySpec` is `{rules: []AccessRule}`, and each `AccessRule` is `{from: []FromRef,
to: []ToRef}`:

| | `kind` accepts | notes |
|---|---|---|
| `FromRef` | `Deployment` \| `Role` | plus `onBehalfOf.roles: []string` |
| `ToRef` | `Deployment` \| `MCPServer` | plus `inboundAccess` and `mcpTools: []string` |

`inboundAccess` on a `to` entry takes exactly two live values: unset (default, open) or
`GatewayOnly`. There is no separate top-level "enforcement mode" field: the gate is per
destination, inside the rule that names it.

> **`Agent` is not a valid `from`/`to` kind.** Both `FromRef.kind` and `ToRef.kind` are
> validated against `Deployment`/`Role` and `Deployment`/`MCPServer` respectively; naming an
> `Agent` (the catalog/design-time resource) instead of a `Deployment` (the running instance) is
> rejected outright (`unknown from kind "Agent" (must be "Deployment" or "Role")`). A RAP
> targets the running Deployment, never the catalog entry it was published from.

Author the example this lab uses throughout: `econresearch-agw` (Part 5's gateway-routed agent)
allowed to reach `fred-incluster-agw`'s FRED tools, but only for two of its three tools and
only via the gateway:

```bash
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: RuntimeAccessPolicy
metadata:
  name: ${AR_USER_PREFIX}-part6-rap
spec:
  rules:
    - from:
        - kind: Deployment
          name: econresearch-agw
          onBehalfOf: { roles: [are-admins] }
      to:
        - kind: Deployment
          name: fred-incluster-agw
          inboundAccess: GatewayOnly
          mcpTools: [fred_search, fred_get_series]
EOF
```

`arctl apply --dry-run` on the same manifest accepts it before you commit; the real apply returns
in about a second. The RAP object itself reports back `status: {}`. There's no compiled-policy
detail surfaced on the RAP; the effects live on the objects it references, which is what the
rest of this section verifies.

**Edit round-trip.** Narrow the allowed tools by dropping one:

```bash
arctl apply -f - <<EOF
apiVersion: ar.dev/v1alpha1
kind: RuntimeAccessPolicy
metadata:
  name: ${AR_USER_PREFIX}-part6-rap
spec:
  rules:
    - from:
        - kind: Deployment
          name: econresearch-agw
          onBehalfOf: { roles: [are-admins] }
      to:
        - kind: Deployment
          name: fred-incluster-agw
          inboundAccess: GatewayOnly
          mcpTools: [fred_search]
EOF
```

The edit is accepted immediately (`updatedAt` bumps); a fresh reconcile is forced on
`fred-incluster-agw` the moment any RAP references it: you'll see a
`reconcile.agentregistry.dev/force: <rap-name>/<token>` annotation and a matching
`status.details.deploymentController.lastForceToken` field appear on the target Deployment.
That's the registry telling the deployment controller "re-evaluate now, a policy that names you
just changed". It's normal, not drift.

### The hard gate only engages for gateway-routed targets

**`GatewayOnly` and `mcpTools` only have anything to enforce against a destination that is
routed through the bound Gateway.** `fred-incluster-agw` (from Part 5) is deployed against the
`virtual-default` Runtime and exposed through the Helm-manifest workshop gateway, not through
`${AR_USER_PREFIX}-part6-gateway` or `Runtime/agentcore`. Naming it in a RAP is accepted (the
registry doesn't reject a `to` target for belonging to a different Runtime), but the
enforcement pipeline has nothing to compile the policy onto.

Live server-side signals confirm this at each end of the binding:

**With no `gatewayRef` bound**, the gateway pipeline skips the RAP outright before it evaluates
anything:

```
{"level":"warn","msg":"skip runtime access policy: runtime/gateway chain unresolvable","component":"gateway-pipeline","policy":"default/<rap-name>","runtime":{"Namespace":"default","Name":"agentcore"},"reason":"runtime has no gatewayRef"}
```

**With `gatewayRef` bound** (section 2), the pipeline gets further but still can't resolve the
target, because `fred-incluster-agw` isn't wired to this Runtime's gateway at all:

```yaml
status:
  conditions:
    - type: AgentEgressReady
      status: "False"
      reason: TargetResolutionFailed
      message: 'resolve egress target Deployment/fred-incluster-agw: target missing'
```

`TargetResolutionFailed` is more specific than "unenforced": the registry isn't silently
allowing the call, it's telling you the RAP references a destination its egress-resolution
pipeline structurally cannot reach from this Runtime's gateway. To make `GatewayOnly` actually
gate `fred-incluster-agw`'s traffic, the FRED MCP server would need a `Deployment` attached to
`${AR_USER_PREFIX}-part6-gateway` (i.e. to the `agentcore`-associated Gateway), not to
`virtual-default`.

> **Allowed and denied tool calls: reachable-cluster-only.** On a cluster with a publicly
> reachable gateway and a `Deployment` actually routed through it, this is where you'd chat with
> `econresearch-agw` and watch `fred_search` succeed (it's in `mcpTools`) while a call using a
> tool you removed from the list comes back as a policy denial from the gateway itself: a
> CEL-authz rejection keyed off the same JWT/subject-role metadata the gateway already compiles
> onto its routes. This workshop's local cluster can't complete that round trip (section 3's
> finding above is why, independent of the reachability gap), so there's no captured
> terminal output to show here; treat the mechanism above as what you're verifying if you have a
> reachable cluster to try it on.

## 4. End-to-End Tracing

You might expect the bound Gateway to inject an `OTEL_EXPORTER_OTLP_ENDPOINT` env var into the
agent's container so its SDK knows where to export spans. **It doesn't; check for yourself:**

```bash
aws bedrock-agentcore-control get-agent-runtime --region "${AWS_REGION}" \
  --agent-runtime-id <econresearch-agw-runtime-id> --query environmentVariables
```

Before and after binding `gatewayRef` and redeploying the agent, the environment is identical:
only `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` are present (baked in at deploy time
regardless of any gateway binding). No `OTEL_EXPORTER_OTLP_ENDPOINT`, no `OTEL_EXPORTER_OTLP_PROTOCOL`,
no new variable of any kind shows up.

> **Release-notes discrepancy.** The `v2026.8.0` release notes describe OTel export as
> environment-variable injection into the runtime. That is not what this environment observed:
> binding the gateway and redeploying left the runtime's env untouched. Treat the mechanism
> below, confirmed live, as the one to design against, and the release notes' env-var
> description as unverified for this release.

The real mechanism is the AppConfig egress rule from section 2:

```json
"rules": [
  { "hosts": ["telemetry.agentregistry.internal"], "action": "redirect", "protocols": ["http"] }
]
```

Any traffic the agent-proxy sees addressed to `telemetry.agentregistry.internal` gets redirected
through `defaultGateway` (this Gateway's `connect` tunnel listener) instead of trying to reach
that (non-resolvable) hostname directly. There is no client-side endpoint to configure because
the redirect happens at the network layer between the agent and the internet, not in the agent's
process.

The rest of the wiring was already running, or already attached, the moment your Gateway came
up in section 1:

**The `otlp-http` listener's route**, forwarding to the registry's built-in collector:

```bash
kubectl get httproute -n agentregistry-system | grep telemetry
```

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gw-rt-telemetry-default-<gateway-name>-<hash>
  namespace: agentregistry-system
spec:
  hostnames: [telemetry.agentregistry.internal]
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: <gateway-object-name>
      sectionName: otlp-http
  rules:
    - backendRefs:
        - kind: Service
          name: agentregistry-enterprise-telemetry-collector
          port: 4318
      matches:
        - path: {type: PathPrefix, value: /}
status:
  parents:
    - conditions:
        - {type: Accepted, status: "True"}
        - {type: ResolvedRefs, status: "True"}
```

**The collector itself**, already deployed by the enterprise Helm chart, ClickHouse-backed:

```bash
kubectl get deploy -n agentregistry-system agentregistry-enterprise-telemetry-collector
```

Its pipeline config (`ConfigMap/agentregistry-enterprise-telemetry-collector-config`, key
`relay`) receives OTLP on 4317 (gRPC) and 4318 (HTTP), and exports traces, logs, and metrics into
ClickHouse tables (`otel_traces_json`, `otel_logs_json`, `otel_metrics_*`).

Put together, the full path is: agent emits a span → AWS-side agent-proxy egress-redirects the
export call per the AppConfig rule → your bound Gateway's `connect` listener (tunnel) →
internally, the `otlp-http` listener → this `HTTPRoute` → the collector → ClickHouse. Every hop
except the first is something you just inspected directly on your cluster.

> **Reading an actual trace: reachable-cluster-only.** Everything above is live wiring; what's
> missing on this workshop's local cluster is the first hop happening at all: AWS reaching back
> into the cluster to make the redirect connection. On a reachable cluster, after a chat turn
> with a gateway-bound agent, you'd query ClickHouse's `otel_traces_json` (or the registry UI's
> trace view, if exposed) and find a trace whose resource attributes include
> `agentregistry.deployment.name=<your-deployment>` (the same value baked into
> `OTEL_RESOURCE_ATTRIBUTES` above), with spans for the LLM call and each MCP tool call nested
> under it. That query itself isn't shown here because there's no local trace to query.

## 5. Unbind and Teardown

Full teardown commands (deleting the RAP, unbinding `gatewayRef`, and deleting the Gateway, in
that order) live in
[Cleanup: "If you completed Part 6"](agentcore-cleanup.md#if-you-completed-part-6-gateway-bound-runtime-policy-enforcement-and-tracing).
Run that before tearing down Part 1's integration; a bound Runtime should be unbound before its
Gateway disappears out from under it.

Two states you'll see there are expected, not failures:

- **`AgentEgressReady: False`, `reason: GatewayRefRemoved`** on `Runtime/agentcore` the moment
  you remove `gatewayRef`. This is the same condition section 2 showed you going the other
  direction: the registry is correctly reporting that any RAP destinations bound through this
  gateway are now unreachable until you redeploy or rebind, not surfacing a bug.
- **A stale `lastForceToken` on `fred-incluster-agw`.** Deleting the RAP does not clear
  `status.details.deploymentController.lastForceToken` on the Deployment it referenced: that
  field is a historical audit marker ("what last forced a reconcile on this object"), not
  current desired state. It stays pointing at your deleted RAP's name and token indefinitely,
  harmlessly, until some other force-reconcile event overwrites it. The Deployment's health
  (`Ready: True`, `DeployedViaAgentgateway`) is unaffected throughout; this residue is not a
  cleanup failure.

## Next

- The `mode: managed` Gateway path (AWS EC2-hosted gateway + companion token-issuing service) is
  the production answer for the reachability requirement this lab and Part 5 both call out: the
  gateway runs *in* AWS, so nothing needs to dial back into your cluster.
- Combine this lab's `RuntimeAccessPolicy` with Part 4's approval workflow: gate a newly
  onboarded agent's tool access with `GatewayOnly` from the moment its Deployment goes live,
  instead of adding the policy after the fact as this lab did.

## Summary

- A registry-managed `Gateway` (`mode: discover`) is a distinct, registry-owned Gateway API
  object: same `gatewayClass` as Part 5's workshop gateway, different namespace, owner, and
  listener set, including the `connect` tunnel acceptor and `otlp-http` collector route that
  make this lab's mechanisms possible.
- Binding `Runtime/agentcore` to it via `spec.config.gatewayRef` is a live, no-redeploy switch:
  it immediately pushes an AWS AppConfig egress payload naming the Gateway's address as the
  runtime's default egress hop and telemetry redirect target.
- `RuntimeAccessPolicy` gates `Deployment`/`MCPServer` destinations (never `Agent`) behind
  `inboundAccess: GatewayOnly` and a `mcpTools` allowlist, but only for destinations actually
  routed through the bound Gateway; a target on a different Runtime's gateway comes back
  `TargetResolutionFailed`, not silently permissive.
- Tracing rides the same bound connection, not an injected `OTEL_EXPORTER_OTLP_*` env var: the
  AppConfig redirect rule for `telemetry.agentregistry.internal`, the Gateway's `otlp-http`
  listener, and its `HTTPRoute` to the built-in ClickHouse-backed collector are all live,
  inspectable wiring, independent of whether AWS can currently complete the first hop.
- The full enforcement and trace-arrival experience needs a publicly reachable gateway, same as
  Part 5; this lab shows you every piece of the mechanism regardless, and exactly what
  `arctl`/`kubectl` state to expect once that reachability exists.
