---
name: changelog
description: Use when the user invokes /changelog to update CHANGELOG.md with the changes made in the current conversation, following the repo's existing version format and branch conventions.
---

# Changelog

## Overview

Updates `CHANGELOG.md` in the current repo with a concise entry describing the changes made during
the conversation. The entry is **always shown to the user for confirmation before it is written** —
the skill never edits the changelog silently.

**Core principle:** Match the changelog that already exists. Reuse its version format, its date
format, and its bullet style. Do not invent a new structure, and do not pad entries with filler.

## When to Use

- User types `/changelog` in a repo that has (or should have) a `CHANGELOG.md`
- User asks something like "add these changes to the changelog"

Not for:
- Repos with no `CHANGELOG.md` — the skill stops and says so rather than creating one unprompted
- Rewriting historical entries (this skill only adds the current conversation's changes)

## Workflow

1. **Check for `CHANGELOG.md`** in the current working directory. If it does not exist, say
   `No CHANGELOG.md found in this repo — skipping.` and stop.
2. **Get the current branch** with `git branch --show-current`.
3. **Read `CHANGELOG.md`** to learn the version format and find the latest version entry.
4. **Decide where the entry goes, based on the branch:**
   - **On `main` / `master`:** increment the patch version (e.g. `0.11.3` → `0.11.4`), use today's
     date in `M-DD-YY` format (e.g. `3-13-26`), and insert a new versioned entry at the top.
   - **On any other branch:** append the new bullets to the latest existing version entry. Do **not**
     create a new version entry or an `Unreleased` section.
5. **Write the entry** from the changes made this conversation. Follow the style of existing
   entries — short imperative bullets, include file paths or demo names where relevant. No filler.
6. **Show the user the new entry and confirm** it looks right before writing it.

## Style Rules

- Imperative mood: "Add X", "Fix Y", "Rename Z" — not "Added" or "This change adds".
- One change per bullet. Reference concrete paths (`labs/catalog/prompts.md`) when it aids the reader.
- Keep it to what actually changed. Omit routine churn the reader does not need.
- Never reformat or reorder existing entries; only add to them.

## Common Mistakes

- **Creating a `CHANGELOG.md` when none exists.** Stop and tell the user instead.
- **Writing a new version entry while on a feature branch.** Append to the latest entry instead.
- **Writing the entry without confirmation.** Always show it first.
- **Padding with filler** ("various improvements", "misc fixes"). State the actual change or omit it.

## Quick Reference

| Step | Action |
|---|---|
| 1 | Confirm `CHANGELOG.md` exists; stop if not |
| 2 | `git branch --show-current` |
| 3 | Read changelog: version format + latest entry |
| 4 | `main`/`master` → new patch entry at top; else → append to latest entry |
| 5 | Draft bullets from this conversation, matching existing style |
| 6 | Show the user, confirm, then write |
