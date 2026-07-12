# Data Safety Design Spec

**Date:** 2026-07-12
**Branches:** PR1 `feat/data-safety` (off `main` @ 3a4bdf2), PR2 `ops/db-backup` (after PR1)
**Purpose:** Close the remaining "không sợ thất lạc" production gates from the
2026-07-12 deep review: a clan has no way to get its data OUT (export = stub, no
GEDCOM/dump — data trapped in the SaaS), documents are HARD-deleted with permanent
blob removal and no recovery window, and there is NO database backup automation and
no tested restore anywhere.

**Owner decisions (2026-07-12):**
- Export v1 = **lossless JSON + GEDCOM 5.5.1** (PDF book deferred).
- Delivery = **synchronous download, data-only**, with a documents *manifest*
  (metadata + short-lived presigned URLs) — no blob zipping, no async job (YAGNI at
  current clan sizes).
- Backup = **GitHub Actions nightly cron → Supabase Storage** (off-provider from the
  Render DB), rotation 7 daily + 4 weekly, plus a restore-drill script executed for
  real once during the PR.

**Build decomposition: 2 PRs.**
1. **PR1 `feat/data-safety` (backend):** export endpoint (JSON + GEDCOM) + document
   deletion safety (soft-delete + retention purge job + restore endpoint) + ADR-019.
2. **PR2 `ops/db-backup` (infra/ops):** backup workflow + restore-drill script +
   `docs/ops/backup-restore.md` rewritten from "target" to actual.

---

## PR1 Item 1 — Clan data export

### Endpoint
`GET /api/v1/exports/clan?format=json|gedcom` — **RequireAdmin**, clan-scoped
(X-Current-Clan-Id), streams the file with
`Content-Disposition: attachment; filename="{clan_slug}-gia-pha-{YYYY-MM-DD}.{json|ged}"`.
Default `format=json`; invalid format → 422 (Pydantic query pattern). This endpoint
returns a FILE, not the API envelope — like `/health`, it is envelope-exempt
(document that in the contract).

### JSON format (the lossless "bản sao ngàn đời")
Versioned envelope:

```jsonc
{
  "format": "familyroots-clan-export",
  "format_version": 1,
  "exported_at": "2026-07-12T10:00:00+07:00",
  "clan": { ...full clan row: name, slug, description, origin_place, founded_year,
            motto, ancestral_hall_location, clan_rules, ... },
  "persons": [ ...every clan member person, ALL business columns: names (full/birth/
      courtesy/posthumous/alias), gender, birth/death date + precision + display,
      lunar strings, places (birth/death/burial/tomb/residence), religion,
      nationality, occupation, education, title_rank, biography, notes, avatar_url,
      version, is_deleted (soft-deleted persons INCLUDED, flagged — heritage data),
      computed "generation" (đời, thủy tổ=1, null when not derivable) ... ],
  "clan_memberships": [ {person_id, role, generation (stored), is_founder, branch_id} ],
  "branches": [ {id, name, description, founder_person_id, parent_branch_id, branch_order} ],
  "marriages": [ ...all clan-owned edges incl. soft-deleted (flagged), spouse_order,
      status, dates + precision/display... ],
  "parent_child": [ ...incl. relationship_type, birth_order, soft-deleted flagged... ],
  "events": [ ...event_type, title, event_date + precision/display, is_lunar_calendar,
      is_recurring, notify_days_before, person_id... ],
  "documents_manifest": [ {id, person_id, title, document_type, description,
      taken_date, taken_place, file_name, mime_type, file_size, storage_path,
      download_url (presigned, ~1h TTL), download_url_expires_at} ]
}
```

Rules: emit raw stored values (no HistoricalDate response nesting — this is an
archival dump, not the REST contract); include soft-deleted persons/edges with their
flags (an archive must not silently drop history); computed đời comes from the same
graph logic the tree uses; phone/email ARE included (admin-only export of the clan's
own data). PII note goes in the contract doc.

