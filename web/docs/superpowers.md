# Superpowers Setup and Workflow

Use superpowers to keep planning and implementation disciplined during the frontend architecture migration.

## Codex Setup

1. Clone repository:

```bash
git clone https://github.com/obra/superpowers.git ~/.codex/superpowers
```

2. Create skills symlink:

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/superpowers/skills ~/.agents/skills/superpowers
```

3. Restart Codex.

4. Verify:

```bash
ls -la ~/.agents/skills/superpowers
```

## Copilot CLI Setup

```bash
copilot plugin marketplace add obra/superpowers-marketplace
copilot plugin install superpowers@superpowers-marketplace
```

## Migration from Legacy Bootstrap

If your Codex setup previously used bootstrap blocks:

1. Update local clone:

```bash
cd ~/.codex/superpowers && git pull
```

2. Remove old bootstrap section from `~/.codex/AGENTS.md`.
3. Restart Codex.

## Updating and Uninstall

Update:

```bash
cd ~/.codex/superpowers && git pull
```

Uninstall:

```bash
rm ~/.agents/skills/superpowers
rm -rf ~/.codex/superpowers
```

## Recommended Project Workflow

Use this sequence for each migration slice:

1. `brainstorming`
   - Clarify UX goal, backend contract touchpoints, and acceptance criteria.

2. `writing-plans`
   - Produce task-level plan with exact files and verification steps.

3. `subagent-driven-development`
   - Execute in small tasks, preserving layer boundaries.

4. `requesting-code-review`
   - Run review gate before merge.

5. `verification-before-completion`
   - Confirm behavior with type-check/tests and runtime checks.

## Team Working Agreement

- Keep PR scope to one bounded context per wave.
- Block merges when layer-boundary violations appear.
- Treat backend API contract invariants as non-negotiable.
