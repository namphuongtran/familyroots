# ADR-073: The Off-Provider Copy of the Nightly Dump Lives in Backblaze B2, EU Central, Encrypted With `age`

## Status

Accepted (2026-10-18), decision only. Resolves issue #284, "Where does the off-provider copy of the
nightly dump live?". The maintainer settled each question in a grilling session the same day.
**#258 implements it.** This pull request changes no script, workflow, secret or bucket.

Repository readings were taken on `main` at `f77be9a`. Vendor pages and Vietnamese legal texts were
read on 2026-10-18 and are cited where they are used.

## Context

Since #252 the nightly dump lands in the `backups` bucket of the same Supabase project it backs up,
`xkmutzxdhdigyfisfrwd` (`docs/ops/backup-restore.md`, "Since 2026-10-10: one project"). Losing the
project, the account or the region takes the database and its backups together. #258's end state
needs a copy that does not share that failure domain.

What the job is today, read at `f77be9a`:

- `.github/workflows/db-backup.yml` runs at 17:15 UTC on GitHub Actions. It holds three secrets,
  among them `SUPABASE_SERVICE_ROLE_KEY`, which the go-live checklist flags as a project-wide admin
  key.
- `scripts/db_backup.sh` runs `pg_dump -Fc | gzip` and uploads with `x-upsert: true`. It rotates by
  deleting through the Storage API (`storage_delete`), keeping the newest 7 daily and 4 weekly.
- `scripts/restore_drill.sh --latest` lists and downloads from Supabase Storage only.
- The first production dump, `db/daily/familyroots-2026-10-11.dump.gz`, is 68,588 bytes.
- **The repository is public.** `gh repo view namphuongtran/familyroots --json visibility` read
  `PUBLIC` on 2026-10-18. Anyone can read the workflow and anything committed beside it.
