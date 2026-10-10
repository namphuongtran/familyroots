# The local Supabase stack

**What it is for.** Auth and Storage, locally, so a test can hold a real session. Nothing else.
Added on 2026-08-22, because five changes in a row could not reach an authenticated
route and four of them invented the same throwaway-route workaround.

**Read this first if you are about to change `supabase/config.toml`.** Two of its settings are load
bearing in a way the CLI's own comments do not explain, and both are recorded below.

---

## The topology: one database in production, two locally

**Since 2026-10-10, production runs one database** (#251, ADR-066). The Supabase project
`xkmutzxdhdigyfisfrwd` holds the application tables in `public`, beside Supabase's own `auth` and
`storage` schemas. Until then production ran two separate databases: Render's Postgres for the
application, and a Supabase project for auth and storage only. This section used to say the local
stack mirrored that on purpose. **The local stack still runs two, so it no longer mirrors
production:**

| | Application tables (`public`) | Auth and Storage (`auth.*`, `storage.*`) |
|---|---|---|
| Production | Supabase project `xkmutzxdhdigyfisfrwd`, Postgres 17 ([supabase-hosted-project.md](supabase-hosted-project.md)) | the same database |
| Local | `pgdb` in `docker-compose.yml`, port 5432, Postgres 18 | `supabase_db_familyroots`, port 54322 |
| Migrated by | Alembic. In production, from CI ([migrations.md](migrations.md), "How migrations reach production") | Supabase |

**What the local split does not show.** Three differences, each of which a migration has to
survive in production and never meets on `pgdb`:

- **Supabase's API roles.** `pgdb` has no `anon` or `authenticated` role, so migration
  `042_close_data_api_on_public`'s revokes do nothing there, and no Data API can reach it anyway. In
  production both exist, and the anon key ships in the web bundle (ADR-066).
- **A login that is not a superuser.** `pgdb`'s `postgres` is a superuser. Supabase's is not, which
  is why migration `041_grant_app_role_to_login` exists (ADR-066).
- **The Postgres major version**, 18 locally and in CI, 17 in production.

#251 runs the chain against this stack's own database, `supabase_db_familyroots`, to check the
first two. The day-to-day local setup is unchanged.

**Neither side migrates the other's schemas.** No Alembic revision may reach into `auth` or
`storage`, and nothing in `supabase/` may create an application table. A user therefore exists in
two places at once, joined by the JWT `sub` claim. That holds in production too. `auth.users` and
`public.user_profiles` now share a database, but no migration references `auth`, because the chain
must also apply to a plain Postgres with no `auth` schema. **Getting those two halves in step is
[`seed-test-users.md`](seed-test-users.md)**, landed on 2026-08-22, not this
document. `make seed` is the one command; `make seed-verify` is what tells you which half is
missing.

**Merging the databases reopened ADR-059, and ADR-066 answers it.** `user_profiles` and
`user_fcm_tokens` carry no row-level security by decision, because the application database was not
exposed through the Supabase Data API. With the application tables in the Supabase project, two
locks keep it that way: migration `042` revokes `anon`'s and `authenticated`'s privileges on
`public`, and a dashboard step removes `public` from the Data API's exposed schemas
([deployment.md](deployment.md), "Go-live checklist", A). Read
[ADR-059](../decisions/059-user-owned-tables-stay-outside-layer-2.md) § 5 and ADR-066.

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

Recorded because it is a fourth instance of the pattern in `.claude/rules/testing.md`, found the same
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

**On a cold GitHub-hosted runner** the figures are not in yet. The CI job ("The image e2e job in
CI", below) logs each phase, the runner's size and its container count. Its first Actions run on
#193's pull request was meant to fill this in. It did not: every run from #193 to 2026-10-07 failed
at the image pull, before any phase it times ("Pulling from ECR Public", below). The table above is a
warm Mac and does not predict them.

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

The hosted project gets them from the same declaration with `supabase seed buckets --linked`. That
was done on 2026-10-04 ([supabase-hosted-project.md](supabase-hosted-project.md) § 2). A bucket is a
container, not data: no object is seeded here. **Never `supabase config push` this file to the hosted
project.** It would overwrite the hosted Site URL and auth settings with the local ones (same file, § 5).

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
- **The CLI reads any `SUPABASE_*` variable in its environment as a config override.** Measured
  2026-10-06: `SUPABASE_API_PORT=59999 supabase status -o env` printed
  `API_URL="http://127.0.0.1:59999"` against a stack listening on 54321. So do not export the backend's
  `SUPABASE_URL` or keys into a shell that then runs `scripts/supabase_local.sh`. The CI job keeps them
  under `LOCAL_SUPABASE_*` names for this reason.
- **GoTrue logs a `GOTRUE_MAILER_EXTERNAL_HOSTS` warning on every request.** It is because the Host
  header is `supabase.localhost`. Harmless: the two auth emails build their links from the Site URL
  (`supabase/templates/`, #202), and the others from `external_url`.
- **The two auth emails are the repository's templates, and an edit needs a restart to reach
  Mailpit.** Measured 2026-10-09 (#202). `supabase/config.toml` `[auth.email.template.*]` makes the
  CLI bind-mount each file into `supabase_kong_familyroots` and point GoTrue at it
  (`GOTRUE_MAILER_TEMPLATES_RECOVERY=http://supabase_kong_familyroots:8088/email/recovery.html`).
  Three consequences. **GoTrue keeps the body it fetched**: an edit written in place reached kong at
  once, and the next mail still carried the old body until `docker restart supabase_auth_familyroots`.
  **An edit that replaces the file never reaches kong**: `sed -i` gave the file a new inode, and kong
  went on serving the old one, as does any editor that saves by replacing the file. **A new or removed template table
  is an environment change**, set when the container is created. So after any template change, run
  `scripts/supabase_local.sh down` then `up`. [supabase-hosted-project.md](supabase-hosted-project.md)
  § 4 has the bodies and how the hosted project gets them.

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

**On Linux, both halves are read rather than assumed.** Host-side resolution of the `.localhost` TLD
is the resolver's business, not Docker's. Read on this repository's Linux dev machine on 2026-10-06:

- **The host.** `getent ahosts supabase.localhost` answered `::1` and `127.0.0.1` with no
  `/etc/hosts` line, under `hosts: files mdns4_minimal [NOTFOUND=return] dns`.
- **A container.** The backend image, started with `--add-host supabase.localhost:host-gateway` on the
  `familyroots_familyroots` network, fetched `http://supabase.localhost:54321/auth/v1/.well-known/jwks.json`
  and got `200` with the key `b81269f1-21d8-4f2e-b719-c2240a840d90`. The stack publishes its ports
  on `0.0.0.0`, which is what lets the bridge gateway reach them.

The CI job takes both readings again on every run, in its "Name resolution on the runner" and "Boot
the backend image" steps. If the host does not resolve the name, the job adds the `/etc/hosts` line
and says so in the log.

---

## The image e2e job in CI (#193)

`.github/workflows/image-e2e.yml` starts this stack on a GitHub-hosted runner and runs
`pnpm test:e2e:auth` against the **built backend image**, not the source tree. A built image once
refused every production boot while every test stayed green, because every test ran from source
([migrations.md](migrations.md), "Boot-time migration gate"). Compose's `api` service could not have
caught it either. It runs `APP_ENV: development` and bind-mounts `./backend/app` over the installed
package. So the job does not use it.

**Since #252 production does not run this image.** Vercel builds the backend from `backend/` with
its own Python runtime, so the job no longer reads the artefact production runs. It still reads a
production-mode boot of the installed package, which no source-tree test does. The production
reading is the release's `GET /health` ([deployment.md](deployment.md), "The release workflow,
step by step"): `"migrations":"current"` there is what shows the `migrations` package reached the
Vercel bundle.

### What it runs, in order

1. `pgdb` from `docker-compose.yml`, and this stack through `scripts/supabase_local.sh up`.
2. `docker build backend`, the context and Dockerfile Render's blueprint named until #252 retired it.
3. `docker build web`, with its three `NEXT_PUBLIC_*` build arguments set to this stack's URL, its
   anon key, and the backend container's port on the runner.
4. The backend image's own `alembic upgrade head` against `pgdb`, the way Render's
   `preDeployCommand` ran it. Production now migrates from `release.yml`'s `deploy` job instead
   ([migrations.md](migrations.md)). Then `make seed`. Its own `alembic upgrade head` finds nothing
   to do.
5. The backend image, with its own `CMD`, `APP_ENV=production` and no source mount. The step waits for
   `GET /health` to answer 200 with `"migrations":"current"`. If the process exits first, the step
   fails and quotes the container's `RuntimeError:` line.
6. The backend image's own `HEALTHCHECK`, as Docker reports it. The step fails unless it reads
   `healthy` (#230, below).
7. The web image, read once in Chromium. `/vi/login` must render the login form and no
   missing-Supabase banner. Then the container is removed, because the harness does not use it.
8. `pnpm test:e2e:auth`, on `next dev` as on a laptop, against the backend container.

Nothing is uploaded, on success or failure. `web/e2e/.auth/` holds live sessions, and a Playwright
report or trace carries the same cookies in its captured requests. The repository is public, so its
artefacts are downloadable by any signed-in GitHub user.

### Pulling from ECR Public

**The job never got past its first real step until 2026-10-07.** All ten runs from #193's own pull
request to `e77116b` failed in "Pull runtime images", each with `toomanyrequests: Rate exceeded`,
so none reached the stack, the images or the suite. The step pulled the six Supabase images from
`public.ecr.aws` all at once. ECR Public allows an unauthenticated client one image pull per second,
and AWS does not raise that quota ("Rate of unauthenticated image pulls", [its service quotas
page](https://docs.aws.amazon.com/AmazonECR/latest/public/public-service-quotas.html)). A hosted
runner shares its address with other jobs, so the budget is not even the job's own.

The step now pulls them one at a time, and retries a refused pull after 5, 10, 20, 40 and 80
seconds. A sixth refusal fails the step with `::error::<image> did not pull in 6 attempts`, so a
registry outage still reads as one. `pgdb` comes from Docker Hub and still pulls alongside.

Read 2026-10-07 against a registry stand-in, which refuses an ECR pull that starts while another is
in flight. The stand-in ran the step's own `run` block, taken out of the workflow file:

| Step | Registry | Result |
|---|---|---|
| as on `main` | refuses bursts | exit 1, five of six images refused, as in CI |
| one at a time | refuses bursts | exit 0, all six pulled, none refused |
| one at a time | also refuses each image's first two attempts | exit 0, twelve warnings, waits of 5 and 10 s |
| one at a time | refuses each image six times | exit 1 on the first image, after 155 s of waiting, naming it |

What a stand-in cannot show is whether one pull at a time stays under a limit that a runner's
neighbours also spend. The first green run in Actions is that reading. If the retries are seen
spending minutes, authenticating to ECR Public is the next step. That needs an AWS identity the
repository does not have.

### The backend's environment satisfies the production validator and does not relax it

| Variable | Value in the job | Why it passes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@pgdb:5432/family_roots` | `pgdb` is a name on the compose network the container joins. Inside a container, `localhost` would not be the database anyway |
| `ALLOWED_HOSTS` | `["127.0.0.1"]` | every request reaches the container through `127.0.0.1:8073` on the runner |
| `CORS_ORIGINS` | `["http://127.0.0.1:3102","http://familyroots-web.test:3102"]` | the harness's auth origin, and the invite link's. The CORS refusal checks for `localhost` and `*`, not `127.0.0.1` (`backend/app/core/config.py:241-244`) |
| `INVITE_LINK_ORIGIN` | `http://familyroots-web.test:3102` | see below |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | `false` | nothing proxies the container. Production sets `true`, because Vercel overwrites `X-Forwarded-For` with the client's address ([deployment.md](deployment.md), "Go-live checklist", C) |
| `RATE_LIMIT_AUTH_MAX_REQUESTS` | `1000` | the validator refuses only a value below 1, in every environment. **The one value here that production does not run**: production sets nothing, so it keeps the default 20 (ADR-021, amended by #226). Every request reaches the container from one address, and a full run spends 28 from the bucket in under a minute (2026-10-07). See "The job inherited the harness's rate-limit collision" below |
| `APP_SECRET_KEY` | `openssl rand -hex 32`, per run | anything but the default passes. Production's is set by hand in Vercel |
| `SUPABASE_URL` and both keys | this stack's, from `scripts/supabase_local.sh env` | `supabase.localhost`, for the reason in "The two settings that are load bearing" |

**`INVITE_LINK_ORIGIN` is a name, because the validator refuses the harness's origin.** Since #191 the
validator refuses an empty or loopback value (`config.py:247-251`, `names_loopback`).
`invitation-link.auth.spec.ts` opens the link the backend builds, so the link has to reach the
harness's `next dev` on `127.0.0.1:3102`. The job adds `127.0.0.1 familyroots-web.test` to the
runner's `/etc/hosts` and builds links on that name. `.test` is reserved by RFC 2606, so it resolves
nowhere else. Do not "fix" this by loosening `names_loopback`. That refusal is what stops a production
deployment from handing every invitee a link to `localhost`.

**So `CORS_ORIGINS` lists that name too.** A page opened from the link has the origin
`http://familyroots-web.test:3102`, and `invitee-registers.auth.spec.ts` (#196) registers from it.
With only `127.0.0.1` listed, the browser's preflight was refused. The job's first run past the image
pull (2026-10-07, run 37547827576) logged `"OPTIONS /api/v1/auth/register HTTP/1.1" 400 Bad Request`
twice, and the walk timed out waiting for the registration message. On a laptop the recipe in
`web/CLAUDE.md` sets `INVITE_LINK_ORIGIN` to the auth origin itself, so the two origins are one, which
is why no local run saw it.

**The name also has to be in `web/next.config.ts`'s `allowedDevOrigins`.** Next 16's dev server
refuses its `/_next/webpack-hmr` socket to a page on any host but `localhost`, `*.localhost` and the
one it was started on (`blockCrossSiteDEV` in Next 16.2.12's
`dist/server/lib/router-utils/block-cross-site-dev.js:77-108`). Measured on this repository's Linux
dev machine on 2026-10-06 at `f6f9409`: a Playwright script launched Chromium with
`--host-resolver-rules=MAP familyroots-web.test 127.0.0.1`, opened
`http://familyroots-web.test:3192/vi/invitations/<token>`, waited 15 s and listed the page's
headings. The port is 3192 because the rehearsal ran with `E2E_PORT_BASE=3190`, clear of the
machine's own dev servers. The job uses 3102.

| Server | `allowedDevOrigins` | Headings on the page |
|---|---|---|
| `next dev` | unset | `Lời mời tham gia dòng họ`, and the button stays on `Đang tải...` |
| `next dev` | `['familyroots-web.test']` | `Hãy đăng nhập trước`, the signed-out state the spec reads |
| the web image, `next start` | unset | `Hãy đăng nhập trước` |
| `next dev`, at `127.0.0.1` instead | unset | `Hãy đăng nhập trước` |

The first row is what `invitation-link.auth.spec.ts`'s first case read in a local rehearsal of the
job, before the entry existed: the heading it waits for never appeared, on the first try or the retry. The page is not a secure context at that name
(`isSecureContext` false, no `crypto.subtle`), and the third row shows that is not the cause. Why a
refused HMR socket leaves the session read pending was not established.

### The image's own `HEALTHCHECK` reports healthy here, and the job reads it (#230)

`backend/Dockerfile`'s `HEALTHCHECK` runs `python -m app.healthcheck` (`backend/app/healthcheck.py`).
It sends `GET /health` to `127.0.0.1:8000` under a `Host` taken from the container's own
`ALLOWED_HOSTS`, read through the same `Settings` the app builds: the first entry, a name under the
domain when that entry is a `*.domain` wildcard, and `localhost` for the development default `["*"]`.
`TrustedHostMiddleware`, its place in the stack and `ALLOWED_HOSTS` are unchanged, and no path is
exempted from the host check. The probe exits 1 on anything but a 200, and `/health` reads the
database, so a database that is unreachable or behind still reads unhealthy.

**Why it changed.** Until #230 the probe requested `http://localhost:8000/health`. This job's
`ALLOWED_HOSTS` is `["127.0.0.1"]`, which does not list `localhost`, so `TrustedHostMiddleware`
answered 400 and Docker marked a healthy container unhealthy. Read on this repository's Linux dev
machine on 2026-10-06 at `f6f9409`, with the image booted as the job boots it: six
`"GET /health HTTP/1.1" 400 Bad Request` lines from the probe beside two 200s from the runner, and
`docker inspect` read `unhealthy failing-streak=7`. Render's `["familyroots-api.onrender.com"]` did
not list `localhost` either, and no production list does.

**Read on 2026-10-10**, on the macOS dev machine with Docker 29.8.2, on #230's branch based on
`3169076`. Each container was booted under `APP_ENV=production` beside a throwaway Postgres, migrated
by the image's own `alembic upgrade head`, and read once it had left `starting` and one more
`--interval` had passed:

| Container | `ALLOWED_HOSTS` | Docker's reading | The probe's last line, from `.State.Health.Log` | `GET /health` in the container log |
|---|---|---|---|---|
| the image | `["127.0.0.1"]` | `healthy failing-streak=0` | `GET /health (Host: 127.0.0.1) -> 200` | 5 × `200 OK` |
| the image | `["*.familyroots.example","api.familyroots.example"]` | `healthy failing-streak=0` | `GET /health (Host: healthcheck.familyroots.example) -> 200` | 5 × `200 OK` |
| control 1: the old probe put back | `["127.0.0.1"]` | `unhealthy failing-streak=4` | `urllib.error.HTTPError: HTTP Error 400: Bad Request` | 7 × `400 Bad Request` |
| control 2: the image, its `CMD` replaced by `sleep 600` | `["127.0.0.1"]` | `unhealthy failing-streak=4` | `ConnectionRefusedError(111, 'Connection refused')` | none |

Control 2 is the one that shows the probe can still fail. Without it, a probe that reported healthy
because of the host it sends would read the same as one that measures `/health`.

**Starlette admits the wildcard pattern itself as a Host**, because it matches `*.domain` by suffix,
so sending `*.familyroots.example` literally would also pass the middleware. `*` admits `*` too. The
probe sends a name instead, and `backend/tests/unit/test_image_healthcheck.py` reads the Host the
server received, not only the status. That test runs the probe against a real uvicorn behind
`TrustedHostMiddleware` for each `ALLOWED_HOSTS` shape the validator admits, and reads `create_app`'s
own answer to the Host the probe takes from its settings, so the probe cannot drift from the list
the app hands its middleware.

**Compose's `api` service runs the same probe.** It sets only the timings, and Docker keeps an
image's test when a container sets none. A container compose created read
`"Test":["CMD","python","-m","app.healthcheck"]` with compose's 15 s interval, and, run against a
throwaway database under compose's `APP_ENV: development`, `healthy failing-streak=0` with the probe
sending `Host: localhost`.

**The job reads it**, in the step after the boot. It waits for Docker to leave `starting` and fails
unless the status is `healthy`. 150 s covers a failing probe, which reads `unhealthy` about 125 s
after the container starts at worst: failures inside the 15 s `--start-period` do not count, and
each of the three that do starts 30 s after the previous probe ended, which can take its full 5 s
`--timeout`. **Since #252 no production container exists.** Vercel runs the backend from source
with its own Python runtime, so the image's `HEALTHCHECK` matters only to compose and to this job.

### The job inherited the harness's rate-limit collision, until #226

**History.** Since #226 (2026-10-07) the job's `api.env` sets `RATE_LIMIT_AUTH_MAX_REQUESTS=1000`,
the same value as the local recipe in `web/CLAUDE.md`, so the suite no longer meets the backend's
bucket. Production still runs the default 20 (ADR-021, amended by #226). The two local rehearsals
below are the reading that opened #226 for this job, and they were taken before the change, so
they read the old limit. The first Actions run with both this change and #239's pull fix in it is
the job's own reading.

Until #226, `web/CLAUDE.md` recorded that a full `pnpm test:e2e:auth` run spends the backend's
20-requests-per-60-seconds bucket on `/api/v1/auth`, which `backend/app/main.py` then hardcoded. The
job ran the suite as written and did not change that limit, so it inherited the collision. Every
request reaches the container from one address, the compose network's gateway, so they share one
bucket, the same as `127.0.0.1` on a laptop. Two local rehearsals of the job on 2026-10-06
at `f6f9409`, against the backend image, with the 429s counted by
`docker logs <backend container> 2>&1 | grep -c ' 429 '` after each run:

| Workers | Result | 429s in the container log |
|---|---|---|
| 4, the Playwright default on this 8-core machine | 17 passed, 1 flaky, 3 failed. Two failures and the flaky case are `guard.auth.spec.ts`'s super_admin cases, on 429s. The third is the invitation case, a run made before `allowedDevOrigins` existed | 7 |
| 2, the default on a 4-vCPU runner | 19 passed, 2 flaky, each passing on its `CI` retry | 2 |

A pass that leans on retries is a gate that will one day go red for a reason in no diff. The defect
was in the suite's request budget or in the limit, not in this job. #226 fixed it in the limit,
for the harness's backend only, by making the count a setting and raising it in both recipes.
