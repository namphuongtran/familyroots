# The local Supabase stack

**What it is for.** Auth and Storage, locally, so a test can hold a real session. Nothing else.
Added by seed S-072 on 2026-08-22, because five seeds in a row could not reach an authenticated
route and four of them invented the same throwaway-route workaround.

**Read this first if you are about to change `supabase/config.toml`.** Two of its settings are load
bearing in a way the CLI's own comments do not explain, and both are recorded below.

---

## The topology: two databases, on purpose

Production runs **two separate databases**, and the local stack mirrors that rather than merging
them:

| | Application database | Supabase database |
|---|---|---|
| Production | Render-managed Postgres, `infra/render/render.yaml:17-20,67-73` | the Supabase project, which supplies only `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (`render.yaml:50-54`) |
| Local | `pgdb` in `docker-compose.yml`, port 5432 | `supabase_db_familyroots`, port 54322 |
| Owns | every application table | `auth.*` and Storage |
| Migrated by | Alembic | the Supabase CLI |

**Neither migrates the other.** No Alembic revision may reach into the Supabase database, and
nothing in `supabase/` may create an application table. A user therefore exists in two places at
once, joined by the JWT `sub` claim. **Getting those two halves in step is
[`seed-test-users.md`](seed-test-users.md)**, landed by S-073 on 2026-08-22, not this
document. `make seed` is the one command; `make seed-verify` is what tells you which half is
missing.

---

## Start it, stop it

The CLI is **not installed globally and must not be**. `scripts/supabase_local.sh` runs a pinned
version through `npx`, so a developer's machine and CI get the same one:

```bash
scripts/supabase_local.sh up        # start, then WAIT until every container is healthy
scripts/supabase_local.sh down      # stop, keeping the Supabase database
scripts/supabase_local.sh destroy   # stop and DELETE it. Every auth.users row goes too
scripts/supabase_local.sh status    # the CLI's own status output
scripts/supabase_local.sh env       # the three backend variables, ready to paste
```

`make supabase-up` / `make supabase-down` are the same thing.

**Why the wrapper exists, and do not delete it.** `supabase start` gives the storage container three
10-second health probes and no start period. Measured 2026-08-22 on this repository's dev machine,
`storage-api v1.69.11` took **31 seconds** to bind its port from a cold volume. That is four
probes' worth, so the CLI declared it unhealthy and tore the entire stack down. That happened on three consecutive
attempts before the wrapper existed. `up` passes `--ignore-health-check` and then asserts health
itself on a 240-second clock. **The health assertion is not skipped**; only the CLI's too-short
window is. If a container is genuinely broken, `up` still fails and names it.

`scripts/supabase_local.sh wait` runs that assertion on its own, without starting anything. It is
how you prove the assertion still works.

### The health assertion had the "a set is a setting" defect, and the control caught it

Recorded because it is a fourth instance of the pattern in `.claude/rules/seeds.md`, found the same
way as the other three: by planting the failure the check exists to catch.

The first version asked *"is every container I can see healthy?"* and looped over
`docker ps --filter name=supabase_...`. **`docker ps` lists only running containers.** Stopping
`supabase_auth_familyroots`, the one container the whole stack exists for, did not make the check
fail. It made the container leave the set, and the check printed `all containers healthy` over the
five that remained, exit code 0. Measured 2026-08-22.

The fix names the four services that must exist (`db`, `auth`, `kong`, `storage`), asserts each is
**running**, and only then asserts health over every `supabase_*` container `docker ps -a` reports.
Roster first, health second. Three planted failures, each caught and named, all on 2026-08-22:

```
stop supabase_auth_familyroots      → not healthy after 10s:  supabase_auth_familyroots: exited      rc=1
pause supabase_storage_familyroots  → not healthy after 10s:  supabase_storage_familyroots: paused   rc=1
restart supabase_storage (mid-boot) → not healthy after 1s:   supabase_storage_familyroots: starting rc=1
intact stack                        → all containers healthy                                         rc=0
```

---

## What it costs

Measured 2026-08-22, Docker 29.7.2, Compose v5.4.0, Supabase CLI 2.115.0, macOS on Apple silicon,
with `familyroots-pgdb`, `familyroots-pgadmin` and three `kind` nodes already running:

| | Wall clock |
|---|---|
| First ever start, images not yet pulled | 5 min 27 s, and it **failed** (see "What we turned off") |
| `up` from an empty Supabase database | **1 min 42.7 s** |
| `up` after `down` (database restored from the CLI's backup) | **27.4 s** |
| `down` | 6.2 s |
| `destroy` | 1 min 5.4 s |

**Six containers**, counted 2026-08-22 with `docker ps --filter name=supabase`:

| Container | Image | Why it is here |
|---|---|---|
| `supabase_kong_familyroots` | `kong:2.8.1` | the gateway. `SUPABASE_URL` points at it |
| `supabase_db_familyroots` | `supabase/postgres:17.6.1.159` | holds `auth.*` and the Storage metadata |
| `supabase_auth_familyroots` | `gotrue:v2.195.0` | issues the JWT. **The reason the stack exists** |
| `supabase_storage_familyroots` | `storage-api:v1.69.11` | the two buckets the backend uses |
| `supabase_inbucket_familyroots` | `mailpit:v1.30.2` | catches the verification and reset emails at <http://127.0.0.1:54324> |
| `supabase_rest_familyroots` | `postgrest:v16.1` | **not used by this product.** See below |

### What we turned off, and what we could not

`supabase/config.toml` disables services the CLI starts by default. **The default set was not
counted**, because the default start never reached a running stack. It failed. What the default set
contains beyond our six is named by the CLI's own failure message, quoted here from that run on
2026-08-22:

```
supabase_analytics_familyroots container is not ready: unhealthy
supabase_vector_familyroots container is not ready: unhealthy
supabase_realtime_familyroots container is not ready: unhealthy
supabase_storage_familyroots container is not ready: unhealthy
supabase_pg_meta_familyroots container is not ready: unhealthy
supabase_studio_familyroots container is not ready: unhealthy
```

So `analytics`, `vector`, `realtime`, `pg_meta` and `studio` are in the default set and are not in
ours. Whether the CLI starts anything else by default is not established here.

| Turned off | Why |
|---|---|
| `[analytics]` (Logflare) | nothing reads it, and it is the heaviest service in the set |
| `vector` (log shipper, follows `[analytics]`) | **this pair is what broke the first start.** Both went unhealthy and every other container failed with them, because they all ship logs through `vector`. 5 min 27 s spent to reach that |
| `[realtime]` | grep over `backend/app`, `web/src` and `mobile/lib` on 2026-08-22 found no use of Supabase Realtime anywhere. The only hit was `vi.useRealTimers()` in a Vitest file |
| `[edge_runtime]` | there is no `supabase/functions/` directory |
| `[studio]` | a browser UI onto the Supabase database. Genuinely useful, but not load bearing, and it pulls in `postgres-meta` as well. Turn it back on with `[studio] enabled = true` when you want to look at `auth.users` in a browser; `psql` on port 54322 does the same job |
| `[storage.s3_protocol]`, `[storage.vector]` | `backend/app/infrastructure/storage/supabase_adapter.py` uses the `storage3` REST client, not the S3 protocol |

**`supabase_rest_familyroots` (PostgREST) is running and this product does not use it.** It is
started by `[api] enabled = true`, which is also what starts Kong, and Kong is required. The CLI
does not separate the two. Do not assume PostgREST is load bearing because it is up: nothing in
`backend/`, `web/` or `mobile/` calls `/rest/v1`. The CLI's `--exclude` flag lists `postgrest` among the names it
accepts (`supabase start --help`), if you want to prove that for a single run. Not tried here.

---

## The two settings that are load bearing

### 1. `SUPABASE_URL` is `supabase.localhost`, and `supabase status` prints the wrong thing

```
SUPABASE_URL=http://supabase.localhost:54321      ← use this
API_URL     =http://127.0.0.1:54321               ← what `supabase status` prints. Do NOT paste it
```

GoTrue stamps `[auth] external_url` into every token as `iss`. `backend/app/core/security.py:101`
rebuilds the expected issuer from `SUPABASE_URL`, so the two strings must match **byte for byte**.
`127.0.0.1` cannot mean both the macOS host and the inside of a container, so no `127.0.0.1` value
works for both. `supabase.localhost` does: it resolves to loopback on the host, and
`extra_hosts: ["supabase.localhost:host-gateway"]` makes it resolve inside a container.

**The failure this causes is misleading, which is why it is written down.** A `127.0.0.1`
`SUPABASE_URL` fetches the JWKS successfully, finds the right key, and then fails the issuer check.
Measured 2026-08-22, same stack, same token, only `SUPABASE_URL` differing:

```
SUPABASE_URL=http://supabase.localhost:54321  → HTTP 200  {"data":[]}
SUPABASE_URL=http://127.0.0.1:54321           → HTTP 401  {"error":{"code":"invalid_token", ...}}
```

Nothing in the 401 mentions the issuer. Check `SUPABASE_URL` first.

### 2. Tokens are ES256 and the key is fixed

The local stack serves a real JWKS at `/auth/v1/.well-known/jwks.json` with a single ES256 key, and
GoTrue signs with it. No `signing_keys_path` is needed and none is committed. Read 2026-08-22:

```json
{"keys":[{"alg":"ES256","crv":"P-256","kid":"b81269f1-21d8-4f2e-b719-c2240a840d90","kty":"EC","use":"sig", ...}]}
```

The `kid` was **identical** before and after a `destroy`, so the CLI's local key is fixed rather
than generated per project. The backend caches the JWKS for an hour
(`backend/app/core/security.py:34`); with a fixed key that cache cannot go stale across a restart.

---

## Buckets

`supabase/config.toml` declares the two buckets the backend expects, so a fresh stack has them
without anyone remembering:

| Bucket | Public | Backend setting |
|---|---|---|
| `family-roots-files` | no | `SUPABASE_STORAGE_BUCKET`, `backend/app/core/config.py:79` |
| `family-roots-avatars` | **yes** | `SUPABASE_AVATAR_BUCKET`, `backend/app/core/config.py:88` (ADR-036) |

In production these are still created by hand in the Supabase dashboard. A bucket is a container,
not data: no object is seeded here.

---

## Things that will surprise you

- **The first write after `up` can time out.** GoTrue returned `504 request_timeout` on the first
  `POST /auth/v1/admin/users` after a start (10.1 s, "context deadline exceeded"), and the same
  call took 0.16 s a minute later. Retry once before believing a failure. Seen twice on 2026-08-22,
  once on `/admin/users` and once on `/resend`; the `/resend` email still reached Mailpit.
- **An unconfirmed user cannot log in, even though `[auth.email] enable_confirmations` is `false`.**
  Measured 2026-08-22: a user created with `email_confirm: false` gets
  `400 {"error_code":"email_not_confirmed"}` from the password grant. That is what production does,
  so the setting was left at the CLI default. What `enable_confirmations = false` changes is the
  public `POST /auth/v1/signup` path, which this backend does not use. It creates identities
  through the admin API (`docs/architecture/auth-flow.md`).
- **`destroy` really destroys.** `down` keeps the Supabase database and `up` restores it in 27 s.
  `destroy` deletes it, and every `auth.users` row with it.
- **The two auth rate limits were raised for local use.** `email_sent` 2 → 100 per hour and
  `sign_in_sign_ups` 30 → 300 per five minutes, in `supabase/config.toml`. The CLI defaults are
  below what one e2e run needs. The backend's own rate limit (ADR-021) is unaffected.
- **GoTrue logs a `GOTRUE_MAILER_EXTERNAL_HOSTS` warning on every request.** It is because the Host
  header is `supabase.localhost`. Harmless: email links are built from `external_url`.

---

## Running it beside `docker-compose.yml`

They are **two stacks in two files**, and that is deliberate. The Supabase stack's containers,
ports, volumes and versions are all owned by the CLI and regenerated from `supabase/config.toml`;
transcribing them into `docker-compose.yml` would create a second copy to keep in step, for no gain.
Start both:

```bash
docker compose up -d pgdb          # the application database
scripts/supabase_local.sh up       # auth + storage
```

For a container in `docker-compose.yml` to reach the Supabase stack it needs one line beside its
environment block:

```yaml
    extra_hosts:
      - "supabase.localhost:host-gateway"
```

and `SUPABASE_URL: http://supabase.localhost:54321`. Verified 2026-08-22 by running the backend
image on the `familyroots_familyroots` network with exactly that: the same token that a host-run
backend accepted returned `200 {"data":[]}` from inside the container.

**On Linux CI, check that `supabase.localhost` resolves before relying on it.** It was verified on
macOS only. `host-gateway` works on Linux Docker from 20.10, but host-side resolution of the
`.localhost` TLD is the resolver's business, not Docker's. That is S-074's problem to settle; an
`/etc/hosts` line is the obvious fallback.
