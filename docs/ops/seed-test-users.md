# Seeding test users into both databases

**What it is for.** One command that produces a clan, an admin, an editor, a viewer, and a
user outside that clan, so that a test can log in through the real flow and reach a real
authenticated screen. Added by seed S-073 on 2026-08-22.

**Read [`local-supabase.md`](local-supabase.md) first.** This document assumes the local
Supabase stack is up and that you know why `SUPABASE_URL` must be `supabase.localhost`.

---

## The whole difficulty, in one paragraph

**A test user exists in two places at once.** The identity — the email, the password, the
`sub` — lives in the Supabase stack's `auth.users`, which GoTrue owns. The membership, the
role, and the clan live in the application database, which Alembic owns. **They are joined
by the JWT `sub` claim**, and nothing enforces that join.

If the two halves disagree, **the login succeeds**. The token is valid, the signature
checks, the issuer matches. Then every clan-scoped request answers
`403 no_approved_clan_membership`, which reads like an authorization bug and is not one.
Measured 2026-08-22 against a running backend, with `editor@`'s `user_clan_roles` row
deleted and its `auth.users` row left alone:

```
POST /auth/login   -> 200
GET  /persons      -> 403  {"error":{"code":"no_approved_clan_membership", ...}}
GET  /clans/me     -> 403  {"error":{"code":"no_approved_clan_membership", ...}}
```

Nothing in that says "a row is missing in the other database". That is what
`scripts/seed_dev_data.py verify` exists to say.

---

## Run it

```bash
docker compose up -d pgdb            # the application database
scripts/supabase_local.sh up         # auth + storage, and WAIT for health
make seed                            # <- this one. alembic upgrade head, then both halves
make seed-verify                     # check the two halves agree, change nothing
```

`make seed` took **23.8 s** from two empty databases, measured 2026-08-22 (most of it is
the 39-revision Alembic chain). It is safe to run repeatedly; see "Running it twice".

Under the hood it is `scripts/seed_dev_data.py`, which takes three commands:

| Command | Does |
|---|---|
| `apply` (the default) | create or repair both halves, then `verify` |
| `verify` | read both halves and name any disagreement. Changes nothing |
| `dump` | canonical JSON of both halves, sorted, timestamps included — for a `diff` |

