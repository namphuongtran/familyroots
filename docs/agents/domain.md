# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/README.md`**: the documentation index for this repo. It names which doc owns each surface.
- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root if it exists: it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/decisions/`**: this repo's ADR directory. Files are named `NNN-title.md` and the index is `docs/decisions/README.md`. Read the ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

This repo is single-context:

```
/
├── CONTEXT.md                         ← does not exist yet; created lazily
├── docs/
│   ├── README.md                      ← the documentation index
│   └── decisions/                     ← ADRs, numbered NNN-title.md
│       ├── README.md                  ← the ADR index
│       └── 058-registration-may-name-no-clan.md
├── backend/
├── web/
└── mobile/
```

If this repo ever splits into multiple contexts, a `CONTEXT-MAP.md` at the root points at one
`CONTEXT.md` per context, and each context may carry its own ADR directory.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-047 (the RLS seam sets `clan_id` only), but worth reopening because…_
