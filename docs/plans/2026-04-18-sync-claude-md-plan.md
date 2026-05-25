# sync-claude-md Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code skill that detects documentation drift between repository state and CLAUDE.md files, proposes targeted updates, and applies approved changes.

**Architecture:** A single SKILL.md file containing a three-phase layered workflow (Detect → Analyze → Apply). A thin command file provides `/project:sync-claude-md` discoverability. The skill is prompt-driven (no executable code) — Claude follows the SKILL.md instructions using its built-in tools (Bash for git, Read/Edit for files).

**Tech Stack:** Claude Code skill system (SKILL.md frontmatter format), git CLI, Bash, Read/Edit tools.

**Spec:** `docs/plans/2026-04-18-sync-claude-md-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `.claude/skills/sync-claude-md/SKILL.md` | Main skill definition — frontmatter + full three-phase workflow instructions |
| `.claude/commands/sync-claude-md.md` | Thin command (one-liner) for `/project:sync-claude-md` discoverability |
| `CLAUDE.md` | Add one line to "How to Use This Second Brain" section |

---

### Task 1: Create the SKILL.md Skill Definition

**Files:**
- Create: `.claude/skills/sync-claude-md/SKILL.md`

This is the core deliverable. The SKILL.md file uses the same frontmatter format as the existing `commit-push-current-branch` skill and contains the full three-phase workflow as structured instructions for Claude to follow.

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ".claude/skills/sync-claude-md"
```

- [ ] **Step 2: Write the SKILL.md file**

Create `.claude/skills/sync-claude-md/SKILL.md` with the following exact content:

```markdown
---
name: sync-claude-md
description: "Detect documentation drift between repository state and CLAUDE.md files, propose targeted updates, and apply approved changes. Use when: updating claude.md, syncing claude.md, reviewing claude documentation, refreshing repo knowledge, updating ai context, after major features, before merging large PRs, or during release preparation."
---

# Sync CLAUDE.md with Repository State

Detect documentation drift between the repository and CLAUDE.md files, propose targeted updates, and apply approved changes with a descriptive commit.

This skill has three phases: **Detect** (build change manifest), **Analyze** (generate proposals), **Apply** (batch approve and commit).

---

## Phase 1: Detect

Build a change manifest describing what changed, where, and what type.

### Step 1.1: Determine the diff source

Run the appropriate git command based on the current branch:

- If on a feature branch (not `main`):
  ```bash
  git diff main...HEAD --name-status
  ```
- If on `main`:
  ```bash
  git diff HEAD~10 --name-status
  ```
- Always also run:
  ```bash
  git status --short
  ```

Combine both outputs into a single list of changed files.

### Step 1.2: Classify changed files

Classify every changed file into categories using this routing table. Files that don't match any pattern are ignored.

| Category | Path patterns | Routes to |
|----------|--------------|-----------|
| backend-domain | `backend/app/domain/**` | `services/backend/CLAUDE.md` |
| backend-api | `backend/app/api/**` | `services/backend/CLAUDE.md` + root `CLAUDE.md` |
| backend-infra | `backend/app/infrastructure/**` | `services/backend/CLAUDE.md` |
| web | `web/src/**` | root `CLAUDE.md` (Services Map) |
| mobile-domain | `mobile/lib/domain/**` | `mobile/CLAUDE.md` |
| mobile-ui | `mobile/lib/features/**`, `mobile/lib/shared/**` | `mobile/CLAUDE.md` |
| contracts | `docs/contracts/**` | root `CLAUDE.md` (Knowledge Indexes) |
| decisions | `docs/decisions/**` | root `CLAUDE.md` (Knowledge Indexes) |
| ops | `docs/ops/**` | root `CLAUDE.md` (Knowledge Indexes) |
| infra | `infra/**`, `docker-compose.yml`, `.github/**` | root `CLAUDE.md` (Shared Infrastructure, Commands) |
| config | `pyproject.toml`, `package.json`, `pubspec.yaml` | root `CLAUDE.md` (Services Map tech/version) |

### Step 1.3: Produce change manifest

Output a structured summary like:

```
Changes detected:
- backend-domain: 3 files (new entity, modified repository)
- contracts: 1 file (new rest-export-api.md)
- infra: 1 file (docker-compose.yml — new service added)
```

### Step 1.4: Short-circuit if empty

If no files match any category, report:

> No documentation-relevant changes detected. CLAUDE.md is in sync.

Then stop. Do not proceed to Phase 2.

---

## Phase 2: Analyze

For each category in the change manifest, compare current CLAUDE.md content against actual repo state and generate proposed updates.

### Step 2.1: Read target CLAUDE.md files

Read only the CLAUDE.md files identified by the routing table. Do not read files that won't be updated. The target files are:

- Root: `CLAUDE.md`
- Backend: `services/backend/CLAUDE.md`
- Mobile: `mobile/CLAUDE.md`

### Step 2.2: Per-category analysis

For each category in the change manifest, check what changed and determine what to propose:

| Category | What to check | What to propose |
|----------|--------------|----------------|
| backend-domain | New entities/aggregates in `backend/app/domain/` | Update domain model section in `services/backend/CLAUDE.md` |
| backend-api | New or changed endpoints in `backend/app/api/` | Update API endpoints in `services/backend/CLAUDE.md`; update root Services Map if responsibility shifted |
| backend-infra | New repositories, new infra dependencies | Update tech stack or infrastructure notes |
| web | New major features, framework changes in `package.json` | Update root Services Map (tech column) if versions changed |
| mobile-domain | New entities in `mobile/lib/domain/` | Update `mobile/CLAUDE.md` domain model section |
| mobile-ui | New features/pages, design system changes | Update `mobile/CLAUDE.md` feature sections |
| contracts | New/modified contract files vs `docs/contracts/README.md` | Flag stale index. Propose root Knowledge Indexes update if new contract not referenced |
| decisions | New ADR files vs `docs/decisions/README.md` | Flag stale index. Propose root Knowledge Indexes or Global Rules update if ADR changes a rule |
| ops | Changed runbooks vs `docs/ops/README.md` | Flag stale index. Propose root Shared Infrastructure or Commands update if relevant |
| infra | New services in docker-compose, new CI workflows, new IaC | Update root Shared Infrastructure, Key Global Commands |
| config | Major version bumps, new dependencies | Update root Services Map tech column |

### Step 2.3: Cross-cutting detection

If changes span 3 or more categories, check whether a new Known Pain Point or Global Rule should be surfaced. For example: a new service appearing in docker-compose + a new API contract + a new domain folder suggests adding a row to the Services Map.

### Step 2.4: Stale content detection

For each section of each target CLAUDE.md, verify that referenced items still exist:

- Commands in "Key Global Commands" — do the paths/scripts still work?
- Services in "Services Map" — do the directories exist?
- Knowledge Indexes — do the referenced README.md files exist?

Report any stale references as proposed removals.

### Step 2.5: Generate proposals

Each proposal is a discrete unit with three fields:

- **Target:** file path and section heading
- **Reason:** what triggered the proposal
- **Action:** the exact content change (what to add, modify, or remove)

Separately, collect stale index warnings (informational only — these are not proposals to apply).

### Step 2.6: Handle missing CLAUDE.md files

If the routing table points to a service-level CLAUDE.md that does not exist (e.g. a new service was added), propose creating it using this template:

```markdown
# {Service Name}
## Ownership & Responsibility
## Tech Stack
## Domain Model
## API Endpoints
## Key Commands
## Error Patterns
## Known Issues
```

Populate the sections based on what you can observe in the service directory.

### Step 2.7: Handle large changesets

If the change manifest has 50+ files across 5+ categories, warn the user:

> Large changeset detected (N files, M categories). Analyze all, or pick categories?

Wait for the user's response before proceeding.

---

## Phase 3: Apply

Present all proposals for batch approval, write approved changes, commit.

### Step 3.1: Check for uncommitted CLAUDE.md changes

Before presenting proposals, check if any target CLAUDE.md files have uncommitted changes:

```bash
git diff --name-only -- CLAUDE.md services/backend/CLAUDE.md mobile/CLAUDE.md
```

If any do, warn the user:

> Warning: {file} has uncommitted changes. Proceeding may conflict. Continue or abort?

### Step 3.2: Present proposals grouped by target file

Present all proposals in this format:

```
=== Root CLAUDE.md (N proposals) ===
1. [Section] Description of change
2. [Section] Description of change

=== services/backend/CLAUDE.md (N proposals) ===
3. [Section] Description of change

=== STALE INDEX WARNINGS (N warnings) ===
! description of stale index

---
Approve all / Pick individually / Skip all?
```

### Step 3.3: Handle user response

- **Approve all** — apply all proposals. Skip warnings (they are informational).
- **Pick individually** — present each proposal one at a time with its exact diff. User says yes or no per item.
- **Skip all** — exit without changes.

### Step 3.4: Write approved changes

- Use the Edit tool for surgical section edits (not full file rewrites).
- Preserve existing formatting and section ordering.
- Never rewrite sections that were not part of a proposal.
- If a proposal targets a section that does not exist, add the section in the canonical order defined by the template structure below.

### Step 3.5: Commit

Stage only the modified CLAUDE.md files and commit:

```bash
git add CLAUDE.md services/backend/CLAUDE.md mobile/CLAUDE.md  # only files that were actually modified
git commit -m "docs(claude-md): sync with repo state

Updated:
- [list each applied proposal as a bullet]

Detected by: sync-claude-md skill"
```

Do **not** push. Leave that to the user.

### Step 3.6: Final report

```
N proposals applied, M skipped
Committed: <hash>
W stale index warnings -- run /project:setup-knowledge to fix

Files modified:
- list of modified files
```

---

## Canonical Section Structure

The skill matches sections by heading text. Use these canonical structures to determine where to insert content.

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

---

## Safety Rules

- Running the skill twice with no intervening changes must produce zero proposals (idempotency).
- The skill checks what CLAUDE.md currently says, not what git changed — already-documented changes are not re-proposed.
- If the user edits CLAUDE.md mid-skill, the Edit tool's exact-match replacement will fail safely rather than overwriting.
- Never modify knowledge index files (docs/contracts/README.md, docs/decisions/README.md, docs/ops/README.md). Only flag them as stale.
```

- [ ] **Step 3: Verify the file was created**

```bash
ls -la ".claude/skills/sync-claude-md/SKILL.md"
cat ".claude/skills/sync-claude-md/SKILL.md" | head -5
```

Expected: file exists, first lines show the frontmatter `---` and `name: sync-claude-md`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/sync-claude-md/SKILL.md
git commit -m "feat: add sync-claude-md skill definition

Three-phase skill (Detect → Analyze → Apply) that detects
documentation drift and proposes CLAUDE.md updates from git state."
```

---

### Task 2: Create the Thin Command

**Files:**
- Create: `.claude/commands/sync-claude-md.md`

This one-liner command provides `/project:sync-claude-md` discoverability, matching the existing command pattern in `.claude/commands/`.

- [ ] **Step 1: Write the command file**

Create `.claude/commands/sync-claude-md.md` with the following exact content:

```markdown
Sync CLAUDE.md files with current repository state. Run the sync-claude-md skill.
```

This matches the terse, single-line style used by other commands in this directory (e.g. `brainstorm.md`, `check-contracts.md`).

- [ ] **Step 2: Verify the file was created**

```bash
ls -la ".claude/commands/sync-claude-md.md"
cat ".claude/commands/sync-claude-md.md"
```

Expected: file exists, content is the single line above.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/sync-claude-md.md
git commit -m "feat: add sync-claude-md thin command for /project: discoverability"
```

---

### Task 3: Update Root CLAUDE.md Self-Reference

**Files:**
- Modify: `CLAUDE.md:9-15` (the "How to Use This Second Brain" section)

Add the sync command reference so users know it exists.

- [ ] **Step 1: Read current CLAUDE.md**

Read `CLAUDE.md` and locate the "How to Use This Second Brain" section. It currently contains:

```markdown
## How to Use This Second Brain
- Before planning any feature: run /project:before-plan
- After finishing any session: run /project:update-knowledge
- Adding a new service: run /project:new-service
- Brainstorming: run /project:brainstorm
- Cross-service change: run /project:check-contracts first
- First-time refresh/bootstrap: run /project:setup-knowledge
```

- [ ] **Step 2: Add the sync line**

Use the Edit tool to add one line after the `setup-knowledge` entry:

**old_string:**
```
- First-time refresh/bootstrap: run /project:setup-knowledge
```

**new_string:**
```
- First-time refresh/bootstrap: run /project:setup-knowledge
- Sync CLAUDE.md with repo changes: run /project:sync-claude-md
```

- [ ] **Step 3: Verify the edit**

Read `CLAUDE.md` lines 9-16 and confirm the new line appears in the correct position.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add sync-claude-md to second brain usage guide"
```

---

### Task 4: Verify the Complete Skill Installation

**Files:** None (verification only)

- [ ] **Step 1: Verify all three files exist**

```bash
ls -la .claude/skills/sync-claude-md/SKILL.md
ls -la .claude/commands/sync-claude-md.md
head -20 CLAUDE.md
```

Expected: both skill files exist, CLAUDE.md shows the new sync line in "How to Use This Second Brain".

- [ ] **Step 2: Verify SKILL.md frontmatter is valid**

```bash
head -4 .claude/skills/sync-claude-md/SKILL.md
```

Expected output:
```
---
name: sync-claude-md
description: "Detect documentation drift between repository state and CLAUDE.md files, propose targeted updates, and apply approved changes. Use when: updating claude.md, syncing claude.md, reviewing claude documentation, refreshing repo knowledge, updating ai context, after major features, before merging large PRs, or during release preparation."
---
```

- [ ] **Step 3: Verify command file matches existing pattern**

```bash
wc -l .claude/commands/sync-claude-md.md
cat .claude/commands/sync-claude-md.md
```

Expected: 1 line, content is `Sync CLAUDE.md files with current repository state. Run the sync-claude-md skill.`

- [ ] **Step 4: Verify git log shows all three commits**

```bash
git log --oneline -3
```

Expected: three commits for the skill definition, thin command, and CLAUDE.md update.