- **Supabase's Singapore region is an AWS region.** "Supabase will deploy your project to an
  available AWS region within that area", and the Singapore row reads `ap-southeast-1`
  ([Available regions](https://supabase.com/docs/guides/platform/regions)). An S3 bucket in
  `ap-southeast-1` would share the region's failure domain with the database.

## Decision

### 1. The copy goes to Backblaze B2, region EU Central (Amsterdam)

One private bucket, in a B2 account opened for it. That is a different company, a different cloud
and a different continent from Supabase on AWS `ap-southeast-1`.

- **The region is fixed when the account is created.** "After you create your Backblaze B2
  account, you cannot change your selected region", and "Accounts that use the EU Central region
  store data in the Amsterdam data center"
  ([data regions](https://www.backblaze.com/docs/cloud-storage-data-regions)). Choose it at sign-up.
- **Price.** "First 10GB storage is always free", then "$6.95 / TB / mo". Egress: "Free 3x monthly
  egress". "No minimum storage duration fees"
  ([pricing](https://www.backblaze.com/cloud-storage/pricing)). Sign-up: "No credit card required"
  ([sign-up](https://www.backblaze.com/sign-up/s3)). With no card on the account, no backup is lost
  to an expired card.
- **Headroom.** § 4 keeps about 30 daily and 13 weekly dumps, plus superseded versions while they
  are locked. 10 GB holds that until one dump passes roughly 200 MB, about 3,000 times today's size.
- **EU, not US.** § 7's assessment reviews how well a recipient protects the data, and GDPR is the
  regime that is easiest to argue there. That is a reading, not a requirement.

### 2. The Supabase copy stays, so there are two destinations

The same encrypted file (§ 5) goes to both. The Supabase copy restores fastest after an everyday
mistake, such as a bad migration or a wrong delete. The B2 copy is for losing the project or the
account.

- **Supabase keeps its rotation and its credential.** It still holds 7 daily and 4 weekly, and the
  script still deletes there with the service-role key. Removing that key from CI is the go-live
  checklist's open item, not this ADR's.
- **Each upload is attempted whatever happened to the other, and either failure turns the job
  red.** A B2 outage must not cost the night's Supabase copy, and the reverse.

### 3. The upload credential can write, and cannot delete or shorten a lock

A B2 application key restricted to the one bucket.

- **It holds `writeFiles`**, and **`writeFileRetentions`** for § 4's weekly retention. #258 adds
  `listFiles` only if its upload tool needs it.
- **It must not hold** `deleteFiles`, `bypassGovernance`, `readFiles`, `writeBuckets` or
  `writeBucketRetentions`.
- It lives in GitHub Actions repository secrets, beside the existing three. #258 names them.

**A key without `deleteFiles` can still delete indirectly.** `b2_hide_file` needs only `writeFiles`
([b2_hide_file](https://www.backblaze.com/apidocs/b2-hide-file)). A same-name upload hides the
previous version too, and a lifecycle rule then deletes hidden versions. **Object Lock closes
that.** While a file is locked, "lifecycle settings or an integration setting attempting to change
or delete the file will fail", and "There is no extra cost to use Object Lock"
([Object Lock](https://www.backblaze.com/docs/cloud-storage-object-lock)).

**Governance mode, not compliance mode.** In governance mode, retention "can be deleted or the
retention period shortened only by clients with the appropriate application key capability (i.e.,
bypassGovernance)"
([b2_update_file_retention](https://www.backblaze.com/apidocs/b2-update-file-retention)). The
upload key lacks it. `writeFileRetentions` can still **extend** a retention. In compliance mode
retention "cannot [be] removed by any user", so a leaked key could pin junk for years at the
owner's cost. In governance mode the owner's own key can undo that.

**The guarantee:** a leaked upload key cannot remove any dump before its § 4 retention ends. It can
still add objects and hide names.

### 4. B2 keeps daily dumps 30 days and weekly dumps 90, and enforces it itself

The script stops deleting at B2.

- **Object Lock** on the bucket, governance mode, default retention 30 days. Weekly uploads set 90
  days on the file.
- **Lifecycle rules:** `db/daily/` hides after 30 days and `db/weekly/` after 90. Both delete one
  day after hiding.
- **A second run on the same day uploads a new version under the same name.** The older version
  stays locked until its own date, then the lifecycle rule removes it.

The window is longer than Supabase's 7 and 4, so a corruption noticed weeks late still has a clean
dump behind it. The cost is that a person whose account or record is deleted stays in B2's dumps
for up to 90 days.

### 5. The dump is encrypted with `age` before either upload, for two recipients

The dump is piped through `age -R <recipients>` before upload, and the object name gains `.age`.
#258 writes the exact pipeline.

- **Two recipients, each able to decrypt alone.**
  - The maintainer's working identity, kept in their password manager.
  - A recovery identity generated offline, printed on paper, and kept at a physical place the
    maintainer chooses. That place is not written in this repository.
- **The recipients' public keys are committed** to the repository, at a path #258 picks. They are
  not secrets. Changing that file changes who can read every later dump, so it is reviewed like
  code.
- **No identity ever lives** in the repository, in GitHub secrets, in Supabase or in the B2
  account. Those are what the backup has to survive.
- **A third recipient**, such as a co-admin or a successor, is one more line in that file. It covers
  dumps from then on, not earlier ones. It is left for later.
- **Why asymmetric.** CI holds only public keys, so a CI leak reads no dump. A symmetric passphrase
  would have to sit in CI.
- **Why both copies are encrypted.** Every routine drill from Supabase then runs the decryption
  path. If only the B2 copy were encrypted, that path would first run during a disaster.
- **The switch-over.** Unencrypted `.dump.gz` objects already in Supabase age out under the
  existing rotation, within four weeks of the first encrypted run. Until then the restore reads
  both forms.

### 6. A restore names its source, and the B2 read key is minted at recovery time

- `scripts/restore_drill.sh --latest` gains `--from supabase|offsite`, default `supabase`. Both
  sources decrypt with an identity file the operator passes. #258 names the variable.
- **No B2 read key waits anywhere.** At recovery, the maintainer signs in to the B2 web console,
  mints a key with `listFiles` and `readFiles` on the bucket, uses it, and deletes it. The B2
  account login is the root credential and lives in the password manager.
- **What a recovery needs once the maintainer's machine is gone:**
  - one identity, either the password manager's or the paper one;
  - access to one of the two accounts, B2 or Supabase.

  Losing the password manager also loses the B2 login, which leaves the paper identity and whatever
  recovery the B2 account offers through its email address.

### 7. Residency does not constrain the choice

Read on 2026-10-18. This is a reading of the texts, not legal advice.

- **The operator is an individual.** FamilyRoots is the maintainer's personal learning project, not
  a business (the maintainer, 2026-10-18).
- **Law 91/2025/QH15 has no localization rule.** Read at source in the
  [text](https://pbgdpl.cantho.gov.vn/files/files/2025/28.%20Lu%E1%BA%ADt-91-2025-QH15%20B%E1%BA%A2O%20V%E1%BB%86%20D%E1%BB%AE%20LI%E1%BB%86U%20C%C3%81%20NH%C3%82N.docx),
  in effect since 2026-01-01:
  - It applies to "Cơ quan, tổ chức, cá nhân Việt Nam" (Art 1(2)(a)), with no exception for
    personal or household purposes.
  - Art 20(1)(c) counts as a cross-border transfer any use of "nền tảng ở ngoài lãnh thổ … để xử lý
    dữ liệu cá nhân được thu thập tại Việt Nam".
  - Art 20(2) requires a transfer impact assessment, filed within 60 days of the first transfer.
  - Art 20(6) exempts only state agencies, an organisation's cloud copy of its own employees' data,
    and a data subject moving their own data.
- **The primary already crosses that line.** The database is in Singapore. A backup in Amsterdam
  adds one recipient to the same assessment and no new trigger. The law lists no approved countries.
- **The only localization rule found** is Decree 333/2026/NĐ-CP Art 19(2), and it binds "Doanh
  nghiệp trong nước" (domestic enterprises), which the operator is not. Quoted by the 2026-10-18
  research from the
  [Official Gazette](https://congbaocdn.chinhphu.vn/180507251028987904/2026/9/4/470335-1787890927_v1_1788486330_signed.pdf),
  not re-read here.
- **What is owed, and where it is recorded.** If the deployment holds real personal data of people
  other than the maintainer, Art 20's assessment is owed because of the primary, not because of the
  backup. The maintainer chose to record that here rather than open an issue. Revisit if the
  project serves people beyond the maintainer's own use or becomes a business.

## Consequences

- **#258 is unblocked, and its scope is fixed:**
  - the B2 account in EU Central;
  - the bucket, with Object Lock in governance mode and the § 4 lifecycle rules;
  - the upload key and its secrets;
  - both `age` identities and the committed recipients file;
  - encryption and the second upload in `scripts/db_backup.sh`;
  - `--from` and decryption in `scripts/restore_drill.sh`;
  - `docs/ops/backup-restore.md` and `docs/ops/secrets.md`.
- **A second third-party account joins the recovery path.** If B2 suspends or closes it, the
  Supabase copy remains, and the reverse. That is the point.
- **Losing every identity loses every dump made after the switch, in both places.** The paper
  identity exists for that case.
- **A leaked upload key can still cost money and hide names.** It can fill the bucket past the free
  tier, at the owner's cost, and hide every name. The locked versions remain.
- **The document blobs bucket is still not mirrored.** This destination may serve it later.
  Nothing here commits to that.
- **The service-role key stays in CI** for the Supabase copy, as the go-live checklist records.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Cloudflare R2 | A token that can write can also delete: the temporary-credentials page puts "PutObject, DeleteObject, DeleteObjects, CopyObject" in one Write category. Its S3 API implements neither versioning nor object lock. Location hints are "a best effort and not a guarantee", with no Southeast Asia option |
| GitHub Actions artifacts or release assets | No upload-only permission: deleting needs the same Actions or Contents write that uploads. Artifacts expire within 90 days on a public repository. The repository is public, so any signed-in GitHub user can read them. That last point is inferred from "Read access to the repository is required", not tested with an outside account |
| AWS S3, `ap-southeast-1` | The same AWS region as the database |
| AWS S3, another Southeast Asian region | Different region, but the same cloud underneath Supabase. The free plan is credits that end after six months |
| Google Cloud Storage, `asia-southeast1` | The runner-up. `roles/storage.objectCreator` "Does not give permission to view, delete, or overwrite objects", which is the cleanest key of all. But the free tier covers US regions only, a billing account is required, and it sits in the same city as the database |
| Backblaze B2, a US region | Equal in every respect except § 7's recipient review, where the EU is easier to argue |
| One destination, B2 only | It would take the service-role key out of CI. But one copy is lost with one account, and family data has to outlive any single provider |
| Credential that deletes, with the script's rotation kept | A CI leak would then delete production's backups along with anything else it reaches |
| Symmetric encryption with a passphrase | The passphrase would sit in CI, so a CI leak would read every dump |
| No encryption | The dump likely carries `auth.users` (#285) and contact PII (ADR-049), held by a third party under a second account |
| Encrypt the B2 copy only | The decryption path would first run during a disaster |

The R2, GitHub and GCS quotes were read on 2026-10-18 from Cloudflare's R2 docs, GitHub's docs and
Google Cloud's docs by the research behind this ADR.

## Verification

**No gate: documentation only.** The reading is this ADR merged, and #258's body naming Backblaze
B2, EU Central.

**Owed by #258**, each as an outcome rather than a setting (`.claude/rules/testing.md`):

- `restore_drill.sh --latest --from offsite` reads `DRILL: PASS` on a production dump decrypted with
  the paper identity.
- **The upload key is refused when it deletes.** A `b2_delete_file_version` with it fails.
- **The lock holds against a key that may delete.** A key with `deleteFiles` but no
  `bypassGovernance` fails to delete a locked version. The control is the same key deleting an
  unlocked file in a scratch bucket. The two readings must differ.

## Related

- [ADR-066](066-the-application-database-lives-in-the-supabase-project.md): the move that put the
  database and its backups in one project.
- [ADR-052](052-restore-bootstraps-the-request-role.md): the restore bootstrap, which runs after
  either source's dump is restored.
- [ADR-049](049-contact-pii-is-the-whole-field-visibility-rule.md): the contact PII the dump
  carries.
- Issues #258 (implements this), #284 (this decision), #285 (which schemas the dump holds) and #252
  (the move).