### GEDCOM 5.5.1 (`app/services/gedcom_export.py`, pure stdlib)
- `INDI` per person: `NAME` (full_name), `SEX`, `BIRT`/`DEAT` with `DATE` mapped by
  precision — `exact` → `DD MON YYYY`; `year` → `YYYY`; `month` → `MON YYYY`;
  `circa` → `ABT ...`; `unknown` → omit DATE; `PLAC` from birth/death place;
  `BURI`/`PLAC` from burial_place; `OCCU`, `RELI`, `NOTE` for biography.
- Vietnamese concepts with no GEDCOM slot go to structured `NOTE` lines so nothing
  is lost: `NOTE FamilyRoots: ten_huy=...; ten_thuy=...; doi=N; chi=...;
  lunar_birth=...; lunar_death=...; tomb=...`.
- `FAM` per marriage: `HUSB`/`WIFE` (by gender; same-gender or unknown → `HUSB` =
  person1), `MARR`/`DATE`, `DIV` when divorced; `NOTE spouse_order=N; status=...`.
- Children attach via `FAMC` on the child + `CHIL` in the FAM of (father, mother)
  when both parents exist and are married; parent-child edges with no matching FAM
  get a single-parent FAM. `relationship_type != biological` → `ADOP`/pedigree NOTE.
- Soft-deleted persons/edges are EXCLUDED from GEDCOM (it's an interop view, not an
  archive; JSON is the archive).
- Header: `HEAD/GEDC/VERS 5.5.1`, `CHAR UTF-8`, `SOUR FamilyRoots`; footer `TRLR`.
- Cross-references: `@I{n}@` / `@F{n}@` with a stable person-id → xref map.

### Architecture
- `app/application/export/handlers.py` — `ExportQueryHandler.export_clan(clan_id,
  format)` returning `(filename, media_type, content_iterator_or_bytes)`.
- `app/infrastructure/persistence/export_query_port.py` — read-side port gathering
  the raw rows (bare session, dict projections — CQRS read side, mirrors existing
  query ports). Presigned URLs via the existing storage adapter seam.
- `app/services/{clan_export.py,gedcom_export.py}` — pure serializers (dict rows in,
  str/bytes out); JSON via stdlib `json`, GEDCOM via string building. No framework
  imports; unit-testable without DB.
- Route `app/api/v1/exports.py`, wired in `router.py` under `/exports`, RequireAdmin.
- đời computation reuses the tree handlers' existing base-generation logic (call the
  same helper; do not reimplement).

### Testing
- Real-DB integration: seed a "đủ gia vị" clan (thủy tổ + 3 đời, đa thê with
  spouse_order 1/2, one adopted child, circa + year precisions, lunar strings, a
  lunar recurring event, one soft-deleted person, documents with files) →
  - JSON: every section present; the soft-deleted person included with
    `is_deleted: true`; precision/display/lunar fields intact; đời values correct;
    manifest has presigned URL.
  - GEDCOM: output parses structurally (assert INDI/FAM counts, xref integrity —
    every FAMC/CHIL points at an existing record), ABT date for the circa person,
    NOTE carries tên thụy/đời, soft-deleted person ABSENT.
- Isolation two-sided: clan B admin's export contains none of clan A's persons/edges
  (and vice versa). Role: editor/viewer → 403.
- Unit: gedcom serializer edge cases (no-gender marriage, single-parent child,
  unknown dates, special characters escaping/line length ≤ 255 per GEDCOM).

## PR1 Item 2 — Document deletion safety

### Problem (verified 2026-07-12)
`document_repository.delete()` hard-deletes the row and the handler permanently
removes the blob; `Document.mark_deleted()` and the soft-delete columns already
exist but are discarded. A misclick permanently destroys a scanned ancestral
document. The "reclaimable by a sweep" comment in the handler refers to a job that
does not exist.

### Behavior
- `DELETE /documents/{id}` → **soft-delete** (repo issues UPDATE via the existing
  entity `mark_deleted()`; blob untouched). Reads/lists filter `is_deleted = false`.
- New `POST /documents/{id}/restore` — admin, mirrors the persons restore semantics;
  404 if not found/not deleted; restores row (blob was never removed).
