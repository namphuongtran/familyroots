# The hosted Supabase project

The hosted Supabase project serves **auth and storage only**. The application database is Render's
`familyroots-db` (`infra/render/render.yaml:17-20`), not this project. This file records how the
project was set up, what it held when it was read, and how to check it again. The local stack is a
separate thing, covered in [local-supabase.md](local-supabase.md).

Everything below was read or done on **2026-10-04**, with Supabase CLI 2.119.0, under issue #163.
Re-run a command before trusting its reading.

| | |
|---|---|
| Name | Family Roots Project |
| Ref | `bftqrkgbulwtbptnpfca` (`https://bftqrkgbulwtbptnpfca.supabase.co`) |
| Region | `ap-northeast-1` |
| Postgres | 17 |
| `public` schema | 0 tables, counted from `pg_class`. Expected, because the app tables live on Render |
| Pointed at by | `web/.env.local`, plus the backend's `SUPABASE_URL` (values in [secrets.md](secrets.md)) |

---

## 1. Connect the CLI

```bash
supabase login                                        # once per machine; the token goes to the OS keychain
supabase link --project-ref bftqrkgbulwtbptnpfca      # writes supabase/.temp/, which supabase/.gitignore ignores
supabase projects list                                # must show the project as ACTIVE_HEALTHY
```

`supabase db query --linked "<sql>"` runs SQL through the Management API with a temporary login
role. It needs no database password. It is the reliable way to read `storage.*` and `auth.*` state.

---

## 2. Buckets: done 2026-10-04

The backend needs two buckets, declared in `supabase/config.toml` `[storage.buckets.*]`. That is the
same declaration the local stack uses.

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
#   expect family-roots-files   | null   (unchanged; that bucket has no list)

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

## 3. Auth settings: read 2026-10-04

Read with `supabase config diff --project-ref bftqrkgbulwtbptnpfca`, which changes nothing. The
"local" column is `supabase/config.toml`, the **local stack's** file.

| Setting | Hosted | Local file |
|---|---|---|
| Site URL | `http://localhost:3000` | `http://127.0.0.1:3000` |
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
  `http://localhost:3000/api/auth/callback`, and the email links, which fall back to the Site URL
  while `EMAIL_VERIFY_REDIRECT_URL` and `PASSWORD_RESET_REDIRECT_URL` are empty.
- **A deployed web origin or a mobile deep link does not work yet.** Every redirect to one falls back
  to `http://localhost:3000`. Add the origin under Redirect URLs, and change the Site URL, when the
  web app is first deployed.

---

## 4. Email templates

Both the **Confirm signup** and **Reset Password** templates must link `{{ .ConfirmationURL }}`
until #203 pushes the repository's templates. [ADR-063](../decisions/063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md)
decided on 2026-10-04 that both will link a `token_hash` page of ours. Pushing that earlier would
leave sign-ups unconfirmable, because the pages (#200, #201) do not exist yet. Until then, these
are the Supabase default bodies:

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

Where they live: Dashboard → Authentication → Emails → Templates
(`https://supabase.com/dashboard/project/bftqrkgbulwtbptnpfca/auth/templates`). What each shape
lands as on the client, and why `?code=` never happens, is in
[frontend-integration-guide.md § 3.1](../contracts/frontend-integration-guide.md).

**How to check the templates by outcome.** No command in this repository can read a template
body (see trap 3). So read the email itself:

1. Dashboard → Authentication → Users → an account whose mailbox you own → **Send password
   recovery**.
2. In the email, copy the link **without opening it**. It must begin with
   `https://bftqrkgbulwtbptnpfca.supabase.co/auth/v1/verify?token=` and carry `type=recovery` and
   `redirect_to=http://localhost:3000`.
3. A link that does anything else (`...`, a missing token, another host) is a broken template.

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
   ADR-063, and it has not yet been run against this project. #202 builds the read-back on it.
4. **Never run `supabase config push` from `supabase/config.toml` against this project.** That file
   configures the local stack, and a push writes every property it declares. Its Site URL, redirect
   list and confirmation setting would overwrite the hosted values. To change one hosted property,
   push from a throwaway directory whose `supabase/config.toml` declares only that property, after
   `supabase config diff --workdir <dir>` shows exactly the change you mean. Undeclared properties are
   left alone. Template bodies cannot be previewed this way (trap 3). **A push does send a declared
   body**, read from `content_path`. Both facts were read at the source of CLI 2.119.0, which is
   TypeScript (ADR-063, Context). The older Go CLI always sent `site_url` and others, so check
   `supabase --version` before relying on either. #202 checks in a config that declares only the two
   templates.
5. **`NXDOMAIN` on the project host does not mean the project is gone.** Earlier on 2026-10-04 the
   host did not resolve. After the owner opened the dashboard, it resolved, and
   `supabase projects list` reported `ACTIVE_HEALTHY`. Look in the dashboard before concluding
   anything.
