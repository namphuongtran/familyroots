# ADR-078: An Email a Former Account's Profile Row Still Holds Goes to the Account the Provider Now Gives It

## Status

Accepted (2026-10-24), resolving issue #297, "A sign-up that reuses a deleted account's email gets a
500 on its first request". The owner chose the outcome on 2026-10-24 from three: release the email,
refuse with a stable code, or re-link the former row.

**This ADR ships backend code**: `ensure_profile_row` releases the email before it inserts, and
`ensure_user_profile` now provisions through it. No request or response shape changes and there is
no migration.

Readings were taken on branch `fix/297-orphaned-profile-email`, based on `main` at `6d5a160`.

## Context

**A profile row outlives its Supabase account, and keeps its email when it does.**
`user_profiles.id` is the Supabase `auth.users.id` with no foreign key
(`docs/architecture/data-model.md`, `user_profiles`), and `user_profiles.email` carries
`uq_user_profiles_email` (`backend/app/models/user_profile.py`). Both writers of a new row,
`ensure_profile_row` (register, onboard, invitation accept) and `ensure_user_profile` (the first
authenticated request), inserted with `ON CONFLICT DO NOTHING` on `id` only. The comment in
`backend/app/core/security.py` said the email case could not arise, because "Supabase sub<->email is
1:1". That holds among accounts that exist at the same time. It does not hold over time: an account
deleted in the dashboard leaves its row, and so does an account created in a new project before
[ADR-074](074-a-restore-takes-public-whole-and-the-data-of-auth.md)'s `auth` restore. Supabase then
gives the same email to a new account with a new `sub`.

**Measured on `main` at `6d5a160` on 2026-10-24**, with the stub identity provider, real RS256
verification and a real Postgres, against a seeded row holding the email:

| Request | Answer |
|---|---|
| `POST /auth/register` with that email, no clan | 409 `conflict`, and the compensation deleted the new Supabase account |
| `POST /auth/register` with a fresh email | 201 |
| `POST /auth/onboard`, signed in as a new account with that email | 409 `conflict` |
| `GET /auth/me`, same token | 200, because it does not go through `ensure_user_profile` |

The issue predicted a 500. `integrity_error_handler` (`backend/app/core/exceptions.py`) maps every
SQLSTATE `23505` to 409 `conflict`, so the answer was a 409. Either way there were two defects. The
person could never sign up, because every retry created the account and deleted it again. And
register answered this email differently from a fresh one, which tells a caller the email belonged
to an account that was deleted. [ADR-021](021-non-enumerating-auth-surfaces.md) exists to stop
exactly that kind of signal.

**Production holds no such row today.** [ADR-076](076-the-name-typed-at-sign-up-is-the-providers-full-name.md)
read it on 2026-10-24: `auth.users` 1, `user_profiles` 0.

## Decision

### 1. The provider decides who owns an email, and a profile row's email is a copy

Supabase holds one live account per email. A `sub` that arrives with an email, from a verified token
or from `create_user`, is the account the provider gives that email to now. Any other row still
holding the email belongs to an account the provider no longer gives it to.

### 2. Before inserting a new row, the writer releases the email from the other row

`_release_email_held_by_another_profile` (`backend/app/infrastructure/persistence/_profile.py`) is
one `UPDATE` that sets the other row's email to `<its id>@released.invalid`. RFC 2606 reserves
`.invalid`, so the value can never receive mail, and the id makes it unique per row. The response
schemas type a profile email as `str`, not `EmailStr`, so reading the value back raises nothing. The
release is logged at WARNING with both ids and without the email.

### 3. Nothing moves to the new account

The former row keeps its id, `display_name`, its `user_clan_roles` rows, `person_id`, `is_active`,
`platform_role` and its audit history. The new `sub` gets a fresh row with no membership. A clan that
wants the person back invites them, or approves a join.

### 4. The release fires only for the insert it unblocks

It does not fire when the `sub` already has a row, because the insert is a no-op then. It never fires
for an empty email: the provider vouches for no owner of one, and two live accounts may both lack
one, so that insert still fails as before.

### 5. One writer of a new row

