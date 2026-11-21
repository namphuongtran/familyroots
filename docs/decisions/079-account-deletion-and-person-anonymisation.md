# ADR-079: An Account Is Deleted, a Person Is Anonymised, and the Tree Keeps Its Shape

## Status

Accepted (2026-11-21), resolving issue #333, the technical part of #322. **This ADR ships the
code it records**: `DELETE /api/v1/auth/me`, `POST /api/v1/persons/{id}/anonymise`, and a draft
privacy notice page in the web app. No migration.

The legal part stays open on #322: who the data controller is, and the final notice text. The
web page carries a "Bản nháp — cần rà soát pháp lý" banner until #322 closes.

## Context

Two different things get called "delete my data" in a genealogy app, and they belong to two
different people.

- **An account** is a person's own: an email, a sign-in, a name and language preference, and
  the memberships and roles that say which clans they may act in. It lives in Supabase Auth and in
  `user_profiles`, `user_clan_roles`, `user_fcm_tokens` and `identity_claims`.
- **A person in a tree** is the clan's record of a relative, often someone who never had an
  account, often long dead. Other people's đời is computed through them. Deleting the node, or its
  edges, moves every descendant: con theo đời cha ([ADR-027](027-doi-single-authority.md)) takes a
  child's đời from the canonical parent, so a missing father hands the child to the mother's line
  or to "đời ?".

[ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md) recorded
that an assessment is owed once the deployment holds real personal data of people other than the
maintainer. Deletion and erasure are what such an assessment asks for first.

## Decision

### 1. A signed-in user deletes their own account: `DELETE /auth/me`

The backend, in this order:

1. Locks the approved-admin rows of every clan the user administers (`FOR UPDATE`, ordered by
   id, the lock `lock_admin_count` already takes for a demotion or a removal) and **refuses with
   409 `account.last_admin_transfer_first`** when the user is the only approved admin of any
   clan. `detail.clans` names each clan, so the client can point the person to transfer the role.
   Nothing is written.
2. Deletes every `user_clan_roles` row of the user (approved and pending), their
   `user_fcm_tokens`, and their `user_profiles` row. `identity_claims` follows by its
   `ON DELETE CASCADE`.
3. Buffers one `account.delete` audit row: `clan_id` null, `resource_id` and `actor_id` the
   account, `new_value = {profile_removed, clan_ids}`. **Ids only**: the email and the name are
   the data being erased, and the trail is append-only.
4. Deletes the provider account (`IdentityProvider.delete_user`, Supabase
   `auth.admin.delete_user`), **before** the commit. If the provider fails, nothing has been
   committed and the person can retry.
5. Commits, dispatching the audit row in the same transaction.

**Persons stay.** A person this account was linked to (`user_profiles.person_id`) is clan data;
the link goes with the profile row and the node stays in the tree.

