# Plugin Marketplace

You've published `changelog` and `field-rfe` to the catalog as individual `Skill` assets. In
practice teammates rarely want just one skill: they want the whole toolkit you've built up for
yourself, kept together and versioned as a unit. Publishing each skill separately means every
consumer has to know the full list and pull each one; bundle drift creeps back in exactly the way
single-file copies did before you started using the catalog at all.

`Plugin` is the Agentregistry catalog kind for that: a governed reference to a Claude Code plugin
bundle, meaning a `.claude-plugin/plugin.json` manifest plus whatever `skills/`, `commands/`,
`agents/`, or `hooks/` directories the bundle contains. Like `Skill`, the catalog stores a
reference to the bundle's source and resolves it on `apply`; unlike `Skill`, the unit you publish
and consume is the whole plugin, not one capability.

This lab publishes the `workshop-toolkit` plugin (`changelog` and `field-rfe` bundled together)
and walks the governance behavior a `Plugin` resource gets that a folder of files never did:
publish it, watch the controller resolve and pin its source, see the skill inventory the scan
extracts, and see what happens when a plugin's source is broken. It also covers the marketplace
compatibility feed that exposes Ready plugins to `claude plugin marketplace add`. The endpoint
registers and serves valid marketplace JSON on this build (with the correctly-prefixed env var),
but the feed's plugin list is always empty in `v2026.8.0`, so the final `install` step can't be
demonstrated yet.

## Lab Objectives

- Understand what a `Plugin` bundle is and how it differs from a `Skill`
- Inspect the `workshop-toolkit` bundle layout
- Publish the plugin with `arctl apply` and watch its `Ready` condition resolve
- Read the pinned commit, manifest, and skill inventory the controller populates in `status`
- List and inspect plugins with `arctl get plugin`
- See how a broken plugin source reports `Ready=False` instead of publishing silently
- Enable the marketplace compatibility feed and register it with `claude plugin marketplace add`, including its current known-issue state (empty feed) in `v2026.8.0`
- Clean up

## Pre-requisites

- [001 - Installation](../../001-installation.md) complete
- [Changelog Skill](changelog-skill.md) and/or [Field RFE Skill](field-rfe-skill.md) recommended
  (not required): this lab bundles both skills into one plugin
- Shell context:

```bash
export PATH=$HOME/.arctl/bin:$PATH
source ~/.are-keycloak-env
export AR_IP=$(kubectl get svc agentregistry-enterprise-server -n agentregistry-system \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}')
export ARCTL_API_BASE_URL="http://${AR_IP}:12121"
```

## 1. What a Plugin Is

A `Skill` catalog entry references one `SKILL.md`. A `Plugin` catalog entry references a whole
Claude Code plugin bundle: the directory shape Claude Code itself expects when you install a
plugin from a marketplace, a `.claude-plugin/plugin.json` manifest at the bundle root plus any
combination of `skills/`, `commands/`, `agents/`, `hooks/`, and `mcpServers/` the plugin ships.
The catalog controller clones the bundle's source, reads the manifest, and scans those
directories to build an inventory, the same way it reads one `SKILL.md`'s frontmatter for a
`Skill`, but for a whole plugin's worth of content at once.

This repo includes the bundle at
[`assets/plugins/workshop-toolkit/`](../../assets/plugins/workshop-toolkit/):

```bash
find assets/plugins/workshop-toolkit -type f
```

```
assets/plugins/workshop-toolkit/.claude-plugin/plugin.json
assets/plugins/workshop-toolkit/plugin.yaml
assets/plugins/workshop-toolkit/skills/changelog/SKILL.md
assets/plugins/workshop-toolkit/skills/field-rfe/SKILL.md
```

| File / dir | What it's for |
|---|---|
| `.claude-plugin/plugin.json` | The Claude Code plugin manifest: `name`, `description`, `version`, `author`. This is what the controller scans to populate `status.manifest`. |
| `skills/changelog/`, `skills/field-rfe/` | The two skills this plugin bundles, each a full `SKILL.md` (the same files the standalone skill labs publish individually). |
| `plugin.yaml` | The catalog manifest (`ar.dev/v1alpha1`, `kind: Plugin`): what `arctl apply` publishes. Points at the bundle's source rather than containing the bundle itself. |