- **Retention purge job**: APScheduler daily job (own advisory lock key, same
  pattern as the anniversary job): documents with `is_deleted = true AND deleted_at
  < now() - DOCUMENT_RETENTION_DAYS` → delete blob (storage adapter), then
  hard-delete row; per-item error isolation (one failing blob doesn't stop the
  sweep); blob-missing (already gone) treated as success for the row deletion.
  `DOCUMENT_RETENTION_DAYS` in Settings (default 30) + configuration.md row.
- avatar interplay: soft-deleting a document that is a person's avatar leaves the
  avatar URL working until purge (blob alive) — acceptable v1; note in ADR.
- ADR-019: documents move from hard-delete to soft-delete + retention purge
  (supersedes the documents row of ADR-006's table); orphan-blob reconciliation
  (blobs with no row, from old compensation paths) explicitly deferred — needs
  bucket listing pagination; follow-up ticket.

### Testing
- Real-DB: delete → row flagged + blob still downloadable (presign succeeds); list
  excludes it; restore brings it back; purge job removes blob+row for a document
  aged past retention (inject `deleted_at`), leaves a fresh one; second job run
  idempotent; per-item isolation (poison one storage delete via monkeypatch → other
  purges proceed); advisory lock prevents double-run (mirror scheduler lock test).
- Existing delete tests updated for the new semantics (204/200 shape unchanged).

## PR2 — Automated backup + tested restore

### `.github/workflows/db-backup.yml`
- Triggers: `schedule: cron "15 17 * * *"` (00:15 VN) + `workflow_dispatch`.
- Steps: postgres-client install → `pg_dump --format=custom --no-owner
  "$PROD_DATABASE_URL"` → gzip → upload to Supabase Storage bucket `backups` as
  `db/daily/familyroots-YYYY-MM-DD.dump.gz` via the Storage REST API
  (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` secrets) → rotation: list the
  `db/daily/` prefix, keep newest 7, delete the rest; every Sunday also copy to
  `db/weekly/` and keep newest 4 there. Failure = red workflow run (GitHub default
  notification). Dump size guard: warn in the job log if > 400 MB (Storage limits).
- Secrets required (documented; owner adds at go-live): `PROD_DATABASE_URL`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. The workflow SKIPS with a clear
  notice (neutral exit) when secrets are absent, so forks/CI don't fail.

### `scripts/restore_drill.sh`
- Args: dump file (or `--latest` to fetch newest from the bucket). Restores into a
  scratch database `familyroots_restore_drill` on local pgdb (`docker compose up -d
  pgdb`), runs: `alembic_version` matches current head (warn if behind), row-count
  smoke report (persons, marriages, parent_child, clans, events, documents), one
  recursive tree query executes. Prints PASS/FAIL summary. Idempotent (drops the
  scratch DB first).
- **Executed for real once in the PR** against a dump of the local dev DB (and
  against prod's first dump at go-live); result recorded in the runbook.

### `docs/ops/backup-restore.md` rewrite
From "target runbook / nothing exists" to actual: schedule, storage layout,
rotation, RPO 24h / RTO ~1h (manual restore), drill procedure + drill log table
(date, dump, result), go-live checklist (add the 3 secrets, create the private
`backups` bucket, run workflow_dispatch once, run the drill on that dump), and
what's still deferred (PITR needs a paid DB plan; bucket versioning; blob backups
for Storage itself — documents bucket is on Supabase already, cross-provider copy
is a follow-up).

## Explicitly NOT in this track
PDF gia phả book; async export jobs; zipping blobs into exports; import (JSON →
restore into app) — the JSON schema is designed to make this possible later;
orphan-blob reconciliation; PITR; Supabase-bucket → other-provider blob mirroring;
GEDCOM 7.x.

## Quality gates
Both PRs: full backend gate (`uv run pytest -q && uvx ruff check . && uvx ruff
format --check . && uv run mypy app/ tests/ && uv run lint-imports`); PR2
additionally shellcheck-clean script and a real drill run logged in the runbook.
