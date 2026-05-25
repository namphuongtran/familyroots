# sync-claude-md Skill Design

**Date:** 2026-04-18
**Status:** Approved
**Scope:** Claude Code skill for automated CLAUDE.md drift detection and synchronization

---

## 1. Overview

`sync-claude-md` is a Claude Code skill that detects documentation drift between repository state and CLAUDE.md files, proposes targeted updates, and applies approved changes with a descriptive commit.

It fills the gap between the existing manual `update-knowledge` command (session-scoped, user-driven) and the heavy `setup-knowledge` bootstrap (full scan). This skill is incremental, autonomous, and git-aware.

## 2. Skill Identity

- **Name:** `sync-claude-md`
- **Location:** `.claude/skills/sync-claude-md/SKILL.md`
- **Thin command:** `.claude/commands/sync-claude-md.md` (one-liner invoking the skill)
- **Trigger phrases:** "update claude.md", "sync claude.md", "review claude documentation", "refresh repo knowledge", "update ai context"

### When to Run

- After major feature implementation
- After architecture changes (new ADR, new contract, new service)
- After new service/module added
- Before merging large PRs
- During release preparation
- When explicitly requested

### Inputs

None required. The skill derives everything from git state and repo structure.

### Outputs

- Summary of detected changes (change manifest)
- Proposed CLAUDE.md updates (with diffs)
- Stale knowledge index warnings (informational only)
- Commit with descriptive message (after approval)

## 3. Architecture: Three-Phase Layered Analysis

```
Phase 1: DETECT          Phase 2: ANALYZE           Phase 3: APPLY
┌──────────────────┐    ┌───────────────────────┐   ┌──────────────────────┐
│ git diff main    │    │ Read target CLAUDE.md │   │ Present proposals    │
│ git status       │───>│ Per-category analysis │──>│ Batch approve UI     │
│ Classify files   │    │ Cross-cutting detect  │   │ Surgical edits       │
│ Change manifest  │    │ Stale content check   │   │ Commit (no push)     │
└──────────────────┘    │ Generate proposals    │   │ Final report         │
                        └───────────────────────┘   └──────────────────────┘
```

## 4. Phase 1 — Detect

**Purpose:** Build a change manifest describing what changed, where, and what type.

### Steps

1. **Determine diff source:**
   - If on a feature branch: `git diff main...HEAD --name-status` (all changes since branching)
   - If on main: `git diff HEAD~10 --name-status` (recent 10 commits as fallback)
   - Also check `git status` for uncommitted changes

2. **Classify each changed file into categories:**

   | Category | Path patterns | Routes to |
   |----------|--------------|-----------|
   | backend-domain | `backend/app/domain/**` | `services/backend/CLAUDE.md` |
   | backend-api | `backend/app/api/**` | `services/backend/CLAUDE.md` + root |
   | backend-infra | `backend/app/infrastructure/**` | `services/backend/CLAUDE.md` |
   | web | `web/src/**` | root (Services Map) |
   | mobile-domain | `mobile/lib/domain/**` | `mobile/CLAUDE.md` |
   | mobile-ui | `mobile/lib/features/**`, `mobile/lib/shared/**` | `mobile/CLAUDE.md` |
   | contracts | `docs/contracts/**` | root (Knowledge Indexes) |
   | decisions | `docs/decisions/**` | root (Knowledge Indexes) |
   | ops | `docs/ops/**` | root (Knowledge Indexes) |
   | infra | `infra/**`, `docker-compose.yml`, `.github/**` | root (Shared Infrastructure, Commands) |
   | config | `pyproject.toml`, `package.json`, `pubspec.yaml` | root (Services Map — tech/version changes) |

3. **Produce a change manifest** — structured summary of categories, file counts, and change types (added, modified, deleted).

4. **Short-circuit:** If no files match any category, report "No documentation-relevant changes detected. CLAUDE.md is in sync." and exit.

## 5. Phase 2 — Analyze

**Purpose:** For each category in the change manifest, compare current CLAUDE.md content against actual repo state and generate proposed updates.