Notice there's no `skill.yaml` anywhere under `skills/changelog/` or `skills/field-rfe/`: that
file is the catalog manifest for a *standalone* `Skill` asset (see [Changelog
Skill](changelog-skill.md)), not something a plugin bundle needs. Inside a plugin, a skill is
just a `SKILL.md`; the plugin's own `.claude-plugin/plugin.json` is the only manifest the bundle
carries.

`plugin.yaml`:

```yaml
apiVersion: ar.dev/v1alpha1
kind: Plugin
metadata:
  name: workshop-toolkit
  tag: "1.0.0"
spec:
  title: Workshop Toolkit
  description: The workshop's changelog and field-rfe skills bundled as one governed Claude Code plugin.
  harnesses: [claude-code]
  source:
    type: git
    git:
      repository:
        url: "https://github.com/ably77/solo-enterprise-agentregistry-workshop"
        branch: main
        subfolder: "assets/plugins/workshop-toolkit"
```

Same shape as a `Skill`'s `source.repository`: `url`, `branch`, `subfolder`. `spec.harnesses`
declares which agent harnesses the plugin targets: `claude-code` here, since this bundle is a
Claude Code plugin.

Check the catalog before publishing:

```bash
arctl get plugins
```

```
No plugins found.
```

## 2. Publish the Plugin

```bash
arctl apply -f assets/plugins/workshop-toolkit/plugin.yaml
```

```
✓ Plugin/workshop-toolkit (1.0.0) created
```

Unlike a `Skill`, publishing a `Plugin` isn't just registering a pointer: the controller
immediately clones the source and resolves it, validating the repo and branch exist, checking
that `subfolder` is a real path in the tree, and scanning the bundle for a manifest and content.
That resolution is asynchronous and shows up in `status`, not in the `apply` output. Watch it
settle:

```bash
arctl get plugin workshop-toolkit --tag "1.0.0" -o yaml
```

Right after `apply`, you may catch a transient state:

```yaml
status:
  conditions:
  - lastTransitionTime: "2026-08-27T17:38:28.727027421Z"
    message: resolving plugin source
    reason: Progressing
    status: "False"
    type: Ready
```

Within a few seconds it settles to `Ready=True`:

```yaml
apiVersion: ar.dev/v1alpha1
kind: Plugin
metadata:
  name: workshop-toolkit
  tag: 1.0.0
spec:
  description: The workshop's changelog and field-rfe skills bundled as one governed
    Claude Code plugin.
  harnesses:
  - claude-code
  source:
    git:
      repository:
        branch: main
        subfolder: assets/plugins/workshop-toolkit
        url: https://github.com/ably77/solo-enterprise-agentregistry-workshop
    type: git
  title: Workshop Toolkit
status:
  conditions:
  - lastTransitionTime: "2026-08-27T17:38:32.520248548Z"
    reason: Resolved
    status: "True"
    type: Ready
  inventory:
    skills:
    - description: Use when the user invokes /changelog to update CHANGELOG.md with
        the changes made in the current conversation, following the repo's existing
        version format and branch conventions.
      name: changelog
    - description: Use when the user invokes /field-rfe to draft a customer-driven
        RFE/issue from context provided in local markdown files, using a local issue
        template.
      name: field-rfe
  manifest:
    author:
      name: Agentregistry Workshop
    description: 'Workshop toolkit: the changelog and field-rfe skills as one governed
      plugin.'
    name: workshop-toolkit
    version: 1.0.0
  resolvedSource:
    commit: 10d5714158c701b8e14d46cc70937a475fb708f6
    type: git
```

> The `resolvedSource.commit` shown here will differ in your run: the controller pins the exact
> branch-tip commit at resolve time, so it's whatever `main` points to when you apply.

