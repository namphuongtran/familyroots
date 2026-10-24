# ADR-077: The Files in the Two Buckets Are Copied to B2 Beside the Dump, One `age` File Each

## Status

Accepted (2026-10-24), decision only. Resolves issue #296, "A recovery from the nightly dump brings
back no file from the two Storage buckets". The maintainer settled each question in a grilling
session the same day. **#303 implements it, and #258 blocks #303.** This pull request changes no
script, workflow, secret or bucket.

Repository readings were taken on `main` at `3869b42`. Production was read on 2026-10-24 with
`supabase db query --linked` (§ Context). Backblaze's docs were read on 2026-10-24 and are cited
where they are used.

## Context

The nightly dump holds `storage.objects` rows, and a row is only metadata. The bytes of every
document and avatar live in Supabase Storage's object store, outside Postgres, so no dump carries
them. ADR-074 § 2 restores no `storage` data, because in a new project those rows would point at
files that do not exist. A recovery into a new project therefore brings back every `documents` row
and no file behind it.

What production held, read 2026-10-24:

| Query | Result |
|---|---|
| `storage.objects`, grouped by `bucket_id` | 2 rows, both in `backups`, 137,176 bytes |
| the same, `family-roots-files` and `family-roots-avatars` | no row |
| `public.documents` | 0 |
| `public.persons` with `avatar_url` set | 0 |
| `public.clans` | 0 |
| `auth.users` | 1 |

Nothing is at risk today. The web upload path is live
(`web/src/components/documents/DocumentUpload.tsx` at `3869b42`), so the first real upload creates
a file no backup holds.

Four readings shape the decision, all at `3869b42`:

- **The two buckets** are declared at `supabase/config.toml:131` (`family-roots-files`, private) and
  `:143` (`family-roots-avatars`, public), and named in `backend/app/core/config.py:84,93`.
- **An avatar outlives its source.** `set_avatar` copies a photo into the public bucket at
  `clans/{clan_id}/avatars/{person_id}` (`backend/app/application/document/handlers.py:54,177`).
  The retention purge deletes from the files bucket only:
  `await storage.delete(row["storage_path"])` (`backend/app/services/document_purge.py:133`). A
  photo deleted and purged leaves its avatar copy in place, so the avatars bucket cannot be rebuilt
  from the files bucket.
- **Every avatar URL names its project.** `_public_object_url` returns
  `f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/" + quote(...)`
  (`backend/app/infrastructure/storage/supabase_adapter.py:111,119`), and `persons.avatar_url`
  stores it (`backend/app/models/person.py:92`). After a restore into a new project, every one
  points at the old project's host. ADR-074 does not mention it.
- **A document's path never changes.** `storage_path` is `unique=True`
  (`backend/app/models/document.py:30`). Staged uploads sit at `clans/{clan}/uploads/{uuid}.{ext}`
  until confirm moves them (`backend/app/application/document/upload.py:8`), and the purge sweeps
  the ones nobody confirmed.

ADR-073 § Consequences left the door open: "The document blobs bucket is still not mirrored. This
destination may serve it later. Nothing here commits to that." This ADR commits to it.

## Decision

### 1. Both buckets are backed up, for disaster only, before the first real clan

- **Both.** `family-roots-files` and `family-roots-avatars`. Avatars are small images, and § Context
  shows they cannot be regenerated.
- **For disaster only:** losing the project, the account or the region. An everyday mistake is
  already covered: ADR-019 soft-deletes a document and keeps its file for `DOCUMENT_RETENTION_DAYS`
  (30, `backend/app/core/config.py:226`) before the purge. So there is no copy in the Supabase
  `backups` bucket. The live buckets are the fast copy.
- **Before the first real clan.** It ships in M3 after #258, the milestone that comes "before real
  data arrives" (`docs/roadmap.md:42`). Real data and its backup arrive together.

### 2. The copy goes into ADR-073's B2 bucket, under `storage/`

Each object lands at `storage/<bucket>/<path>.age`, in the one private bucket of ADR-073 § 1. It
uses the same upload key (§ 3 there), the same Object Lock default, and the same GitHub secrets. No
second bucket and no second key.

### 3. Each object is encrypted with `age` on its own

The object is piped through `age -R <recipients>` before upload, using ADR-073 § 5's committed
recipients file. The same two identities decrypt it.