It reads three environment variables and **does not read `backend/.env`**, so what it
targets is always visible in the command that ran it: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`. `make seed` fills in the last two from
`scripts/supabase_local.sh env` and defaults the first to `docker-compose.yml`'s `pgdb`
credentials — but **whatever you have already exported wins**, so
`DATABASE_URL=... make seed` targets your database.

---

## What gets seeded

Two clans and four users. Every password is `dev-password-s073`.

| Email | Clan | Role |
|---|---|---|
| `admin@familyroots.example.com` | `nguyen-phuc` | admin |
| `editor@familyroots.example.com` | `nguyen-phuc` | editor |
| `viewer@familyroots.example.com` | `nguyen-phuc` | viewer |
| `outsider@familyroots.example.com` | `tran-gia` | admin |

```
nguyen-phuc = aaaaaaaa-0000-4000-8000-000000000001
tran-gia    = bbbbbbbb-0000-4000-8000-000000000002
```

**`outsider@` is the point of the second clan.** Clan isolation cannot be tested from
inside one clan: a "clan B cannot see this" assertion needs a caller who is genuinely
outside clan A. The four users are in exactly one clan each, and the two member sets are
disjoint — pinned at the database layer by
`backend/tests/integration/test_seed_dev_data.py::test_the_two_clans_have_disjoint_member_sets`.

**Nobody is a member of both clans, on purpose.** A user in two clans makes
`get_current_clan_id` answer `400 multiple_clans_no_selection` whenever a caller omits
`X-Current-Clan-Id` (`backend/app/core/security.py`), which every e2e test would then have
to work around. Add such a user when a test needs the clan switcher, and give it its own
email rather than changing one of these four.

**Nothing else is seeded.** No persons, marriages, parent-child links, documents or events:
a role check needs none of them, and S-073 put them out of scope. `clan_memberships` is
untouched too, and that is not an oversight — it links a **Person** to a clan, not a user,
so it cannot be written without inventing person fixtures.

### Two decisions inside the fixture that are not free

**1. The ids are constants, so the two halves join by construction.** GoTrue's admin API
accepts an explicit `id` on create — verified 2026-08-22 against `gotrue v2.195.0`: a
`POST /auth/v1/admin/users` carrying `"id": "11111111-…"` returned `200` with that id, and
the password grant then issued a token whose `sub` was that same string. So the application
database is seeded with the uuid the token will carry, rather than creating the identity
first and reading it back. Two consequences worth knowing. There is no ordering dependency
between the halves, so either can be rebuilt alone. And a `destroy` of the Supabase stack
followed by `apply` restores the *same* ids, so the application database does not go stale.

**2. The email domain is `familyroots.example.com`, and `familyroots.test` does not work.**
`.test` is the obvious choice and it fails in a way that costs an hour. GoTrue creates an
identity at a `.test` address happily. `POST /api/v1/auth/login` then answers **before it
ever reaches Supabase**:

```
422 {"error":{"code":"validation_error","detail":{"fields":["body.email"]}}}
```

`LoginRequest.email` is a Pydantic `EmailStr` (`backend/app/schemas/auth.py:45-46`), and
`email_validator` rejects `.test` and `.local` with "The part after the @-sign is a
special-use or reserved name that cannot be used with email". Measured 2026-08-22.
`example.com` is reserved by RFC 2606 for exactly this purpose, its subdomains pass the
validator, and mail to it cannot reach a real party.
`test_every_fixture_email_survives_the_api_s_own_email_validator` pins this by constructing
the real request DTO, not by matching the domain string.

---

## What each user can reach, measured

Measured 2026-08-22 against a backend on `:8073` with `RLS_ENABLED=true`, on a stack
seeded from two empty databases. Every user sent `X-Current-Clan-Id` for their own clan.
Every login returned `200` with the right clan and role in `data.user`.

| | admin | editor | viewer | outsider (clan B) |
|---|---|---|---|---|
| `POST /auth/login` | 200 | 200 | 200 | 200 |
| `GET /me/clans` | 200 | 200 | 200 | 200 |
| `GET /clans/me` | 200 | 200 | 200 | 200 |
| `GET /persons` | 200 | 200 | 200 | 200 |
| `POST /persons` | 201 | 201 | **403** `insufficient_permissions` | 201 |
| `GET /clans/me/users` | 200 | 200 | 200 | 200 |
| `PATCH /clans/me` | **500** (see below) | 403 `insufficient_permissions` | 403 `insufficient_permissions` | **500** |
| `GET /persons` with the **other** clan's id | **403** `clan_membership_required` | **403** | **403** | **403** |

Three readings in that table deserve a sentence each.

**`GET /clans/me/users` returns 200 for a viewer, and that is correct.** The route carries
`RequireViewer` (`backend/app/api/v1/clans.py:87,92`). The `../architecture/rbac.md` matrix
row that is admin-only is "View **pending** users", which is a different route,
`GET /clans/me/users/pending`. Do not read the 200 as a permissions defect.

**The last row is the two-sided half, through the API.** Every user's own token, pointed at
the clan they do not belong to, is refused by `get_current_clan_id` before any handler runs.

**`PATCH /clans/me` answers 500, and it is a real backend defect that has nothing to do
with seeding.** It is recorded here because this fixture is what made it visible: nobody
could log in as a clan admin before. See the next section.

### `PATCH /clans/me` 500s on every real edit — found by S-073, not caused by it

Measured 2026-08-22, reproduced on demand:

```
change motto to A            -> 500  {"error":{"code":"internal_error", ...}}
set motto to A again (no-op) -> 200
set motto to A again (no-op) -> 200
change motto to B            -> 500
```

**The write lands every time.** After three 500s the column held the third value. So the
client is told the edit failed while the database took it.

The cause, from the traceback:

```
File "backend/app/api/v1/clans.py", line 84, in update_own_clan
    return {"data": ClanResponse.model_validate(clan).model_dump()}