> **This plugin's content ships in this same repo**, so `plugin.yaml`'s `branch: main` only
> resolves once `assets/plugins/workshop-toolkit/` actually exists on `main`. Running from a
> fork or a branch where that path isn't on `main` yet? Edit `branch:` to your branch before
> applying; otherwise the Plugin sits at `Ready=False`/`SourceUnresolvable`, exactly the
> condition Section 4 demonstrates on purpose.

Notice in that status block:

- **`resolvedSource.commit` is a pinned SHA, not a moving branch reference.** The controller
  resolves `branch: main` to a concrete commit at reconcile time and records it. The plugin's
  content is frozen to that commit until you re-apply.
- **`inventory.skills` lists exactly the two skills the bundle contains** (`changelog` and
  `field-rfe`), each with the `name` and `description` read straight from that skill's `SKILL.md`
  frontmatter. Only categories the bundle has appear here; there's no `commands`,
  `agents`, `hooks`, or `mcpServers` key since this bundle has none of those.
- **`manifest` is populated from `.claude-plugin/plugin.json`**: `name`, `version`,
  `description`, `author`. If the controller can't find a manifest at all, this field is
  omitted (not an error) and `inventory` comes back empty.

## 3. List and Inspect Plugins

```bash
arctl get plugins
```

```
NAME               TAG     DESCRIPTION
workshop-toolkit   1.0.0   The workshop's changelog and field-rfe skills bundled as ...
```

The table form doesn't surface the `Ready` condition; use `-o yaml` (as above) for the
authoritative status. The plugin's detail page in the catalog UI mirrors this status information.

To author a plugin of your own, create the `.claude-plugin/plugin.json` and content directories
by hand following the layout in Section 1, then publish it with `arctl apply` the same way.

## 4. A Broken Plugin Source Fails Loudly

The controller has to resolve the bundle at publish time, and if it can't, the plugin stays
`Ready=False` instead of silently registering. Apply a plugin pointed at a subfolder that
doesn't exist in the repo:

```bash
arctl apply -f - <<'EOF'
apiVersion: ar.dev/v1alpha1
kind: Plugin
metadata:
  name: broken-demo
  tag: "1.0.0"
spec:
  title: Broken Demo
  description: Intentionally broken plugin source for the not-Ready demo.
  harnesses: [claude-code]
  source:
    type: git
    git:
      repository:
        url: "https://github.com/ably77/solo-enterprise-agentregistry-workshop"
        branch: main
        subfolder: "assets/plugins/does-not-exist"
EOF
```

```
✓ Plugin/broken-demo (1.0.0) created
```

The apply is accepted: the subfolder path is only tree-validated at reconcile time, not at
apply time. Check its status:

```bash
arctl get plugin broken-demo --tag "1.0.0" -o yaml
```

```yaml
status:
  conditions:
  - lastTransitionTime: "2026-08-27T17:45:04.137458715Z"
    message: 'resolve git source: subdirectory "assets/plugins/does-not-exist" not
      found in repository'
    reason: SourceUnresolvable
    status: "False"
    type: Ready
```

`Ready=False`, `reason: SourceUnresolvable`, and a message naming exactly what couldn't be
found. This settles within a few seconds and stays that way; there's no retry loop that
eventually succeeds. No `status.manifest` or `status.inventory` appears at all when resolution
fails this way. This is the governance the `Plugin` resource adds over a folder of files copied
by hand: a bad reference is visible in the catalog as a failed condition, not a plugin that
quietly doesn't work for whoever tries to use it.

> **Documented, not demonstrated here:** a not-Ready plugin (like `broken-demo`) is also meant to
> be excluded from the marketplace compatibility feed covered in the next section: only `Ready`
> plugins should appear in `marketplace.json`. That exclusion is documented controller
> behavior; on this build the feed's plugin list is always empty (see the known-issue callout
> below), so there's no populated feed to observe the exclusion against directly.

Clean up the broken demo; it was only here to show the failure path:

```bash
arctl delete plugin broken-demo --all-tags
```

```
Deleting all tags of plugin broken-demo...
Deleted: plugin/broken-demo (all tags)
```

## 5. Enable the Marketplace Compatibility Endpoint