- **One file per object, not one archive a night.** A 50 MiB video (`supabase/config.toml`'s
  `file_size_limit`) uploaded once is copied once.
- **Avatars are encrypted too**, although they are public, so a restore has one decryption path.
- **What stays readable in B2** is each object's name and size: clan UUIDs, document UUIDs and file
  extensions. No person's name and no title is in a path.

### 4. The copy runs in `db-backup.yml`, straight after the dump

- **Order.** The dump first, then the files. A file leaves its bucket only through the purge, and
  the purge deletes its row in the same transaction. So the dump written moments earlier holds no
  row whose file the copy that follows has not seen.
- **What is copied.** Every object in both buckets that is new since the last copy, or changed since
  the last copy (a replaced avatar upserts the same path). The staging folder `clans/*/uploads/` is
  skipped: a staged file is either confirmed and moved, or swept, and never has a row.
- **Each step is attempted whatever happened to the other, and either failure turns the job red**,
  the same rule as ADR-073 § 2.
- **One switch.** While the workflow stays `disabled_manually` (since 2026-10-11), files go unbacked
  up exactly like the dump.

### 5. A file removed at source stays in B2 for 90 days

When a path disappears from its bucket, the next run hides its name in B2. `b2_hide_file` needs only
`writeFiles` (ADR-073 § 3), so the upload key does it. A replaced avatar's older version becomes
hidden the same way, by the newer upload.

- **A `storage/` lifecycle rule deletes a hidden version 90 days after hiding,** and never hides on
  its own. Object Lock's 30-day default is shorter, so the two do not conflict.
- **90, to match the longest dump B2 keeps** (ADR-073 § 4, weekly). Every dump B2 holds can then be
  restored with every file its rows name.
- **The cost is that a purged photo outlives its purge by up to 90 days.** That is the same cost
  ADR-073 § 4 accepted for rows.
- **A leaked upload key can hide every `storage/` name, and delete none.** Each hidden version stays
  90 days, so the owner can undo it with their own key.

### 6. A restore copies back what the restored rows name, then fixes `avatar_url`

The restored rows are the list of files to bring back:

- every `documents.storage_path`, including soft-deleted rows mid-retention, since ADR-074 restores
  `public` whole and an admin can still restore those;
- every avatar path in `persons.avatar_url`.

For each path, the restore takes the newest version in B2, hidden or not, decrypts it, and uploads it
to the same path in the new project's bucket. ADR-074 § 3's recovery creates those buckets from
`supabase/config.toml`.

- **A file with no row is not copied**, so a restore creates no orphan. A file with no row is one
  uploaded after the dump.
- **A row whose file is missing is reported, and the restore goes on.** In a disaster, a partial
  recovery beats none.
- **Then `avatar_url` is rewritten**: the old project's `SUPABASE_URL` prefix is replaced with the
  new one's, so the path is unchanged. Restoring into the same project is a no-op. This runs before
  traffic opens, in ADR-074 § 3's order.
- **Only a replaced avatar can differ between versions**, and getting the newer portrait back is
  harmless.

### 7. The drill restores the files from B2, with a read key minted for the release

ADR-074's drill into the local Supabase stack also runs § 6.

- **Pass condition.** It passes only when every path on § 6's list decrypts to a file in the local
  bucket whose size equals the row's `file_size_bytes` (where the row records one), and every
  rewritten `avatar_url` answers on the local host. A missing file or a wrong size reads
  `DRILL: FAIL`.
- **The control** removes one restored file from the local bucket before the check, and must read
  `DRILL: FAIL`.
- **An empty list reads `WARN`, not `PASS`.** Production held 0 documents and 0 avatars on
  2026-10-24, and no clan, so there is nothing to read yet. This is the same rule ADR-074 § 5 gives
  check 4 until a real clan exists.
- **The read key.** The files exist only in B2, and ADR-073 § 6 keeps no B2 read key waiting
  anywhere. So at each release the maintainer signs in to the B2 console, mints a key with
  `listFiles` and `readFiles` on the bucket, runs the drill with `--from offsite` for the files, and
  deletes the key. That step joins "Cutting a release" (ADR-074 § 6). It rehearses the B2 sign-in a
  real recovery depends on.

### 8. The job prints the bucket's size, and 8 GB is when a card goes on