pydantic_core.ValidationError: 1 validation error for ClanResponse
updated_at
  Error extracting attribute: MissingGreenlet: greenlet_spawn has not been called;
  can't call await_only() here.
```

The commit expires the `Clan` instance, and reading `updated_at` back out of it in the
route triggers a lazy refresh outside the async greenlet. A no-op update changes nothing,
so nothing is expired, so it returns 200 — which is why this never showed up as "the route
is broken". **This is not S-073's to fix**; it needs its own seed and a contract check on
what `PATCH /clans/me` returns.

---

## Running it twice

**The claim is exact: a second `apply` writes nothing at all**, in either database. Not
"writes the same values" — writes nothing, so no `updated_at` moves.

Every SQL upsert carries a `WHERE` guard on its `DO UPDATE` branch, and the identity half
skips the GoTrue `PUT` when the identity already matches the fixture. Measured 2026-08-22:

```
$ seed_dev_data.py dump > after-1.json
$ seed_dev_data.py apply
seed_dev_data: auth.users  unchanged admin@familyroots.example.com
seed_dev_data: auth.users  unchanged editor@familyroots.example.com
seed_dev_data: auth.users  unchanged viewer@familyroots.example.com
seed_dev_data: auth.users  unchanged outsider@familyroots.example.com
seed_dev_data: app database rows written  clans 0, user_profiles 0, user_clan_roles 0
$ seed_dev_data.py dump > after-2.json
$ diff -u after-1.json after-2.json     # no output, exit 0
```

`dump` includes `created_at` and `updated_at` on purpose. Without them the diff would be
empty even if every row had been rewritten, and the claim would be untestable.

A **repair** run writes only what drifted. With one role row deleted, `apply` reported
`clans 0, user_profiles 0, user_clan_roles 1`.

**A `dump` taken after somebody logged in is not comparable to one taken before, and that
is not the seeder's doing.** `ensure_user_profile` (`backend/app/core/security.py:142`)
refreshes `last_login_at` on an authenticated request, at most once every five minutes, and
`TimestampMixin.updated_at` carries `onupdate=func.now()`
(`backend/app/models/base.py:34-39`), so that ORM update bumps `user_profiles.updated_at`
too. Take both dumps with nothing logging in between, or the diff measures the login rather
than the seeder.

**One thing `apply` does not notice: a password changed by hand.** A password cannot be
read back, so the identity half compares the email, the confirmation and the display name
only. If a fixture user's password stops working, delete that user from `auth.users` and
run `apply` again.

---

## When the two halves disagree

`verify` names **which database is missing its half**, and says in words that the resulting
403 is not a permissions error. Four disagreements were planted on 2026-08-22 and each was
caught and named. Two of them, quoted:

**A membership row deleted, identity left alone.** This is the inversion the whole tool
exists to prevent.

```
seed_dev_data: THE TWO HALVES DISAGREE.
  An identity in the Supabase stack without its row in the application database
  is a user who logs in successfully and can then reach nothing.

  editor@familyroots.example.com (id 22222222-2222-4222-8222-222222222222)
    membership : MISSING  from the application database's `user_clan_roles`
                 expected role 'editor' in clan 'nguyen-phuc' (aaaaaaaa-…-000000000001)
    consequence: this user CAN log in, and every clan-scoped request then answers
                 403 {"error":{"code":"no_approved_clan_membership",...}}.
                 That is NOT a permissions bug. It is the missing row named above.
    fix        : re-run `scripts/seed_dev_data.py apply`