Agentregistry can expose its `Ready` plugins as a `marketplace.json` feed that Claude Code's own
`claude plugin marketplace add` command understands, letting Claude Code treat the catalog as a
plugin marketplace directly, without anyone hand-copying bundle URLs around.

The endpoint is off by default; enable it with an environment variable on the server
Deployment, set with `kubectl set env` directly.

> **The variable needs the `AGENT_REGISTRY_` prefix.** The flag appears in release notes and in
> the binary's config struct as `PLUGIN_MARKETPLACE_COMPAT_ENABLED`, but the server's env parser
> prepends `AGENT_REGISTRY_` to every config field (the same reason the log level is
> `AGENT_REGISTRY_LOG_LEVEL`, not `LOG_LEVEL`). Setting the unprefixed name is silently ignored:
> the route never registers, `marketplace.json` falls through to the SPA's `index.html`, and
> nothing is logged.

```bash
kubectl set env deployment/agentregistry-enterprise-server -n agentregistry-system \
    AGENT_REGISTRY_PLUGIN_MARKETPLACE_COMPAT_ENABLED=true

kubectl rollout status deployment/agentregistry-enterprise-server -n agentregistry-system --timeout=180s
```

```
deployment.apps/agentregistry-enterprise-server env updated
Waiting for deployment "agentregistry-enterprise-server" rollout to finish: 1 old replicas are pending termination...
deployment "agentregistry-enterprise-server" successfully rolled out
```

Confirm the route registered. It now appears in the server's OpenAPI document and serves JSON:

```bash
curl -s "http://${AR_IP}:12121/openapi.json" | jq '[.paths | keys[] | select(contains("marketplace"))]'
curl -s "http://${AR_IP}:12121/plugin-marketplace/marketplace.json" \
    -w "\nSTATUS:%{http_code} TYPE:%{content_type}\n"
```

```
[
  "/plugin-marketplace/marketplace.json"
]
{"$schema":"https://json.schemastore.org/claude-code-marketplace.json","name":"agentregistry","owner":{"name":"agentregistry"},"plugins":[]}
STATUS:200 TYPE:application/json
```

> **Re-check this flag after any `helm upgrade`.** Because it's a direct `kubectl set env` patch
> rather than a Helm value, a later `helm upgrade` on this release can re-render the Deployment's
> `env:` list from the chart template and drop an out-of-band change like this one, depending on
> how the chart's Deployment template is structured. It happened to survive an upgrade during
> this lab's validation, but that isn't guaranteed: if you ever re-run `helm upgrade` on this
> release, re-check the flag and re-apply `kubectl set env` if it's gone.

Register the feed with Claude Code; `add` succeeds because the document is valid marketplace
JSON:

```bash
claude plugin marketplace add "http://${AR_IP}:12121/plugin-marketplace/marketplace.json"
claude plugin marketplace list
```

```
✔ Successfully added marketplace: agentregistry (declared in user settings)

  ❯ claude-plugins-official
    Source: GitHub (anthropics/claude-plugins-official)

  ❯ agentregistry
    Source: URL (http://172.18.255.251:12121/plugin-marketplace/marketplace.json)
```

> **Phase 1 scope:** this compatibility feed targets Claude Code specifically: it's a bare
> marketplace URL Claude Code's own `plugin marketplace add` consumes, not a general
> multi-harness plugin distribution mechanism.

### Known issue: the feed's plugin list is always empty in v2026.8.0

**On this build, `plugins` is always `[]`**, even with `workshop-toolkit` `Ready`, resolved to a
git commit, and visible via `arctl get plugins` / `/v0/plugins`. So `claude plugin install
workshop-toolkit@agentregistry` has nothing to install and the end-to-end demo stops here. This
has been root-caused as far as is possible from outside the closed-source enterprise wrapper and
reported to Solo engineering; there is no client-side workaround:

- The stored `Plugin` row satisfies every condition the OSS translation layer
  (`pkg/pluginmarketplace.FromPlugin`) checks: `Ready=True`, non-nil git `resolvedSource`,
  `observedGeneration` caught up with `generation`. It should be emitted.
