---
name: field-rfe
description: Use when the user invokes /field-rfe to draft a customer-driven RFE/issue from context provided in local markdown files, using a local issue template.
---

# Field RFE Draft

## Overview

Drafts a customer-driven GitHub issue (RFE or bug) from raw context the user provides in one or more
local markdown files, plus a local issue template. The output is **always a draft** written to
`issue.md` in the working dir — never auto-filed.

**Core principle:** The template captures what the **customer** said and what the **field engineer**
observed. Do not paraphrase customer language, do not invent priorities/dates/dollar values, and do
not add AI-generated root-cause analysis or implementation suggestions to customer-facing sections.

## When to Use

- User types `/field-rfe` in a working directory containing a `template.md` and one or more context `*.md` files
- User asks something like "help me create an RFE issue from this context"

Not for:
- Updating an existing issue (this skill produces a new draft only)
- Filing issues without human review (no `gh issue create` — output is a markdown file)
- Issues with no customer signal (internal tech-debt RFEs, etc.)

## Inputs

The skill expects to find in the current working directory:

- **`template.md`** (required, exact filename) — the issue template to fill in. Section headings and HTML comments inside the template are the source of truth for structure and constraints.
- **One or more other `*.md` files** — context. The user drops in whatever they have: meeting notes, a conversation transcript, an email, a ticket export, anything relevant. Any non-`template.md` markdown file is treated as context.

If `template.md` is missing → stop and tell the user.
If no context files exist → ask the user where the customer signal is (path or paste).

## Output

A single file `issue.md` in the working dir, structured as:

1. **Title line** at top: `# [RFE] <short, specific description>` (or `# [Bug]` if the customer is reporting a defect rather than requesting a feature).
2. **HTML comment** with labels to apply when the issue is filed, e.g. `<!-- Labels to add: Customer: <Name>, <other-labels> -->`. Include `Customer: <Name>` always; include any other labels the user specified.
3. **Each template section**, in order, filled per the rules below.

The skill never runs `gh issue create`. The user reviews `issue.md` and files it themselves.

## Workflow

1. **Locate inputs.** Confirm `template.md` exists. Glob `*.md` (excluding `template.md` and `issue.md`) for context.
2. **Read template.** Note its sections and any HTML-comment instructions (e.g. "no AI-generated analysis", "bullet list under 150 chars", "add Customer: label").
3. **Read all context files.** Build a model of: customer name, what they literally said (quotable), who else is mentioned, any priority/$/date signals.
4. **Identify gaps.** For each template section, decide what context covers vs. what's missing. Common gaps: customer name, deal size, close date, priority, related issues, labels beyond `Customer:`, issue title.
5. **Ask for gaps, one at a time.** Use `AskUserQuestion` where a small option set fits; free-text questions for $ amounts, dates, free-form titles. Don't ask about anything context already covers. Don't batch — one question per turn.
6. **Draft `issue.md`** per the rules in the next section.
7. **Summarize.** Tell the user the file path, list any `<!-- TODO -->` markers left, and remind them to review before filing.

## Faithfulness Rules

The template typically separates **what the customer said** from **what the field engineer thinks**. Respect that distinction strictly.

**For customer-statement sections (e.g. "Customer Requirements", "Customer Priority and Relevant Dates"):**

- Quote or closely mirror the customer's own language. If they said "we're having to reauth every 24 hours", don't rewrite to "session lifetime is insufficient for production use".
- Do **not** invent priorities (P0/P1, "critical", "blocker") the customer didn't say.
- Do **not** invent dates, dollar values, deadlines, or renewal timelines.
- Do **not** add root cause analysis or implementation suggestions.
- If the customer said something ambiguous, ask the user — don't guess.

**For field-engineer sections (e.g. "Field Engineer Assessment", "Notes"):**

- The FE's interpretation, judgment, and synthesis are explicitly welcome here.
- Still ground claims in things observable from the context. Don't invent stakeholder positions.

**For "References" section:**

- Include real URLs the user provides. Don't fabricate source links — if the user only gave you a paste of the context, leave a `<!-- TODO: real source link -->` marker.

## Title Convention

`# [RFE] <Component>: <short specific ask>` — e.g. `[RFE] Eager OAuth: support refresh token flow for downstream third-party clients`.

Use `[Bug]` instead of `[RFE]` only if the customer is reporting broken behavior they expect to work, not asking for new behavior.

If unsure between RFE and Bug, ask the user.

## Asking for Gaps — Useful Patterns

Common fields to probe interactively when context doesn't supply them:

- **Customer name** — required for the `Customer:` label.
- **Issue type** — RFE vs. Bug.
- **Title** — propose one based on context and let the user accept or rewrite.
- **Priority / deal size / close date** — these often live in CRM, not in the context files. Ask once.
- **Additional labels** — the context may mention requested labels in passing. If so, propose them; otherwise ask.
- **Related issues** — internal references like "X also hit this" are worth surfacing as a question.
- **Source link** — if the context is a paste rather than a link, ask for the real URL.

Skip any question the context already answers.

## Common Mistakes

- **Paraphrasing customer requirements into "cleaner" language.** Defeats the purpose of the template. Quote them.
- **Filling in priority/dates/$ values the customer didn't state.** Don't. Ask the user or leave blank.
- **Auto-running `gh issue create`.** Never. Output is always a draft markdown file.
- **Batching all gap questions into one mega-prompt.** Ask one at a time — easier to answer.
- **Treating every non-template `.md` file as something to summarize.** They're context for understanding; you don't summarize them into the output, you extract quotes and facts.
- **Inventing labels.** Only include labels the user named or that the context explicitly requested.
- **Skipping the Title line.** Always include `# [RFE] ...` or `# [Bug] ...` at the top.

## Quick Reference

| Step | Action |
|---|---|
| 1 | Confirm `template.md` exists; glob other `*.md` as context |
| 2 | Parse template sections and HTML-comment rules |
| 3 | Read all context files |
| 4 | Identify gaps vs. template sections |
| 5 | Ask one question per gap, via `AskUserQuestion` where possible |
| 6 | Write `issue.md`: title → label comment → each template section |
| 7 | Summarize file path + leftover TODOs to the user |
