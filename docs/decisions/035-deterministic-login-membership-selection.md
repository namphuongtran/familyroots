# ADR-035: Deterministic Membership Selection in the Login/Profile Response

## Status
Accepted (2026-08-02). Codifies behaviour shipped in `fix(auth): correct and
deterministic login profile` (2026-07-16) that had never been written down.

## Context

`POST /auth/login` and `GET /auth/me` return **one** membership inline in the profile
(`clan_id`, `clan_name`, `role`, `is_approved`) so a client can render the first screen
without a second round-trip. A user can be a member of several clans — approved in one,
pending in another, or approved in two.

The projection behind it (`SqlAlchemyAuthQueryPort.get_login_profile` /
`get_profile`, `app/infrastructure/persistence/auth_repository.py`) was a
`LIMIT 1` with **no `ORDER BY`**. Postgres was then free to return any matching row,
and the row it happens to return can change with plan, physical row order, or a
`VACUUM`. Two concrete consequences:

- **Nondeterminism.** The same user could land in clan A on one login and clan B on the
  next, with no data change in between.
- **A wrong answer, not just an arbitrary one.** A user approved as admin in clan A and
  pending in clan B could be told `clan_id: B, role: null, is_approved: false` — the
  login response describing them as a pending nobody while they are in fact an admin.

`docs/contracts/frontend-integration-guide.md` marked this **⚠️ UNDEFINED — needs
backend decision** and told both clients not to trust `user.clan_id`. That workaround
was on its way into two client architectures.

## Decision

**The inline membership is chosen by a total, documented ordering.** In
`get_login_profile`:

1. `is_approved DESC NULLS LAST` — an approved membership always beats a pending one;
2. `created_at ASC NULLS LAST` — then the **oldest** membership, i.e. the clan the user
   joined first (`user_clan_roles.created_at` is exactly what `GET /me/clans` exposes as
   `joined_at`);
3. `clan_id ASC` — final tiebreak, so even two memberships written in the same
   transaction (identical `created_at`) resolve to one stable answer.

`get_profile` (`GET /auth/me`) joins **approved memberships only** and applies (2)+(3);
rule (1) is implicit there.

Rationale for the ordering:

- **Approved first** is the only rule that makes the response *truthful*: reporting a
  pending membership while an approved one exists understates the user's access and
  routes them to the pending-approval screen when they should see their tree.
- **Oldest first** is the stable, meaningful choice: it is monotonic (joining a third
  clan never moves an existing user's landing clan), it matches the intuition that the
  clan you have been in longest is your home clan, and it is expressible from data
  clients already see (`joined_at` on `GET /me/clans`), so a client can predict the
  answer. "Newest first" fails monotonicity; "most recently used" would require
  server-side state we deliberately do not keep (clan selection is client-owned).
- **`clan_id` last** turns a partial order into a total one. Without it the tie case is
  still undefined, which is the bug being fixed, just rarer and harder to reproduce.

The selection is a **landing hint, not stored state**. The active clan remains the
client's choice, sent per request as `X-Current-Clan-Id` and validated by
`get_current_clan_id`. This ADR does not make login a clan switcher.

## Consequences

- `user.clan_id` from login is now safe to use as the initial clan for a multi-clan
  user; the guide's "do not use it" workaround is withdrawn.
- Clients may depend on the ordering: it is part of the auth contract
  (`docs/contracts/rest-auth-api.md`), and changing it needs a new ADR.
- Cost is one `ORDER BY` over a user's own membership rows (single-digit rows in
  practice, indexed by `user_id`) — not measurable next to the identity-provider call
  in the same request.
- Pinned by `backend/tests/integration/test_login_profile_contract.py` against real
  Postgres: approved-beats-older-pending, oldest-of-two-approved stable across repeated
  logins, and the `clan_id` tiebreak when `joined_at` ties. Removing the `ORDER BY`
  fails all three.

## Alternatives considered

- **Return every membership inline and let the client choose.** Rejected as a breaking
  change to a frozen response shape; `GET /me/clans` already exists for exactly that,
  and the profile's job is the fast first paint.
- **Persist a "last active clan" server-side and return it.** Rejected: clan selection
  is deliberately client-owned (no tenant middleware, no server session state — see
  `backend/CLAUDE.md`), and this would add a write to the login path plus a new
  cross-device consistency question.
- **Return `clan_id: null` whenever a user has multiple memberships**, forcing explicit
  selection. Rejected: it would regress the common single-clan-plus-one-stale-invite
  case into an extra screen, and it discards information the backend already holds.
- **Leave it undefined and document "any membership".** Rejected: it is the status quo
  that produced the wrong-answer case above, and it exports nondeterminism to every
  client.