- The endpoint never enforces authentication on this build: anonymous requests return `200` with
  the empty document (Solo's own upstream walkthrough expects **`401` for anonymous** and an
  identity-scoped feed fetched with a bearer token; Claude Code passes the token via a
  `headersHelper` in `extraKnownMarketplaces`). A valid superuser bearer token changes nothing:
  the `Authorization` header is ignored, so every request is evaluated as anonymous.
- The enterprise wrapper scopes the feed's list query with the same RBAC filter as the native
  read path, and for that anonymous identity the filter matches nothing: `AccessPolicy` grants
  (tested: wildcard-principal, exact role + exact plugin, and a `reader`-role policy that
  demonstrably unlocks `/v0/plugins` for the `reader` user) never affect the feed.

Once a fixed build wires the auth middleware into this route, the feed lists every `Ready` plugin
the caller's role can `registry:read` (not-Ready and OCI-sourced plugins stay excluded), and from
there `claude plugin install workshop-toolkit@agentregistry` installs the plugin the same way
installing from any other Claude Code marketplace works. Until then, the `Plugin` catalog
behavior in Sections 1–4 is unaffected and works as documented.

Remove the marketplace registration since there's nothing to install from it yet:

```bash
claude plugin marketplace remove agentregistry
```

## Cleanup

```bash
arctl delete plugin workshop-toolkit --all-tags
```

Optionally unset the marketplace compatibility flag if you don't want it left on for later labs:

```bash
kubectl set env deployment/agentregistry-enterprise-server -n agentregistry-system \
    AGENT_REGISTRY_PLUGIN_MARKETPLACE_COMPAT_ENABLED-
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `arctl apply` for a `Plugin` returns `✓ ... created` immediately, but `status` shows `Ready=False`/`SourceUnresolvable` shortly after | `apply` only validates structure (`url` present, `branch`/`commit` not both set, `commit` format). `subfolder` is only checked against the real repo tree at reconcile time, after the object is already created. | Fix the `subfolder`/`branch` in `spec.source.git.repository` and re-apply the same `metadata.name`/`tag`: `arctl apply` upserts in place (`configured`, not `created`). |
| `marketplace.json` returns `200 text/html` (the SPA `index.html`), not JSON | The enable flag was set **without** the `AGENT_REGISTRY_` prefix (release notes list it as bare `PLUGIN_MARKETPLACE_COMPAT_ENABLED`, but the server's env parser prefixes every config field); the route never registered. | Set `AGENT_REGISTRY_PLUGIN_MARKETPLACE_COMPAT_ENABLED=true` per Section 5 and confirm `/openapi.json` lists `/plugin-marketplace/marketplace.json`. |
| `claude plugin marketplace add <url>` fails with `Invalid marketplace schema from URL: : Invalid input: expected object, received string` | Direct consequence of the above: Claude Code received HTML where it expected a marketplace JSON object. | Same as above. |
| `marketplace.json` returns valid JSON but `plugins` is always `[]`, even with `Ready` plugins in the catalog and any `AccessPolicy` you grant | Known product bug in `agentregistry-enterprise` `v2026.8.0`: the compat route skips the auth middleware, so every request is evaluated as anonymous and the RBAC list filter matches nothing. See the known-issue callout in Section 5. | None available client-side; wait for a fixed build. |
| `AGENT_REGISTRY_PLUGIN_MARKETPLACE_COMPAT_ENABLED` is missing after a `helm upgrade` on the `agentregistry-enterprise` release | The flag was set with `kubectl set env` (a direct Deployment patch), not a Helm value; a chart re-render can drop it. | Re-run the `kubectl set env` command from Section 5. |

## Next

- [Changelog Skill](changelog-skill.md) / [Field RFE Skill](field-rfe-skill.md) - the two skills this plugin bundles, published individually as `Skill` assets
- [Prompts](prompts.md) - the inline text catalog asset, also managed with `arctl apply`
- [AccessPolicy / RBAC](../access-control/access-policies.md) - grant `registry:read` / `registry:write` on `plugin`
- [Approval Workflows](../access-control/approval-workflows.md) - gate catalog submissions behind admin approval
