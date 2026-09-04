# ADR-009: Clan Deletion Is RESTRICT-Guarded (No Cascade-Wipe of Clan Data)

## Status
Accepted (2026-07-05).

## Context
There is intentionally **no clan-delete path** in the application: a clan's lifecycle
is suspend / reactivate only (`Clan.suspend()` / `reactivate()`, ADR-002). But every
clan-owned foreign key was originally declared `ON DELETE CASCADE`. That meant a
future or manual `DELETE FROM clans WHERE id = …` (an ops script, a hastily-added
endpoint) would **silently cascade-wipe the clan's entire genealogy** — marriages,
parent-child edges, branches, memberships, invitations, settings, change requests,
notifications, documents, and events — in one statement. For a genealogy platform,
that irreversible loss is the worst-case data event.

This complements ADR-006 (which governs *person / edge* delete). ADR-006 is about
soft-deleting a person; this ADR is about what happens to a whole clan's data if the
clan row itself is ever deleted.

## Decision
All clan-owned foreign keys use **`ON DELETE RESTRICT`** so that deleting a clan that
still owns rows **fails loudly** instead of cascading. A real clan purge must
therefore be an explicit, deliberate, audited operation that removes children first —
never an accidental side effect.

- **RESTRICT** (11 FKs): `change_requests`, `clan_settings`, `marriages`,
  `user_clan_roles`, `clan_invitations`, `branches`, `clan_memberships`,
  `notification_log`, `parent_child`, `documents`, `events`.

  > **Amended 2026-08-22 by [ADR-054](054-clan-settings-table-is-dropped.md).** The
  > RESTRICT list is now **ten** foreign keys, not eleven: `clan_settings` was dropped with its
  > table by migration `039_drop_clan_settings`. **The decision is unchanged and so is every other
  > row** — a clan-owned table still makes a conscious RESTRICT-versus-SET-NULL choice, and
  > `tests/integration/test_schema_baseline.py::test_clan_fks_are_restrict` still asserts the clan
  > foreign keys partition exactly. Only the count moved. With no row ever created, `clan_settings`
  > blocked nothing in practice, so **no clan deletion behaves differently**. The list is left as
  > written rather than edited, because this ADR is a dated record of what was decided.
- **SET NULL** (retained / de-provenanced, *not* destroyed): `persons.created_by_clan_id`
  and `audit_logs.clan_id`. A person outlives its origin clan (its provenance is simply
  cleared); the audit trail is retained for accountability.

Enforced by migration `010_clan_fk_restrict` (introspects each FK's real name and
recreates it with RESTRICT, preserving the name for an exact round trip) and pinned
against `pg_constraint` by `tests/integration/test_schema_baseline.py::test_clan_fks_are_restrict`,
which also asserts the clan FKs partition *exactly* — so any future clan-referencing
table must make a conscious RESTRICT-vs-SET-NULL choice.

## Consequences
Easier:
- A clan's genealogy can never be silently destroyed by a single delete; the FK layer
  is a hard backstop independent of application logic (defense-in-depth).
- Adding a clan-referencing table forces an explicit deletion-policy decision (the
  partition test fails otherwise).

Harder:
- **A future "delete clan" feature must be built deliberately** — it has to remove or
  reassign the clan's children first (or run as an explicit, audited purge). This is
  the intended cost: do NOT "fix" a RESTRICT violation by reverting the FK to CASCADE.
- Ops/manual clan deletion now errors until the clan is empty; that error is the point.