ADR-073 § 1 keeps the B2 account card-less, and its 10 GB headroom was sized for dumps alone. Files
fill it far sooner.

- **Each run prints the bucket's total stored bytes**, dumps and files together, in its log.
- **At 8 GB the maintainer adds a card and sets a cap.** That leaves headroom before 10 GB.
- **What a card-less account does past 10 GB is unread.** Backblaze's
  [Data Caps and Alerts](https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts), read
  2026-10-24, says only "If you do not set up data caps, your Backblaze B2 Cloud Storage account
  usage is unlimited, and unlimited charges can accrue". The upload API lists a `cap_exceeded`
  error
  ([upload files with the native API](https://www.backblaze.com/docs/cloud-storage-upload-files-with-the-native-api)).
  #303 reads the actual behaviour first and records it.

## Consequences

- **#303 carries the build**: the copy and the hide in `scripts/db_backup.sh` and
  `db-backup.yml`, the `storage/` lifecycle rule, § 6 in `scripts/restore_drill.sh` and in
  "Restoring for real", § 7's check and its control, § 8's size line, and the release step in
  `docs/ops/deployment.md`. It needs #258's bucket, key, recipients file and two-upload job first.
- **The maintainer sets the `storage/` lifecycle rule.** It changes the bucket, which the upload
  key cannot do (`writeBuckets` is excluded by ADR-073 § 3).
- **Each release gains a B2 console sign-in.** That's a couple of minutes, and it rehearses the
  recovery login.
- **The 10 GB free tier now runs out much sooner than ADR-073 § 1 estimated**, and § 8 makes that
  something you can check rather than a surprise.
- **A deleted person's photos stay in B2 for up to 90 days after the purge**, which is about 120
  days after the soft delete.
- **Object names in B2 reveal how many files each clan holds, and their types.** Their contents do
  not.
- **No freshness alert.** A stopped copy is as silent as a stopped dump. `docs/ops/backup-restore.md`
  "Still deferred" already tracks the dead-man's switch, and it covers both.
- **Orphan-blob reconciliation stays deferred.** The copy backs up an orphan file like any other,
  and § 6 never restores one.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Record that the files are not backed up until the first real clan | M3 already sits before real data, so "later" and "with #258" are the same moment. Deciding now means the destination is picked once |
| Build it now, ahead of #258 | Picks the destination and the encryption twice |
| A second B2 bucket | A second key, a second lock config and more secrets, for files that fit under one prefix |
| A second copy in the Supabase `backups` bucket | Same failure domain as the live buckets. Everyday mistakes are already covered by ADR-019's soft delete |
| One encrypted archive a night | Re-uploads every file every night. A single file can be 50 MiB |
| `rclone sync` from Supabase's S3 endpoint, with `rclone crypt` | A second encryption scheme with its own key to keep beside the `age` identities, and the hosted project's S3 protocol and keys switched on for it |
| The files bucket only, with avatars regenerated on restore | An avatar whose source photo was purged has nothing to regenerate from (`document_purge.py:133`) |
| Delete removed files from B2 within 30 days | A weekly dump older than 30 days would restore rows pointing at files B2 had already deleted |
| Restore every file in B2 | Creates orphan files with no row in the new project |
| A standing B2 read key in the password manager | Amends ADR-073 § 6. A leak would expose only ciphertext, names and sizes, but the console step is short and worth rehearsing |
| Drill files from the live Supabase buckets | The B2 decryption path for files would first run during a disaster, which is the failure ADR-073 § 5 exists to prevent |
| Add a card to the B2 account now | ADR-073 § 1 keeps it card-less so no backup is lost to an expired card. § 8 adds one only when storage needs it |

## Related

- [ADR-019](019-document-soft-delete-purge.md): soft delete and the 30-day purge
- [ADR-036](036-public-avatar-urls.md): the avatar copy and its permanent URL
- [ADR-068](068-documents-upload-straight-to-storage.md): staged uploads
- [ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md): the B2
  bucket, its key, Object Lock and the `age` recipients
- [ADR-074](074-a-restore-takes-public-whole-and-the-data-of-auth.md): what a restore takes, the
  drill, and the release step
- [docs/ops/backup-restore.md](../ops/backup-restore.md)
- Issues #296 (this decision), #258 (the dump's off-provider copy) and #303 (builds this)