### Steps

1. **Read target CLAUDE.md files** — only the ones identified by the routing table in Phase 1.

2. **Per-category analysis:**

   | Category | What to check | What to propose |
   |----------|--------------|----------------|
   | backend-domain | New entities/aggregates in `backend/app/domain/` | Update domain model section in `services/backend/CLAUDE.md` |
   | backend-api | New or changed endpoints in `backend/app/api/` | Update API endpoints section in `services/backend/CLAUDE.md`; update Services Map if responsibility shifted |
   | backend-infra | New repositories, new infra dependencies | Update tech stack or infrastructure notes |
   | web | New major features, framework changes in `package.json` | Update root Services Map (tech column) if versions changed |
   | mobile-domain | New entities in `mobile/lib/domain/` | Update `mobile/CLAUDE.md` domain model section |
   | mobile-ui | New features/pages, design system changes | Update `mobile/CLAUDE.md` feature sections |
   | contracts | New or modified contract files vs `docs/contracts/README.md` | Flag stale index (don't modify). Propose root Knowledge Indexes update if new contract not referenced |
   | decisions | New ADR files vs `docs/decisions/README.md` | Flag stale index. Propose root Knowledge Indexes or Global Rules update if ADR changes a rule |
   | ops | Changed runbooks vs `docs/ops/README.md` | Flag stale index. Propose root Shared Infrastructure or Commands update if relevant |
   | infra | New services in docker-compose, new CI workflows, new IaC | Update root Shared Infrastructure, Key Global Commands |
   | config | Major version bumps, new dependencies | Update root Services Map tech column |

3. **Cross-cutting detection:** If changes span 3+ categories, check whether a new "Known Pain Point" or "Global Rule" should be surfaced (e.g., new service appears in docker-compose + new API contract + new domain folder → suggest adding to Services Map).

4. **Stale content detection:** For each section of each target CLAUDE.md, verify referenced items still exist:
   - Commands in "Key Global Commands" — do the paths/scripts still work?
   - Services in "Services Map" — do the directories exist?
   - Knowledge Indexes — do the referenced README.md files exist?
   - Report stale references as proposed removals.

5. **Generate proposals** — each is a discrete unit with:
   - Target file and section
   - Reason (what triggered the proposal)
   - Action (exact content change)

   Example:
   ```
   Proposal 1: [root CLAUDE.md -> Services Map]
     Reason: New "worker" service detected in docker-compose.yml
     Action: Add row -- worker | Async export tasks | Python, Redis consumer | N/A

   Proposal 2: [services/backend/CLAUDE.md -> Domain Model]
     Reason: New Export aggregate in backend/app/domain/export/
     Action: Add "Export" to domain entities list

   Proposal 3: [STALE INDEX WARNING]
     docs/contracts/README.md does not reference new rest-export-api.md
     -> Run /project:setup-knowledge to fix
   ```

## 6. Phase 3 — Apply

**Purpose:** Present all proposals for batch approval, write approved changes, commit.

### Steps

1. **Present proposals grouped by target file:**

   ```
   === Root CLAUDE.md (3 proposals) ===
   1. [Services Map] Add worker service row
   2. [Shared Infrastructure] Add Redis Streams reference
   3. [Known Pain Points] Remove resolved item about web testing

   === services/backend/CLAUDE.md (1 proposal) ===
   4. [Domain Model] Add Export aggregate

   === STALE INDEX WARNINGS (1 warning) ===
   ! docs/contracts/README.md missing rest-export-api.md

   ---
   Approve all / Pick individually / Skip all?
   ```

2. **Handle user response:**
   - **Approve all** — apply all proposals, skip warnings (informational)
   - **Pick individually** — present each proposal with its exact diff, user says yes/no per item
   - **Skip all** — exit without changes

3. **Write approved changes:**
   - Use Edit tool for surgical section edits (not full file rewrites)
   - Preserve existing formatting and section ordering
   - Never rewrite sections that weren't part of a proposal

4. **Commit:**
   - Stage only the modified CLAUDE.md files
   - Commit message pattern:
     ```
     docs(claude-md): sync with repo state

     Updated:
     - [root] Added worker service to Services Map
     - [root] Added Redis Streams to Shared Infrastructure
     - [backend] Added Export aggregate to domain model

     Detected by: sync-claude-md skill
     ```
   - Do **not** push — leave that to the user

5. **Final report:**
   ```
   N proposals applied, M skipped
   Committed: <hash>
   W stale index warnings -- run /project:setup-knowledge to fix

   Files modified:
   - CLAUDE.md
   - services/backend/CLAUDE.md
   ```

## 7. Edge Cases & Safety

**Merge conflicts:** If the target CLAUDE.md has uncommitted changes when the skill runs, warn the user and ask whether to proceed or abort.

**Empty diff:** If Phase 1 detects no documentation-relevant changes, exit early: "No documentation-relevant changes detected. CLAUDE.md is in sync."

**Missing CLAUDE.md files:** If the routing table points to a service-level CLAUDE.md that doesn't exist (e.g. new service added without CLAUDE.md), propose creating it using existing service CLAUDE.md files as a template.

**Large changesets:** If the change manifest has 50+ files across 5+ categories, warn the user and offer to scope to specific categories: "Large changeset detected (N files, M categories). Analyze all, or pick categories?"

**Idempotency:** Running the skill twice with no intervening changes produces zero proposals on the second run. The skill checks what CLAUDE.md currently says, not what git changed.

**Concurrent edits:** The skill reads CLAUDE.md at the start of Phase 2 and writes at the end of Phase 3. If the user edits CLAUDE.md mid-skill, the Edit tool's exact-match replacement will fail safely rather than overwriting.

## 8. CLAUDE.md Template Structure

The skill targets these canonical section structures to know where to insert proposals.

### Root CLAUDE.md

```
# {Project Name}
## What This System Does
## Current Stage
## How to Use This Second Brain
## Global Rules
## Never Do
## Services Map
## Shared Infrastructure
## Knowledge Indexes
## Key Global Commands
## Known Pain Points
```

### Service-level CLAUDE.md

```
# {Service Name}
## Ownership & Responsibility
## Tech Stack
## Domain Model
## API Endpoints
## Key Commands
## Error Patterns
## Known Issues
```

### Mobile CLAUDE.md

```
# Mobile
## Ownership & Responsibility
## Tech Stack
## Design System
## Domain Model
## Feature Modules
## Key Commands
## Known Issues
```

The skill matches sections by heading text. If a section doesn't exist but a proposal targets it, the skill proposes adding the section in canonical order.

## 9. Integration with Existing Commands

| Command | Relationship |
|---------|-------------|
| `/project:update-knowledge` | Complementary. `update-knowledge` is session-scoped and user-driven. `sync-claude-md` is autonomous and git-aware. No overlap. |
| `/project:setup-knowledge` | `sync-claude-md` is the incremental version. `setup-knowledge` is the full bootstrap. Stale index warnings may recommend running `setup-knowledge`. |
| `/project:before-plan` | `sync-claude-md` should run before `before-plan` so AI context is fresh. |
| `/project:check-contracts` | `sync-claude-md` flags stale contract indexes but doesn't validate contract content. `check-contracts` is the deep check. |

### Thin Command

`.claude/commands/sync-claude-md.md`:
```
Sync CLAUDE.md files with current repository state. Run the sync-claude-md skill.
```

### CLAUDE.md Self-Reference

Add to root CLAUDE.md "How to Use This Second Brain" section:
```
- Sync CLAUDE.md with repo changes: run /project:sync-claude-md
```

## 10. File Manifest

| File | Purpose |
|------|---------|
| `.claude/skills/sync-claude-md/SKILL.md` | Skill definition with full workflow |
| `.claude/commands/sync-claude-md.md` | Thin command for `/project:` discoverability |
| `CLAUDE.md` | Updated with self-reference in second brain section |
