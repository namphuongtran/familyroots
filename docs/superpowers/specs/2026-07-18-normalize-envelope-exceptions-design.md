# Normalize the two non-canonical envelope exceptions (ADR-024 follow-through)

**Date:** 2026-07-18
**Status:** Approved — ready for implementation plan
**Branch:** `feat/normalize-envelope-exceptions`

## Problem

PR-2 (#84) typed the last routes but deliberately left two shapes non-canonical,
**typed as-is** and tracked by ADR-024 for normalization **before the frontend
binds**. The frontend has not been built, so the window is open now — a breaking
change here costs nothing (no client is bound). The two exceptions:

1. `GET /me/clans` — returns `meta: {count}` instead of the canonical envelope.
2. `GET /clans/me/users/pending` — omits the `person_id` key its sibling
   `GET /clans/me/users` includes.

This change makes both canonical and retires ADR-024's debt.

## Decisions

### ① `GET /me/clans` → plain array `ok_list(UserClanMembership)` (breaking)

The route becomes `{"data": [UserClanMembership, ...]}` — a plain array, **no
`meta`**. Rationale (owner-confirmed as the long-term choice):
- `/me/clans` backs a clan **switcher**: it must return *all* the user's approved
  memberships, never a paginated page. Cursor pagination is semantically wrong
  (you don't paginate a 3-item dropdown).
- Plain `{data:[...]}` is fully canonical — the same shape as other bounded,
  non-paginated list endpoints (`/persons/{id}/marriages`, `/events/upcoming`, …),
  all typed with `ok_list`.
- **Low-regret / not a corner:** if a user could ever have hundreds of clans,
  adding cursor `meta` later is **non-breaking** (clients reading `data` keep
  working). The reverse (`page` → `ok_list`) would be breaking. So starting simple
  is strictly safer.
- The dropped `count` is redundant with `data.length`.

The underlying query already returns all rows (no pagination existed); only the
envelope shape changes. **Breaking:** clients reading `meta.count` must switch to
`data.length`. No client is bound, so this is free now.

### ② `GET /clans/me/users/pending` → include `person_id` (additive)

The #83 fix made `clan_repository.list_users` `joinedload` `UserClanRole.user_profile`
for **both** approved and pending queries, so pending rows already carry the linked
profile. Add `person_id` (None-guarded, exactly as the approved route does) to the
pending wire dict. Its shape then equals `/clans/me/users`, so **`PendingClanUser`
is dropped and both routes use `ClanUserSummary`**. Additive (adds a key); not
breaking.

### ③ Cleanup

- Drop schemas `UserClansEnvelope`, `CountMeta` (and dead `UserClansResponse` if
  unused), `PendingClanUser`, and their legacy-exception deprecation docstrings.
- Simplify `MeQueryHandler.list_clans` to return `list[dict]` (drop the now-unused
  `count`); update the one test that asserts `clans["count"]`.
- Update **ADR-024** Status to reflect the normalization is done (both exceptions
  retired), and the README ADR index status.
- Update `docs/contracts/README.md` so no non-canonical exceptions remain — every
  v1 JSON 2xx is canonical except `/exports/clan` (file download, exempt).

## Component changes

| File | Change |
|---|---|
| `app/application/me/handlers.py` | `list_clans` returns `list[dict]` (drop `count`) |
| `app/api/v1/me.py` | route `{"data": result}` + `responses=ok_list(UserClanMembership)`; import `ok_list`, drop `UserClansEnvelope` |
| `app/api/v1/clans.py` | `list_pending_users` adds None-guarded `person_id`; route `responses=page(ClanUserSummary)`; drop `PendingClanUser` import |
| `app/schemas/clan.py` | remove `UserClansEnvelope`, `CountMeta`, `UserClansResponse` (if unused) |
| `app/schemas/clan_membership.py` | remove `PendingClanUser` |
| `docs/decisions/024-…md`, `docs/decisions/README.md` | ADR-024 status → normalized |
| `docs/contracts/README.md` | drop the two exceptions from the caveat |

## Testing

- **OpenAPI tests** (`test_openapi_typed_responses.py`): `/me/clans` → `Envelope` +
  `UserClanMembership` (via `ok_list`, no longer `UserClansEnvelope`);
  `/clans/me/users/pending` → `PageEnvelope` + `ClanUserSummary` (no longer
  `PendingClanUser`).
- **Coherence guards:** `/me/clans` guard validates the new `{"data":[...]}` body —
  each item against `UserClanMembership`; `/pending` guard validates against
  `ClanUserSummary` and asserts `person_id` is present (populated for a member with
  a linked person). Both sabotage-verified.
- **Behavior-change tests:** update `test_me_lists_only_approved_and_blocks_non_member`
  (`clans["count"] == 1` → `len(clans) == 1`, since the handler now returns a list).
  This is the negative control — the *set* of clans returned is unchanged; only the
  envelope shape changed.
- Full gate green.

## Definition of done

- `/me/clans` returns `{"data":[...]}` (no meta); `/clans/me/users/pending` includes
  `person_id`.
- OpenAPI: `/me/clans` typed via `ok_list(UserClanMembership)`, `/pending` via
  `page(ClanUserSummary)`; the 3 dropped schemas are gone; untyped-2xx still 1
  (`/exports/clan`).
- ADR-024 marked normalized; `docs/contracts` shows no non-canonical exceptions.
- Full gate green; guards sabotage-verified.

## Breaking-change note (for the record)

`GET /me/clans` drops `meta.count` — the single intentional breaking change,
made now precisely because no frontend is bound. `/clans/me/users/pending` gaining
`person_id` is additive. `docs/contracts/` is the spec and is updated in the same PR.