`ensure_user_profile` now calls `ensure_profile_row` with its `language` and `last_login_at`. The two
copies of the insert that shared the wrong comment are one. This adds an import from
`app.core.security` to `app.infrastructure.persistence._profile`. No import-linter contract forbids
that edge.

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **Refuse with a stable code**, e.g. 409 `auth.email_held_by_former_account` | Locks the person out until an operator edits the row. Register would also have to stay a silent 201 to keep ADR-021, so the person would read "check your email" and no account would exist |
| **Re-link the former row to the new `sub`** | Hands the former account's clan roles, person link and platform role to whoever controls the email now. If the account was deleted because it was misused, this restores it. This is the account-takeover case the issue named, and it rewrites every table keyed by `user_profiles.id` |
| **Make `email` nullable and set it to NULL on release** | A migration, plus a type change in every reader that treats the email as a string, such as the admin's pending list, for the same outcome |
| **A foreign key from `user_profiles.id` to `auth.users`** | `auth.users` is absent locally and in CI (`backend/app/services/notification.py`, `send_to_clan`), and ADR-074's restore order would have to satisfy it. It also would not decide what the new sign-up gets |

## Consequences

### What this buys

- **A person whose account was deleted can sign up again with the same email** and get a working
  account, through register or through the first-request path.
- **Register answers that email exactly as it answers a fresh one**, so ADR-021 holds for this case
  too.
- **A sign-up admitted during a recovery, before `auth` is restored, still works.** ADR-074 still
  restores `auth` first, so restored rows keep their ids and are not released.

### What this costs, stated plainly

- **A deleted person comes back clean.** Deactivation is per row, on the former id. A person an
  operator deleted, deactivated or not, can sign up again with the same email and gets a fresh
  account without the old roles. They could already do that with another email.
- **An unconfirmed sign-up triggers the release.** Register creates the account unconfirmed
  ([ADR-015](015-email-verification-flow.md)), so someone who does not control the address can
  trigger it. They gain nothing from it: they cannot sign in until the address is confirmed, and the
  new row has no role. The former row shows `<id>@released.invalid` from then on. Its account was
  already gone.
- **A live account whose email was changed at the provider can lose its stale copy.** Only the
  dashboard changes an email, because no product flow does, and nothing syncs `email` after the
  first insert. If someone then signs up with the old address, the live account's row shows the
  placeholder. That column was already wrong.
- **The admin's pending list can show a `.invalid` address** for a former account that had a pending
  join.

## What this deliberately does not decide

- **Whether `ensure_user_profile` should refresh `email` from the token on every request**, the way it
  does `language`. That would close the stale-copy case above, and it would need the same release.
- **Whether emails compare case-insensitively.** The constraint compares exactly, so the release does
  too.
- **Merging a former account into a new one when an operator is asked to.** That stays a manual
  operation.

## How it is held

`backend/tests/integration/test_email_held_by_former_account.py`. Every negative control below was
run on 2026-10-24.

- `test_register_with_a_former_accounts_email_answers_like_any_sign_up` registers the held email and a
  fresh one and requires the same status and body. It then signs in and reads the rows: the new
  account has its own row, holding the email and no role, and the former row keeps its name and its
  admin role under the placeholder. With the release call removed, it failed with
  `assert (409, {...}) == (201, {...})`.
- `test_first_request_through_ensure_user_profile_provisions_the_new_account` sends a token for a new
  `sub` with the held email to `GET /api/v1/platform/clans`, which sits on `ensure_user_profile`. It
  requires the answer a brand-new email gets, 403 `super_admin_required`. With the release removed,
  it failed with `409 != 403`.
- `test_concurrent_first_requests_release_the_email_once` races two first requests for the same `sub`
  and requires exactly one row to end up holding the email. With the release removed, it failed
  with `UniqueViolation` on `uq_user_profiles_email`.
- `test_an_empty_email_is_never_released` failed with the empty-email guard removed.
- `test_a_sub_that_already_has_a_row_takes_no_email` failed with the release's "no row for this
  `sub` yet" predicate removed.

## Related

- [ADR-021](021-non-enumerating-auth-surfaces.md): the property register now keeps for this email.
- [ADR-074](074-a-restore-takes-public-whole-and-the-data-of-auth.md): restores `auth` before traffic,
  which keeps the recovery case rare. #297 did not block it.
- [ADR-076](076-the-name-typed-at-sign-up-is-the-providers-full-name.md): the production reading.
- `docs/architecture/auth-flow.md`, "Per-request identity pipeline", step 2.