**The route runs on the privileged session (`get_system_db`).** It names no clan, and
`user_clan_roles`' UPDATE and DELETE policies are clan-keyed
([ADR-050](050-user-clan-roles-clan-keyed-mutations.md)). Measured 2026-11-21 with the provider
re-pointed at `get_db`: the `FOR UPDATE` read no row under the request role with no clan GUC,
the clan's only admin was deleted (`200`, not `409`), and the explicit role delete removed
nothing (the audit row read `"clan_ids": []`; the rows went only by the profile's FK cascade).
Every statement keys on the JWT `sub`, so the account is the scope, as the token is for
invitation accept ([ADR-048](048-invitation-accept-runs-on-the-system-session.md)).

**`delete_user` treats "user not found" as done**, and now classifies its other failures
(`IdentityUnavailableError` → 503). That closes the one window the order above leaves: a commit
that fails after the provider deletion. A retry, with the access token still valid, finds the
provider account gone, proceeds, and completes the row deletion.

### 2. A clan admin anonymises a person: `POST /persons/{id}/anonymise`

Anonymise, not delete. `Person.anonymise()`:

- **replaces** `full_name` with `"Đã ẩn danh"` (stored, not localised: it is the value of a name,
  read by every client and every export, as any other name is);
- **clears** the other names (`birth_name`, `courtesy_name`, `posthumous_name`, `alias_name` —
  tên húy, tên tự, tên thụy, biệt danh), both dates, their displays and the lunar dates, the five
  places, `biography`, `notes`, `avatar_url`, and the remaining personal details (`phone`,
  `email`, `religion`, `occupation`, `education_level`, `title_rank`);
- sets both date precisions to `unknown`;
- **keeps** `id`, `gender`, `nationality`, the clan memberships, and every marriage and
  parent-child edge. The person is not soft-deleted.

**Gender is kept on purpose, not by omission.** ADR-027's canonical parent is chosen by the
parent's gender (father > mother > unknown). In the H4 family
(`tests/integration/test_person_anonymisation.py`), clearing the anonymised father's gender
moves his child from đời 4 to đời 3 with every edge still in place. Measured 2026-11-21.
`nationality` is kept because it is a column default (`"VN"`), not something a relative wrote.

The published avatar object is deleted the way `DELETE /persons/{id}` deletes it. The audit row,
`person.anonymise`, names the cleared fields and carries **no old value**. The write bumps
`version`, so a PATCH racing it gets `stale_write` rather than writing a name back.

Admin only, the same role as soft-delete and restore. The person must be a live member of the
active clan, the same scoping as every other person write.

### 3. A privacy notice page, marked draft

`/{locale}/privacy` in the web app: public (in `middleware.ts`'s `PUBLIC_ROUTES`), in all four
locales, linked from sign-up and from a site footer, and carrying a visible
"Bản nháp — cần rà soát pháp lý" banner. Its text describes what this ADR builds. It names no
data controller: that is #322's decision.

## Alternatives considered

- **Hard-delete the person, or soft-delete it with its edges.** Rejected: both move descendants'
  đời, which is the shape of the tree other people's records depend on. The issue's negative
  control plants exactly this, and the đời assertion fails.
- **Let the last admin delete their account and leave the clan without one.** Rejected: nobody
  could then approve members or change roles, and only a platform super-admin could repair it.
  Refusing with the clan named costs the person one step (transfer the role).
- **Delete the account on the request session.** Rejected by measurement, § 1.
- **Commit first, then delete the provider account.** Rejected: a provider failure would leave a
  sign-in account with no profile and no memberships, and a later sign-in would provision a fresh
  empty profile, silently.

## Consequences

- A person can leave the platform without asking anyone, unless they are a clan's only admin.
- A clan admin can honour an erasure request for a relative without breaking the tree.
- `account.delete` audit rows have `clan_id` null, so a clan admin's clan-scoped audit view does
  not show them. The member simply disappears from the clan's member list.
- `GET /persons/{id}` and every tree endpoint show `"Đã ẩn danh"` in every locale.

## What this deliberately does not decide, and what stays open

- **Older audit rows still hold the erased values.** `person.create` carries `full_name`, and
  `person.update` carries `changes` and `old_values`. `audit_logs` is append-only to the request
  role ([ADR-043](043-audit-notification-rls-posture.md)). Scrubbing them is a separate decision,
  with a retention question attached; it is not made here.
- **Documents, events and pending change requests about the person are untouched.** A photo
  document stays in the private bucket (only the public avatar copy is deleted), a giỗ event keeps
  its title and date, and approving a change request written before the anonymisation would write
  its values back. Each needs its own rule.
- **Marriage dates and places** are attributes of the edge, not of the person, and are kept.
- **A person shared by two clans** is anonymised for both: a person row is global and the route
  scopes by membership, as `PATCH` and `DELETE` do.
- **An access token issued before the deletion still verifies until it expires** (Supabase's
  default is one hour). A request in that window provisions a fresh, empty profile row through
  `ensure_user_profile`, with the email from the token and no clan. A client must sign out on
  200. A tombstone that refuses a deleted `sub` would close it; it is not built here.
- **Backups**: the nightly dump and its B2 copy keep a deleted account's rows until they age out
  ([ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md)'s
  retention). A restore brings them back.
- **No client screen calls either route yet.** #333 builds the backend and the notice page; the
  web settings screen for deleting an account and the admin action for anonymising a person are
  later work, and mobile is out of #333's scope.

## How it is held

- `tests/integration/test_account_deletion.py`: the provider fake receives `delete_user`; roles,
  tokens and profile are gone; the linked person stays; the audit row carries no email or name;
  the last admin is refused with nothing deleted; a co-admin may delete; a provider outage
  leaves every row. Real `RlsSession` for `get_db`, privileged `get_system_db`.
- `tests/integration/test_person_anonymisation.py`: the H4 family read through `GET /tree`
  before and after; fields cleared at the row; edges intact; đời unchanged for every node; editor
  refused; another clan's admin gets 404. Negative controls (edges dropped, gender cleared) are
  recorded in its header.
- `tests/unit/domain/test_person_entity.py::TestPersonAnonymise`: every client-writable field is
  filled, and after `anonymise()` only `gender` and `nationality` still hold what was written, so a
  field added later that anonymise forgets fails here.
- `web/src/app/[locale]/privacy/page.test.tsx`: the notice renders with the banner in `vi` and
  `en`.

## Related

- [ADR-027](027-doi-single-authority.md), con theo đời cha
- [ADR-036](036-public-avatar-urls.md), the public avatar
- [ADR-043](043-audit-notification-rls-posture.md), the append-only audit trail
- [ADR-048](048-invitation-accept-runs-on-the-system-session.md), a route scoped by something other than a clan
- [ADR-050](050-user-clan-roles-clan-keyed-mutations.md), `user_clan_roles` mutations are clan-keyed
- [ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md), the assessment owed
- `docs/contracts/rest-auth-api.md` § `DELETE /me`, `docs/contracts/rest-persons-api.md` § anonymise