seed_dev_data: 1 problem(s). Exit 1.
```

**The Supabase stack re-created while the application database was kept.** This is the one
`apply` **cannot** repair, so it refuses rather than half-running:

```
seed_dev_data: a fixture email is registered under a different id, so `apply` cannot proceed.
  GoTrue would answer 422 email_exists partway through, leaving half a run.

  viewer@familyroots.example.com
    expected id : 33333333-3333-4333-8333-333333333333  (absent from auth.users)
    found id    : 99999999-9999-4999-8999-999999999999  (holds this email)
```

The other two it names: an identity missing from `auth.users` while the application rows
are complete, and a `user_profiles` row that is gone. It also names an identity that exists
but is **unconfirmed**, because that user gets `400 email_not_confirmed` from the password
grant and never reaches the backend at all.

It refuses to run against anything that is not a local stack. A `SUPABASE_URL` whose host
is not `supabase.localhost`, `127.0.0.1`, `localhost` or `host.docker.internal` is rejected
before the first request: this script creates users with a password written down in a
public file.

---

## Verifying it end to end, by hand

**The test suite does not talk to the Supabase stack, and that is a deliberate limit.**
`backend/tests/integration/test_seed_dev_data.py` exercises the application-database half
against a real migrated Postgres and drives the identity half through a stub. The stack is
one shared container set with fixed fixture ids, so two suites running at once would create
and delete the same four `auth.users` rows underneath each other — the `TEST_PG_DB_NAME`
trap in another costume, with no per-worktree name available to fix it.

So **the GoTrue half is verified by hand**, and this is the procedure:

```bash
scripts/supabase_local.sh destroy && scripts/supabase_local.sh up   # auth.users empty
docker exec familyroots-pgdb psql -U postgres -d postgres \
  -c 'DROP DATABASE IF EXISTS family_roots WITH (FORCE)' -c 'CREATE DATABASE family_roots'
make seed                      # expect: four "created", then a summary table
make seed-verify               # expect: "both halves agree"
# then log in as each user and read what comes back
```

The readings from the last run of that procedure are the table in "What each user can
reach", above, dated 2026-08-22.

---

## Things that will surprise you

- **The first write after `supabase_local.sh up` can return `504`.** The seeder retries a
  502/503/504 up to four times, three seconds apart, and says so on stderr while it does.
  That is not the stack being broken; it is `storage-api` and GoTrue still warming up. See
  `local-supabase.md`, "Things that will surprise you".
- **`supabase status` prints nothing at all while any container reports unhealthy**, even
  one that is answering queries normally. Measured 2026-08-22:
  `supabase_db_familyroots` went unhealthy on "Health check exceeded timeout (2s)" on a
  loaded machine while `psql` against it answered in milliseconds. Before S-073,
  `scripts/supabase_local.sh env` printed its hardcoded `SUPABASE_URL` line, no keys, and
  **exit 0** — a successful-looking command with two of three variables missing. It now
  emits all three or exits 1. If you hit it, `scripts/supabase_local.sh wait` is the
  diagnosis, and exporting the keys yourself is the way past it.
- **`user_clan_roles` will not take a row with `is_approved = true` and no approver.**
  `ck_user_clan_roles_user_clan_roles_approval_consistency` requires `approved_by` and
  `approved_at` to be present together with it. The seeder makes each clan's own admin the
  approver, and that admin's row is self-approved.
- **`make migrate` used `uvx alembic`, which cannot work.** Measured 2026-08-22:
  `uvx alembic upgrade head` in `backend/` ends in
  `ModuleNotFoundError: No module named 'pydantic'`, raised from
  `migrations/env.py:14`, because `uvx` runs alembic outside the project virtualenv and
  `env.py` imports `app.core.config`. `backend/CLAUDE.md` already says only ruff may run
  through `uvx`. S-073 changed the target to `uv run`. **`make backend-lint` still calls
  `uvx mypy app/` and has the same defect**; it is not S-073's to fix and is reported.
