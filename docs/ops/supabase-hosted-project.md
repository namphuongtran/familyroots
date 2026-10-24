# The hosted Supabase project

**Since 2026-10-10 the hosted project is `xkmutzxdhdigyfisfrwd`, and it holds the application
database as well as auth and storage** (#251, #252, ADR-066). Until then the application database
was Render's `familyroots-db`, and a different project, `bftqrkgbulwtbptnpfca` in Tokyo, served
auth and storage only. Render is retired, and nothing was live, so no data moved. This file records
how a project is set up, what it held when it was read, and how to check it again. The local stack
is a separate thing, covered in [local-supabase.md](local-supabase.md).

| | Current project | Retired project |
|---|---|---|
| Ref | `xkmutzxdhdigyfisfrwd` (`https://xkmutzxdhdigyfisfrwd.supabase.co`) | `bftqrkgbulwtbptnpfca` (`https://bftqrkgbulwtbptnpfca.supabase.co`) |
| Region | `ap-southeast-1` (Singapore), beside the Vercel functions in `sin1` | `ap-northeast-1` (Tokyo) |
| Postgres | 17. `supabase projects list` on 2026-10-10 read `"version":"17.11.0.003"`, `"postgres_engine":"17"` | 17 |
| Holds | the application database (`public`, migrated by Alembic from CI, [migrations.md](migrations.md)), auth, and storage | auth and storage only |
| Pointed at by | the backend's `SUPABASE_URL` and `DATABASE_URL`, the web's `NEXT_PUBLIC_SUPABASE_URL`, and the backup secrets ([deployment.md](deployment.md), "Go-live checklist") | `web/.env.local` on the maintainer's machine, as read 2026-10-04 |

**Which sections were read on which project.** § 2, § 3 and the traps in § 5 were read or done on
**2026-10-04**, on the **retired** project, with Supabase CLI 2.119.0, under issue #163. Keep them
as the record of what a fresh project looked like and as the procedure. None of them has been
repeated on `xkmutzxdhdigyfisfrwd`. Every owner step for the current project is listed once, in
[deployment.md](deployment.md), "Go-live checklist", A. Re-run a command before trusting its
reading.

**What the current project needs that the retired one did not**, because it now holds the
application tables:

- **`public` must not be served by the Data API.** Supabase grants `anon` and `authenticated`
  access to new tables in `public` by default, and the anon key ships in the web bundle. Migration
  `042_close_data_api_on_public` revokes those grants, and the dashboard step that removes `public`
  from the exposed schemas is the second lock (ADR-066).
- **The migrating login must be able to `SET ROLE familyroots_app`.** Supabase's `postgres` is
  not a superuser. Migration `041_grant_app_role_to_login` makes it a member (ADR-066), so the
  app's `DATABASE_URL` and CI's `MIGRATION_DATABASE_URL` use that same login.
- **Two connection strings, two poolers.** The app connects through Supavisor's transaction
  pooler on `:6543` with `DB_EXTERNAL_POOLER=true` (#250). CI migrates through the session pooler on
  `:5432` ([migrations.md](migrations.md), "How migrations reach production").

---

## 1. Connect the CLI

```bash
supabase login                                        # once per machine; the token goes to the OS keychain
supabase link --project-ref xkmutzxdhdigyfisfrwd      # writes supabase/.temp/, which supabase/.gitignore ignores
supabase projects list                                # must show the project as ACTIVE_HEALTHY
```

On 2026-10-04 this section linked the retired `bftqrkgbulwtbptnpfca`. A machine linked then is
still linked to it, so run `supabase link` again before any `--linked` command.

`supabase db query --linked "<sql>"` runs SQL through the Management API with a temporary login
role. It needs no database password. It is the reliable way to read `storage.*` and `auth.*` state.

---

## 2. Buckets: done 2026-10-04 on the retired project, not yet on the current one

The backend needs two buckets, declared in `supabase/config.toml` `[storage.buckets.*]`. That is the
same declaration the local stack uses. **On `xkmutzxdhdigyfisfrwd` the seed has not been run.** It
is an owner step ([deployment.md](deployment.md), "Go-live checklist", A). The `supabase` commands
below run unchanged once § 1 links the current project. The two `curl` lines name the retired
host, so put `xkmutzxdhdigyfisfrwd` in its place. The readings below are the retired project's.

**What was there.** `select count(*) from storage.buckets` returned **0**. The private
`family-roots-files` was missing as well as the avatars bucket. Until that day, set-avatar returned 503
and document uploads failed too (#177 covers how that failure was misreported).

**What was done.**

```bash
supabase seed buckets --linked
# {"buckets_created":["family-roots-files","family-roots-avatars"], ...}
supabase db query --linked "select id, public, file_size_limit, allowed_mime_types from storage.buckets order by id;"
```

| id | public | file_size_limit | allowed_mime_types |
|---|---|---|---|
| `family-roots-avatars` | `true` | 52428800 | `null` on that day; #176 adds the list, see § 2a |
| `family-roots-files` | `false` | 52428800 | `null` |

**How it was verified: by outcome, with a control.** The same file went into both buckets and was
fetched without any key:

```bash
echo "familyroots avatar bucket probe" > probe.txt
supabase storage cp probe.txt ss:///family-roots-avatars/probe.txt --linked --experimental
supabase storage cp probe.txt ss:///family-roots-files/probe.txt   --linked --experimental
curl -s https://bftqrkgbulwtbptnpfca.supabase.co/storage/v1/object/public/family-roots-avatars/probe.txt
#   → HTTP 200, the file's body           (pass: an anonymous reader resolves an avatar URL)
curl -s https://bftqrkgbulwtbptnpfca.supabase.co/storage/v1/object/public/family-roots-files/probe.txt
#   → HTTP 400, {"error":"Bucket not found","code":"NoSuchBucket"}   (control: the private bucket refuses)
supabase storage rm ss:///family-roots-avatars/probe.txt ss:///family-roots-files/probe.txt \
  --linked --experimental --yes
```

The two readings differ, and the only difference between the two fetches is the public flag. After
the removal, `storage.objects` held 0 rows.

**Not created:** the private `backups` bucket from the go-live checklist in
[backup-restore.md](backup-restore.md). It is not in `config.toml`, so the seed does not make it.

### 2a. The avatars bucket's MIME list (#176): owner step, NOT yet run on hosted

`supabase/config.toml` now declares
`allowed_mime_types = ["image/jpeg", "image/png", "image/webp", "image/heic"]` on
`family-roots-avatars`. It is a second wall. The rule is `Document.set_avatar`, which refuses
any other declared type before a byte is copied
([storage.md](../architecture/storage.md), set-avatar step 1). The hosted bucket only gets the
list when someone seeds it, **after the #176 pull request merges**:

```bash
supabase seed buckets --linked
#   expect "buckets_updated" to name family-roots-avatars (the seed updates an existing bucket)
supabase db query --linked "select id, allowed_mime_types from storage.buckets order by id;"
#   expect family-roots-avatars | {image/jpeg,image/png,image/webp,image/heic}
#   expect family-roots-files   | null   (until #256: see § 2b, which gives it a list)

printf 'familyroots avatar mime probe\n' > probe.txt     # and any real 1x1 PNG as probe.png
supabase storage cp probe.txt ss:///family-roots-avatars/probe.txt --linked --experimental
#   expect REFUSED: 415 InvalidMimeType, "mime type text/plain; charset=utf-8 is not supported"
supabase storage cp probe.png ss:///family-roots-avatars/probe.png --linked --experimental
#   expect accepted          (control: the bucket still takes an image)
supabase storage rm ss:///family-roots-avatars/probe.png --linked --experimental --yes
supabase db query --linked "select count(*) from storage.objects where bucket_id = 'family-roots-avatars';"
#   expect 0
```

**Why the expectations above are not guesses.** The same sequence ran on the **local** stack on
2026-10-04 with CLI 2.119.0. Before the seed, a `.txt` into the avatars bucket was accepted.
`supabase seed buckets --local` reported `"buckets_updated":["family-roots-files","family-roots-avatars"]`.
After it, the `.txt` was refused with `415 InvalidMimeType` and the `.png` was accepted. The
probes were removed and `storage.objects` held 0 rows for the bucket.

**What the bucket does not check.** In the same local run, the `.txt` sent with
`--content-type image/png` was accepted. The bucket reads the declared type, not the bytes.

When the hosted run is done, replace this section's heading with the date and the readings.

---

### 2b. The files bucket's MIME list (#256): owner step at that release, NOT yet run on hosted

Since #256 the browser uploads a document straight to `family-roots-files` through a signed URL
(ADR-068), so `supabase/config.toml` gives that bucket
`allowed_mime_types` equal to the domain's `ALLOWED_MIME_TYPES`, nine types.
`backend/tests/unit/test_files_bucket_mime_types.py` fails if the two drift. It is a second wall:
the confirm call re-checks the stored type and deletes a file that fails. The hosted bucket gets
the list only when someone seeds it, **after the #256 pull request merges**. The same command
also applies § 2a's list if that was never run:

```bash
supabase seed buckets --linked
#   expect "buckets_updated" to name family-roots-files
supabase db query --linked "select id, allowed_mime_types from storage.buckets order by id;"
#   expect family-roots-files | {image/jpeg,image/png,image/webp,image/heic,application/pdf,audio/mpeg,audio/wav,video/mp4,video/quicktime}
```

**Read on the local stack on 2026-10-11** with CLI 2.115.0, which `scripts/supabase_local.sh`
pins. `supabase seed buckets --local` reported `"buckets_updated":["family-roots-files","family-roots-avatars"]`.
After it, a PUT to a signed upload URL as `text/html` was refused with `415 InvalidMimeType`, and
the same PUT as `image/png` answered 200. Like § 2a's, the wall reads the declared type, not the
bytes.

## 3. Auth settings: read 2026-10-04 on the retired project

Read with `supabase config diff --project-ref bftqrkgbulwtbptnpfca`, which changes nothing. The
"local" column is `supabase/config.toml`, the **local stack's** file. **The current project was read
on 2026-10-18**, with the scratch-directory `config pull --dry-run` of § 4d, which writes nothing:
Site URL `https://familyroots-web.vercel.app`, Redirect URLs `["https://familyroots-web.vercel.app/**"]`,
Confirm email on, OTP length 8, send interval 1 minute, TOTP enroll and verify on, and the SMTP
sender of § 4d. The "Hosted" column below is still the **retired**
project's, and production's Site URL and Redirect URLs are the values just given
([deployment.md](deployment.md), "Go-live checklist", A).

**Google sign-in is off on the current project, read 2026-10-24 (#290).** Two readings, both
read-only. `GET /auth/v1/settings` with the anon key answered `200` with `"google":false` under
`external`, and every other provider but `email` false too. The authorize call answered
`400 {"error_code":"validation_failed","msg":"Unsupported provider: provider is not enabled"}`:

```bash
curl -s -w '\nHTTP %{http_code}\n' "https://xkmutzxdhdigyfisfrwd.supabase.co/auth/v1/authorize?provider=google&redirect_to=https://familyroots-web.vercel.app/api/auth/callback"
```

It stays off by the owner's decision of 2026-10-24. The web offers the Google button only while
`/auth/v1/settings` reports it on (`web/src/features/auth/hooks/use-oauth-providers.ts`), so the
login and register pages show no button today. Turning Google on needs no web change: the steps
are in [deployment.md](deployment.md), "Go-live checklist", and once they are done the authorize
call above answers a redirect to `accounts.google.com`.

| Setting | Hosted | Local file |
|---|---|---|
| Site URL | `http://localhost:3000` | `http://localhost:3000` (`http://127.0.0.1:3000` until 2026-10-24) |
| Redirect URLs | **empty** | `["https://127.0.0.1:3000"]` |
| Confirm email | on | off |
| Email OTP length | 8 | 6 |
| Email send interval | 1 minute | 1 second |
| Google sign-in | on | not declared |
| TOTP MFA enroll / verify | on / on | off / off |

**What these values mean.** Supabase honours a `redirect_to` only when it has the Site URL's scheme
and host (any port, for a loopback host), or when it is listed under Redirect URLs
(`supabase/auth` `internal/utilities/request.go:106-113`). With the values above:

- **Local web on `localhost:3000` works as is.** That covers Google's
  `http://localhost:3000/api/auth/callback`. It covers the email links too. Since #202 the backend
  passes no redirect on either email, so the default template's `redirect_to` is the Site URL, and
  the repository's templates (§ 4) build their link from `{{ .SiteURL }}` itself.
- **A deployed web origin or a mobile deep link does not work yet.** Every redirect to one falls back
  to `http://localhost:3000`. Add the origin under Redirect URLs, and change the Site URL, when the
  web app is first deployed. Since #203 pushed the templates (2026-10-18), the Site URL is also the
  origin of every auth email link, so a wrong one breaks them all (ADR-063, Consequences).

---

## 4. Email templates

**Where the bodies live: in the repository, since #202 (2026-10-09).**
`supabase/templates/confirmation.html` is the **Confirm signup** body and
`supabase/templates/recovery.html` the **Reset Password** body. Each links the URL of
[ADR-063](../decisions/063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md) § 1 and
reads Vietnamese first, English below (§ 7):

| Template | Link |
|---|---|
| Confirm signup | `{{ .SiteURL }}/verify-email/confirm?token_hash={{ .TokenHash }}&type=email` |
| Reset Password | `{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery` |

Two configs carry the same two files:

- `supabase/config.toml` declares `[auth.email.template.confirmation]` and
  `[auth.email.template.recovery]`, so the **local stack's** Mailpit renders the same bodies. A
  template change reaches it only on a restart, `scripts/supabase_local.sh down` then `up`
  ([local-supabase.md](local-supabase.md), "Things that will surprise you", has why).
- `supabase/supabase/config.toml` declares **those two tables and nothing else**. Its workdir is
  the repository's `supabase/` directory. It is the only config a push to this project may come
  from (trap 4).

Each `content_path` is relative to the workdir, the directory that holds `supabase/`, so the two
files name different strings for the same body: `./supabase/templates/…` locally, `./templates/…`
in the hosted one. CLI 2.120.0 refuses a `content_path` that resolves outside the workdir, which is
why the hosted config sits inside `supabase/` rather than beside it.
`backend/tests/unit/test_auth_email_templates.py` resolves both, and checks each link and the
language order.

**What the hosted project holds: the repository's two bodies, since 2026-10-18 (#203).** The owner
pushed them that day (§ 4a), and a hosted recovery email now links the reset page (§ 4c). Both
pages exist: the confirmation page (#200) since 2026-10-07 and the reset pages (#201) since
2026-10-08. Before the push, the hosted project held Supabase's defaults, as read on 2026-10-04:

```html
<h2>Confirm your signup</h2>

<p>Follow this link to confirm your user:</p>
<p><a href="{{ .ConfirmationURL }}">Confirm your mail</a></p>
```

```html
<h2>Reset Password</h2>

<p>Follow this link to reset the password for your user:</p>
<p><a href="{{ .ConfirmationURL }}">Reset Password</a></p>
```

What each shape lands as on the client, and why `?code=` never happens, is in
[frontend-integration-guide.md § 3.1](../contracts/frontend-integration-guide.md).

### 4a. Push the templates (#203, owner step)

#203's body was written on 2026-10-04 and names the retired `bftqrkgbulwtbptnpfca`. Push to the
current project, `xkmutzxdhdigyfisfrwd`, as below.

**The push needs the custom SMTP sender of § 4d.** On 2026-10-11, before there was one, Supabase
refused it with HTTP 400: "Email template modification is not available for free tier projects
using the default email provider." Nothing was written. The sender has been set since 2026-10-18.

**Pushed 2026-10-18 by the owner, to `xkmutzxdhdigyfisfrwd`.** The owner ran § 4b before the push,
the push, and § 4b again, and reported each as expected: the read-back failing first, then exiting
0. The outputs were not kept, so this record carries the owner's report of them, not the text.
Read independently afterwards, without the owner's token:

- `npx --yes supabase@2.120.0 config diff --workdir supabase --project-ref xkmutzxdhdigyfisfrwd`
  reported `"update": 0`, and none of its 19 `remote_only` differences is under
  `auth.email.template`. On 2026-10-11 the same command had read the remote subjects as Supabase's
  defaults, so the two subjects changed. `config diff` never reads a body (trap 3).
- The bodies are evidenced by the recovery email of § 4c: its link has the repository's shape,
  which the default body cannot produce. The confirmation body rests on the owner's read-back
  alone, because no confirmation email has been sent from the hosted project yet.

From the repository root, with the CLI pinned in the command. **Not with a global `supabase`, and
never with 2.115.0**, the version `scripts/supabase_local.sh` pins for the local stack:

```bash
npx --yes supabase@2.120.0 login
npx --yes supabase@2.120.0 config push --workdir supabase --project-ref xkmutzxdhdigyfisfrwd
#   expect four changes listed, then the prompt:
#     auth.email.template.confirmation.subject  [update]
#     auth.email.template.recovery.subject      [update]
#     auth.email.template.confirmation.content  [content]
#     auth.email.template.recovery.content      [content]
#   answer y only if those four are the whole list
```

Then read them back (§ 4b).

**What a push from that config sends, by CLI version.** Measured 2026-10-09 (#202) against a
stand-in for `api.supabase.com`: a local HTTP server, named to the CLI through a `--profile` file's
`api_url`, that answered the CLI's reads and recorded every request. Nothing reached Supabase.

| CLI | Run | What it sent |
|---|---|---|
| 2.120.0 | from the repository root, `--workdir supabase` | one `PATCH /v1/projects/{ref}/config/auth` with **four** properties: `mailer_subjects_confirmation`, `mailer_subjects_recovery`, `mailer_templates_confirmation_content`, `mailer_templates_recovery_content`. Both bodies equal the files byte for byte. It printed "10 remote properties are not declared in supabase/config.toml and were left unchanged" |
| 2.120.0 | the same, answering `n` at the prompt | three `GET`s and no write |
| 2.115.0 | from the repository root, `--workdir` naming the hosted config's directory | **ignored `--workdir`** and read `./supabase/config.toml`, the local stack's file: 46 properties, `rate_limit_otp` 300 from its `sign_in_sign_ups`, then went on to Storage |
| 2.115.0 | from inside the hosted config's own directory | 46 properties, every undeclared one at the CLI's default: `site_url` `http://127.0.0.1:3000`, `uri_allow_list`, `mailer_autoconfirm` true, `mailer_otp_length` 6, `mfa_totp_enroll_enabled` false and the rest |

So 2.115.0 would turn **Confirm email** off, change the OTP length, turn TOTP off and point every
link at `127.0.0.1`, whichever directory it ran from. ADR-063's Context read
"Properties the file does not declare are left unchanged" at the source of 2.119.0. It does not
hold for 2.115.0, which is also the TypeScript CLI. 2.119.0 itself was not run.

### 4b. Read them back, after every push

`scripts/read_back_auth_email_templates.py` reads
`GET https://api.supabase.com/v1/projects/<ref>/config/auth` and compares
`mailer_templates_confirmation_content` and `mailer_templates_recovery_content` with the two files,
**byte for byte**. It needs a personal access token with `auth:read` (Dashboard → Account →
Access Tokens), so it is not a CI job. Standard library only:

```bash
export SUPABASE_ACCESS_TOKEN=sbp_...
python3 scripts/read_back_auth_email_templates.py --project-ref xkmutzxdhdigyfisfrwd
#   expect "match confirmation" and "match recovery", exit 0
```

| Exit | Meaning |
|---|---|
| 0 | both hosted bodies equal their files |
| 1 | at least one differs. Each one is named on a `DIFFERS <name>:` line, with the first differing byte |
| 2 | nothing was compared: no token, a malformed ref, or an unreadable response |

`--response <file>` compares a response saved earlier instead, with no token.
`backend/tests/unit/test_read_back_auth_email_templates.py` runs it that way.

### 4c. Check the email by outcome

The read-back proves what the project holds. The email proves what a person receives:

1. Dashboard → Authentication → Users → an account whose mailbox you own → **Send password
   recovery**.
2. In the email, copy the link **without opening it**. It must begin with
   `<Site URL>/reset-password?token_hash=` and carry `type=recovery`. The Site URL is
   `https://familyroots-web.vercel.app`, read with `config diff` on 2026-10-11 and again on
   2026-10-18. Before #203 it began with `https://xkmutzxdhdigyfisfrwd.supabase.co/auth/v1/verify?token=`
   and carried `type=recovery` and a `redirect_to` naming the Site URL.
3. A link that does anything else (`...`, a missing token, another host) is a broken template.
4. Open it, and set a password on `/reset-password`. The token is spent then, so the account's
   `recovery_token` in `auth.users` reads empty afterwards, `recovery_sent_at` returns to null, and
   `last_sign_in_at` is set.

**Read 2026-10-18 (#203).** The project had no auth user, so the owner created one in the
dashboard (**Add user**, auto-confirmed, on a mailbox the owner holds). `auth.users` read
`created_at` 12:53:35 UTC and `recovery_sent_at` 12:54:13 UTC. The owner read the link as beginning
`https://familyroots-web.vercel.app/reset-password?token_hash=`. At 12:57:01 UTC, before step 4,
the `recovery_token` was unspent and `last_sign_in_at` was null. The owner then opened the link and
set a password. At 12:59:52 UTC the `recovery_token` was empty, `recovery_sent_at` was null,
`last_sign_in_at` read 12:58:52.27 and `updated_at` 12:58:52.84, the password write half a second
after the sign-in.

### 4d. The sender: Resend on the owner's domain (#276, ADR-071)

**Set by the owner on 2026-10-18.** Supabase's default provider delivers only to the project's team,
so every auth email to anyone else goes through this sender
([ADR-071](../decisions/071-hosted-auth-email-goes-out-through-resend-on-the-owners-domain.md)).

| | Value |
|---|---|
| Provider | Resend. The domain and the API key are in the owner's Resend account |
| Domain | `getnami.dev`. Its nameservers are Cloudflare's, and Resend's records live there |
| Sender | `noreply@getnami.dev`. No mailbox stands behind it, and the apex has no MX record |
| Sender name | `Familyroots`, as read. #276 proposed `FamilyRoots`. The casing is the owner's choice |
| Where it is set | Dashboard → Authentication → Emails → SMTP Settings |
| SMTP | host `smtp.resend.com`, port `465`, username `resend` |
| Password | a Resend API key with sending access. **It is set in the dashboard and nowhere else.** Never record it here |
| Email rate limit | 30 an hour (`auth.rate_limit.email_sent`), read 2026-10-18 |

**Read the settings back without writing anything.** `config pull` with `--dry-run` reads every
SMTP field except the password. Run it from a scratch directory, never from the repository's
`supabase/`, so no repository config is involved:

```bash
mkdir -p /path/to/scratch/supabase && printf 'project_id = "scratch"\n' > /path/to/scratch/supabase/config.toml
cd /path/to/scratch
npx --yes supabase@2.120.0 config pull --workdir . --project-ref xkmutzxdhdigyfisfrwd --dry-run
#   expect, under auth.email.smtp: enabled true, host smtp.resend.com, port 465, user resend,
#   admin_email noreply@getnami.dev. It reports "dry_run": true and "wrote": false.
```

Read 2026-10-18: every value in the table above, and `"wrote":false`.

**Read the DNS records from Cloudflare's nameserver.** A public resolver can keep an earlier "no
record" for up to 30 minutes after a change, because the zone's negative TTL is 1800 seconds. On
2026-10-18, 1.1.1.1 and 8.8.8.8 still answered empty while the nameserver held every record.

```bash
dig +short TXT resend._domainkey.getnami.dev @galilea.ns.cloudflare.com   # DKIM: "p=MIGfMA0…"
dig send.getnami.dev MX @galilea.ns.cloudflare.com +noall +answer          # CNAME send.forge.rmta.net.
dig +short MX send.forge.rmta.net                                          # 10 feedback.forge.rmta.net.
dig +short TXT send.forge.rmta.net                                         # "v=spf1 ip4:… ~all"
dig +short TXT _dmarc.getnami.dev @galilea.ns.cloudflare.com              # "v=DMARC1; p=none;"
```

Read 2026-10-18: all five as shown. Resend showed the domain as verified, as the owner reported.

**Checked 2026-10-18, by the first of the two ways below.** That is #276's outcome check. The
recovery email of § 4c (#203) came from `noreply@getnami.dev`, and Resend's email log lists it, as
the owner reported. So hosted auth email leaves through Resend, not the default provider. The
second way, a sign-up from a mailbox outside the team, was not tried, because the web's sign-up
flow has open defects of its own. Either of these proves the sender:

1. Dashboard → Authentication → Users → an account whose mailbox you hold → **Send password
   recovery**. The email must come from `noreply@getnami.dev`, and Resend's email log must list
   it. The default provider sends from Supabase's own address and never appears in Resend's log.
   Done 2026-10-18 (§ 4c).
2. Sign up on `https://familyroots-web.vercel.app` with a mailbox outside the team, once sign-up
   works. The confirmation email must arrive.

Record the date and what arrived here.

**If no email arrives,** look in Resend's email log first. No row there means Supabase did not hand
it over: read Dashboard → Logs → Auth for an SMTP error, usually a wrong key or a sender outside the
verified domain. A row marked bounced or failed carries Resend's reason.

**To change the domain,** add the new one in Resend, publish its records, wait for **Verified**,
then change the sender in SMTP Settings, send one email, and update the table above. The templates
build links from `{{ .SiteURL }}`, not from the sender, so no push and no new ADR is needed.
**To rotate the key,** create a new one in Resend, paste it into SMTP Settings, send one email, then
delete the old key in Resend.

---

## 5. Traps found while doing this

1. **`supabase storage ls ss:///<bucket>/` cannot tell a missing bucket from an empty one.** A bucket
   name that cannot exist returned the same `{"paths":[]}` as the two real names. Read
   `storage.buckets` with `supabase db query --linked` instead.
2. **An anonymous fetch of a missing object cannot verify a bucket.** Storage's public route looks up
   the bucket and the object in one `Promise.all` (`supabase/storage`
   `src/http/routes/object/getPublicObject.ts:58-63`). For a missing or private bucket, either
   rejection can come back, so the fail reading can equal the pass reading. Fetch an object that
   exists, as in section 2.
3. **`supabase config diff` and `config pull` carry email-template subjects, never bodies.** A body
   changed in the dashboard leaves no trace in either, and the editor keeps no history.
   **Corrected 2026-10-04:** the body *is* readable. The Management API's
   `GET https://api.supabase.com/v1/projects/bftqrkgbulwtbptnpfca/config/auth` returns
   `mailer_templates_confirmation_content` and `mailer_templates_recovery_content` to a personal
   access token with `auth:read`. That is a source reading of the API's OpenAPI schema, under
   ADR-063. #202 built the read-back on it, `scripts/read_back_auth_email_templates.py` (§ 4b). The
   owner ran it against `xkmutzxdhdigyfisfrwd` on 2026-10-18, before and after #203's push (§ 4a).
4. **Never run `supabase config push` from `supabase/config.toml` against this project.** That file
   configures the local stack, and a push writes every property it declares. Its Site URL, redirect
   list and confirmation setting would overwrite the hosted values. **And the CLI version decides
   whether undeclared properties are left alone.** Measured 2026-10-09 (#202, § 4a): CLI 2.120.0
   sends only what the file declares, and says so. CLI 2.115.0, also the TypeScript CLI, ignores
   `--workdir` on `config push`, reads `./supabase/config.toml` from the current directory, and
   sends its default for every property the file does not declare. The older Go CLI always sent
   `site_url` and others too. ADR-063's Context had read the 2.119.0 source and generalised it to
   every TypeScript release; 2.115.0 shows it does not generalise. So to change one hosted
   property, push from a directory whose `supabase/config.toml` declares only that property, with
   the version pinned (`npx --yes supabase@2.120.0`), and answer the prompt only after its list of
   changes shows exactly the change you mean. Template bodies show there only as `[content]`, not
   as text (trap 3). **A push does send a declared body**, read from `content_path`, byte for byte.
   The config that declares only the two templates is `supabase/supabase/config.toml`, pushed with
   `--workdir supabase`.
5. **`NXDOMAIN` on the project host does not mean the project is gone.** Earlier on 2026-10-04 the
   host did not resolve. After the owner opened the dashboard, it resolved, and
   `supabase projects list` reported `ACTIVE_HEALTHY`. Look in the dashboard before concluding
   anything.
