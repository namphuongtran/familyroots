# The local Supabase stack

**What it is for.** Auth and Storage, locally, so a test can hold a real session. Nothing else.
Added on 2026-08-22, because five changes in a row could not reach an authenticated
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
[`seed-test-users.md`](seed-test-users.md)**, landed on 2026-08-22, not this
document. `make seed` is the one command; `make seed-verify` is what tells you which half is
missing.

**Merging the two databases reopens ADR-059.** `user_profiles` and `user_fcm_tokens` carry no
row-level security by decision, because the application database is not exposed through the
Supabase Data API. Move the application tables into the Supabase project and those two tables'
grants become the only thing between the Data API and every user's email and push token. Read
[ADR-059](../decisions/059-user-owned-tables-stay-outside-layer-2.md) § 5 before doing it.

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

### What it runs, in order

1. `pgdb` from `docker-compose.yml`, and this stack through `scripts/supabase_local.sh up`.
2. `docker build backend`, the context and Dockerfile `infra/render/render.yaml` names.
3. `docker build web`, with its three `NEXT_PUBLIC_*` build arguments set to this stack's URL, its
   anon key, and the backend container's port on the runner.
4. The backend image's own `alembic upgrade head` against `pgdb`, the way `render.yaml`'s
   `preDeployCommand` runs it. Then `make seed`. Its own `alembic upgrade head` finds nothing to do.
5. The backend image, with its own `CMD`, `APP_ENV=production` and no source mount. The step waits for
   `GET /health` to answer 200 with `"migrations":"current"`. If the process exits first, the step
   fails and quotes the container's `RuntimeError:` line.
6. The web image, read once in Chromium. `/vi/login` must render the login form and no
   missing-Supabase banner. Then the container is removed, because the harness does not use it.
7. `pnpm test:e2e:auth`, on `next dev` as on a laptop, against the backend container.

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
| `CORS_ORIGINS` | `["http://127.0.0.1:3102"]` | the harness's auth origin. The CORS refusal checks for `localhost` and `*`, not `127.0.0.1` (`backend/app/core/config.py:241-244`) |
| `INVITE_LINK_ORIGIN` | `http://familyroots-web.test:3102` | see below |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | `false` | nothing proxies the container. Render sets `true` because its own proxy terminates TLS |
| `APP_SECRET_KEY` | `openssl rand -hex 32`, per run | anything but the default passes. Render generates one too |
| `SUPABASE_URL` and both keys | this stack's, from `scripts/supabase_local.sh env` | `supabase.localhost`, for the reason in "The two settings that are load bearing" |

**`INVITE_LINK_ORIGIN` is a name, because the validator refuses the harness's origin.** Since #191 the
validator refuses an empty or loopback value (`config.py:247-251`, `names_loopback`).
`invitation-link.auth.spec.ts` opens the link the backend builds, so the link has to reach the
harness's `next dev` on `127.0.0.1:3102`. The job adds `127.0.0.1 familyroots-web.test` to the
runner's `/etc/hosts` and builds links on that name. `.test` is reserved by RFC 2606, so it resolves
nowhere else. Do not "fix" this by loosening `names_loopback`. That refusal is what stops a production
deployment from handing every invitee a link to `localhost`.

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

### The image's own `HEALTHCHECK` reports unhealthy here, and the job does not read it

`backend/Dockerfile`'s `HEALTHCHECK` requests `http://localhost:8000/health`. `ALLOWED_HOSTS` does not
list `localhost`, so `TrustedHostMiddleware` answers 400 and Docker marks the container unhealthy.
Read on this repository's Linux dev machine on 2026-10-06, with the image booted as the job boots it:
the container log held six `"GET /health HTTP/1.1" 400 Bad Request` lines from the probe beside two
200s from the runner, and `docker inspect` read `unhealthy failing-streak=7`. The job reads
`GET /health` from the runner, through the host the backend admits. `render.yaml` sets
`ALLOWED_HOSTS` to `["familyroots-api.onrender.com"]`, which does not list `localhost` either, so the
same probe fails inside a production container too. Whether Render reads the image's `HEALTHCHECK` at
all is not established here. Its blueprint names `healthCheckPath: /health` (`render.yaml:64`).

### The job inherits the harness's rate-limit collision

`web/CLAUDE.md` already records that a full `pnpm test:e2e:auth` run spends the backend's
20-requests-per-60-seconds bucket on `/api/v1/auth` (`backend/app/main.py:221-227`). The job runs the
suite as written and does not change that limit, so it inherits the collision. Every request reaches
the container from one address, the compose network's gateway, so they share one bucket, the same
as `127.0.0.1` on a laptop. #226 tracks the collision. Two local rehearsals of the job on 2026-10-06
at `f6f9409`, against the backend image, with the 429s counted by
`docker logs <backend container> 2>&1 | grep -c ' 429 '` after each run:

| Workers | Result | 429s in the container log |
|---|---|---|
| 4, the Playwright default on this 8-core machine | 17 passed, 1 flaky, 3 failed. Two failures and the flaky case are `guard.auth.spec.ts`'s super_admin cases, on 429s. The third is the invitation case, a run made before `allowedDevOrigins` existed | 7 |
| 2, the default on a 4-vCPU runner | 19 passed, 2 flaky, each passing on its `CI` retry | 2 |

A pass that leans on retries is a gate that will one day go red for a reason in no diff. The defect
is in the suite's request budget or in the limit, not in this job, and it is not fixed here.
