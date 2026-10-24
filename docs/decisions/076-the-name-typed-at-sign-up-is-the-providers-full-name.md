# ADR-076: The Name Typed at Sign-Up Is the Identity Provider's `full_name`, the One Store the Auth Path Reads

## Status

Accepted (2026-10-24), resolving issue #300, "GET /auth/me answers an empty full_name for a
password sign-up, though the typed name is stored". The owner chose the store on 2026-10-24.

**This ADR ships backend code**: `IdentityProvider.create_user` takes `full_name`, and the Supabase
adapter writes it to the new account's `user_metadata`. No request or response shape changes. It
amends [ADR-058](058-registration-may-name-no-clan.md) § 7, whose premise was that nothing carries
`full_name` to the provider.

Readings were taken on branch `fix/300-me-full-name`, based on `main` at `8636699`.

## Context

**A person's name was kept in two stores, and the auth path read the one register never wrote.**
Read at source on `main` at `8636699`:

| Store | Written by | Read by |
|---|---|---|
| The provider's `user_metadata.full_name` | `PATCH /auth/me` (`AuthSessionService.update_profile`), and Google's own profile | `GET /auth/me` and `POST /auth/onboard` from the token (`backend/app/api/v1/auth.py:75,156`), and `POST /auth/login` from sign-in (`backend/app/infrastructure/supabase_identity_provider.py:103`) |
| `user_profiles.display_name` | `ensure_profile_row`, on register, onboard and invitation accept, and `get_current_user`'s first-request provisioning (`backend/app/core/security.py:165`) | the clan's member list and the admin's pending list (`backend/app/api/v1/clans.py:115,152`) |

`IdentityProvider.create_user` took `email` and `password` only, so a password account's
`user_metadata` held no name until the person saved one through `PATCH /auth/me`.

**Measured 2026-10-24 on the local stack** (issue #300): for an account the #291 walk had just
registered as `Người Đăng Ký 291`, `GET /api/v1/auth/me` answered `"full_name": ""` while
`user_profiles.display_name` held the typed name. Since [ADR-075](075-sign-up-names-no-clan-and-onboarding-opens-on-create.md)
every password sign-up meets onboarding, whose name field is required and filled from
`GET /auth/me`, so every such person typed their name twice.

**Production holds nothing to backfill.** Read 2026-10-24 with `supabase db query --linked`:
`auth.users` 1, of which 1 has no `full_name` in its metadata, and `user_profiles` 0. No typed name
exists anywhere to copy.

## Decision

### 1. The provider's `user_metadata.full_name` is the one store the auth path reads a name from

`GET /auth/me`, `POST /auth/login` and `POST /auth/onboard` read it, as they already did. Nothing on
the auth path reads `user_profiles.display_name`.

### 2. `POST /auth/register` writes the typed name there

`AuthCommandHandler.register` passes `full_name` to `create_user`
(`backend/app/application/auth/handlers.py:326-328`), and `SupabaseIdentityProvider.create_user`
sends it as `user_metadata: {"full_name": ...}` with the account
(`supabase_identity_provider.py:77` on this branch). The account is created
unconfirmed, as before, so the first token that carries the name is the one minted at sign-in after
confirmation.

### 3. A name saved later, and a Google name, keep winning

`PATCH /auth/me` writes the same `user_metadata.full_name`, so a saved name replaces the typed one
from the next token on. A Google account's name comes from Google's profile into the same store.
Neither path changes.

### 4. `user_profiles.display_name` stays, and is still written at register

The clanless path still writes the profile row with the typed name (ADR-058 § 1 and § 7), and the
clan paths still write it beside the membership. Invitation accept's `ensure_profile` is still
`ON CONFLICT DO NOTHING`, so the register row stays. What changes is that accept now offers the same
name from the token, not an empty one, so the row is no longer the only place the typed name lives,
and a reading after accept can no longer tell which writer wrote it (see "How it is held").

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **`user_profiles.display_name` becomes the store `/me`, login and onboard read** | `PATCH /auth/me` would have to write it, which puts a database session into `AuthSessionService`, built DB-free on purpose. A Google user has no row until onboard or a first request, so the read would need the provider's name as a fallback anyway. A larger change for the same outcome |
| **Read both, the provider's name first and `display_name` when it is empty** | It also fixes accounts made before this change. But every auth read would consult two stores, and the two still disagree after a `PATCH /auth/me`. Production holds no account it would fix |
| **Backfill `user_metadata` from `display_name`** | Production has no `user_profiles` row, so there is nothing to copy |

## Consequences

### What this buys

- **A password sign-up reads back the name it typed**, on login, on `GET /auth/me`, and on
  onboarding's form, which now opens filled.
- **One store for the auth path.** The typed name, a saved name and a Google name all live in the
  provider's metadata.

### What this costs, stated plainly

- **An account created before this change keeps an empty name** until it is saved through
  `PATCH /auth/me`. Production has one such account. Locally, every account an earlier walk
  registered is one.
- **`display_name` still drifts from the provider's name after a `PATCH /auth/me`.** `PATCH` never
  wrote `display_name`, so the member list and the pending list keep showing the first name. That
  is older than this ADR, and this ADR does not change it.
- **`create_user` sends one more field to the provider.** A provider that refused it would fail
  registration. Supabase accepts it: the authenticated walk below creates its account this way.

## What this deliberately does not decide

- **Whether `PATCH /auth/me` also writes `display_name`**, closing the drift above. That is a
  change to the member list's source, and it needs its own reading of who reads that column.
- **Which name an admin sees** on the pending list for a Google user who later renames themselves.

## How it is held

- `backend/tests/integration/test_auth_http_flow.py::test_the_name_typed_at_register_is_the_name_login_and_me_answer`
  registers a password account with no clan and a name, signs in, and reads `full_name` from the
  login body and from `GET /auth/me`. The stub provider keeps what `create_user` is handed and mints
  it into the token, as Supabase does. With the handler planted to hand `create_user` an empty name,
  it failed on 2026-10-24 with `assert '' == 'Người Đăng Ký 300'`.
- `web/e2e/auth/signs-up-with-no-invitation.auth.spec.ts`, against the local Supabase stack, now
  reads onboarding's name field already holding the typed name, instead of typing it again. With
  the adapter's `user_metadata` line removed and the backend restarted, it failed on 2026-10-24:
  `getByLabel('Họ và tên')`, `Expected: "Người Đăng Ký 291"`, `Received: ""`.
- `test_invitee_registers_with_no_clan.py::test_the_name_typed_at_register_survives_accept` reads
  `display_name` twice. After accept alone it no longer told the two writers apart, since both now
  offer the typed name, and a register that wrote no row stayed green. So it also reads the row
  after register, before any sign-in, which only register can have written. With
  `_provision_clanless_account`'s `ensure_profile` removed, it failed on 2026-10-24 with
  `assert None == 'Nguoi Duoc Moi'`.

## Related

- [ADR-058](058-registration-may-name-no-clan.md) § 7: the profile row this keeps, and the premise
  this amends.
- [ADR-075](075-sign-up-names-no-clan-and-onboarding-opens-on-create.md): put every password sign-up
  in front of onboarding's name field, and named this as its cost.
- [ADR-061](061-the-auth-session-is-server-state-and-access-is-routed-on-the-server.md): the web
  session reads `GET /auth/me`.
- `docs/contracts/rest-auth-api.md`, "Profile field semantics".
