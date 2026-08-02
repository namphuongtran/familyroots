# ADR-039: Clan User Lists — `display_name` on Both, `email` Only on the Admin Pending Queue

## Status
Accepted — 2026-08-02

## Context

A clan admin approving a join request was deciding against a **UUID**.
`GET /api/v1/clans/me/users/pending` returned `{id, user_id, role, person_id, created_at}`
— no name, no email. Approving grants the requester read access to hundreds of living
relatives' records (names, birth dates, places, photographs), so it is an identity
decision, and the screen showed nothing to make it with. `person_id` helps only when the
account is already linked to a person; for a fresh registrant it is `null`, which is
exactly the case that most needs judgement.

Raised as **J18** in
[`docs/superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
§9. The design spec responded honestly — §7.10a specifies the row the decision requires,
and until the fields existed the interim row's primary action was `Xem chi tiết`, not
`Duyệt`.

The data was already in memory. `SqlAlchemyClanRepository.list_users` eager-loads
`UserClanRole.user_profile` with `joinedload` (a LEFT JOIN on
`user_profiles.id = user_clan_roles.user_id`), and `UserProfile` already carries `email`
and `display_name`. Both route handlers built their response dict by hand and simply
omitted them. This was serialisation, not a query change.

**The two endpoints do not have the same guard**, and that is what this ADR is about:

| Endpoint | Guard | Audience |
|---|---|---|
| `GET /clans/me/users/pending` | `RequireAdmin` | clan admins only |
| `GET /clans/me/users` | `RequireViewer` | **every approved member of the clan** |

The J18 entry recommended adding both fields to both endpoints. That recommendation was
written from the shape of the payloads, not from the guards, and adopting it verbatim
would publish every member's login email address to the entire clan.

It would also contradict a decision this codebase already made deliberately. ADR-037's
change-request review surface excludes `phone` and `email` from `SUBMITTABLE_PERSON_FIELDS`
(`app/domain/change_request/person_changes.py`) on the ground that the review queue echoes
each field's current value, so allowing contact PII there would leak an ordinary member's
contact details to any editor through the queue, bypassing the redaction on the person read
path. A viewer-readable member directory carrying `email` is the same leak through a
different door.

## Decision

Serialise the identity fields **asymmetrically**, matching each endpoint's guard:

- **`GET /clans/me/users/pending`** (`RequireAdmin`) — add `display_name` **and** `email`.
- **`GET /clans/me/users`** (`RequireViewer`) — add `display_name` **only**. No `email`,
  and not even a nulled `email` key: an always-null key would still put the field in the
  documented shape and invite the next contributor to populate it.

`email` is justified on the pending queue and only there. The admin is making an identity
decision; already holds approve / reject / role powers over that account; and the address
is the **account holder's own registration email** — a fact about the person asking to be
let in, supplied by them for that purpose — not a genealogy record about a third party who
never consented. On the approved list none of that holds: the decision is over, the
audience is every viewer, and the members whose addresses would be published are not the
ones who benefit.

`display_name` is symmetric because a member directory that names its members is the
ordinary expectation of a clan roster, and the name is already visible throughout the
genealogy surface.

Both fields are nullable in the payload. `user_profiles.display_name` is nullable, and the
LEFT JOIN can in principle yield no profile row at all, so both handlers None-guard the
`user_profile` reference in the same style as the existing `person_id` line.

### Consequences for the schemas

`PendingClanUserSummary` is a **separate model**, not a subclass of `ClanUserSummary` and
not a shared serialiser. Subclassing would mean every field later added to the
viewer-readable model silently widens the admin one, and — far worse — a shared model or a
shared `_serialise_clan_user()` helper is the single most likely way this distinction gets
erased by a well-meant tidy-up. The duplicated fields are the cost of making the asymmetry
structural instead of conventional.

## Alternatives considered

1. **Both fields on both endpoints** (the spec's recommendation). Closes J18 with one code
   path and no duplication. Rejected: it broadcasts every member's login email to the whole
   clan, and it re-opens the exact exposure ADR-037 closed.
2. **`display_name` only, on both.** Safe, symmetric, no ADR needed. Rejected: it does not
   close J18. A display name is self-chosen at registration and unverified; two relatives
   can share one, and a stranger can pick a plausible one. The email is the one
   identifier tied to a delivery channel the admin can check out of band, and it is the
   difference between recognising a requester and guessing.
3. **A separate `GET /clans/me/users/pending/{id}` detail endpoint carrying the email.**
   Keeps the list payload minimal and gives contact PII its own auditable surface.
   Rejected as premature: same guard, same data, same admin, one extra round trip per row
   in a queue whose whole purpose is triage. Revisit if the pending row ever needs fields
   heavier or more sensitive than an email — phone, address, or an ID document would each
   justify it.
4. **Email masked to `h***@gmail.com` on the pending queue.** Rejected: it defeats the
   purpose. An admin identifies a requester by recognising the address or by contacting it;
   a mask supports neither, while still implying the admin has been given something to
   judge by.

## Consequences

- The J18 approval screen can ship its designed row (`full_name` / `email` above the join
  date) and restore `Duyệt` as the primary action; the interim `Xem chi tiết` fallback in
  §7.10a is no longer required.
- Additive response changes only — no existing key changed type or disappeared, so clients
  pinned to the old shape keep working. Contract updated in
  [`rest-clans-api.md`](../contracts/rest-clans-api.md) in the same change.
- **A refactor that merges the two handlers or the two schemas is a PII regression, not a
  cleanup.** It is pinned by
  `backend/tests/integration/test_clan_users_identity_fields.py::test_email_is_on_pending_and_never_on_approved`,
  which asserts `email` is present on the pending payload and **absent** — not null — on the
  approved one. If that test is in your way, you are the case it was written for; read this
  ADR before deleting it.
- Clan isolation is unaffected: `list_users` still filters on `clan_id`, and the profile
  data reachable through the join is only that of users who hold a role row in the acting
  clan. Pinned two-sided in the same test module.

## Related

- [ADR-037](037-change-requests-workflow.md) — the `phone`/`email` exclusion this decision
  is consistent with.
- [ADR-024](024-non-canonical-envelope-exceptions.md) — the earlier addition of `person_id`
  to these same two lists.
- [ADR-002](002-clan-scoped-multitenancy.md) — clan-scoped isolation.
- [rbac.md](../architecture/rbac.md) — the `viewer < editor < admin` hierarchy the
  asymmetry is drawn along.
