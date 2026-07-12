# ADR-020: Clan Export Formats — Lossless JSON Archive + GEDCOM Interop

## Status
Accepted (2026-07-12 — shipped).

## Context
Before this PR a clan had no way to get its own data out of the platform — no
dump, no GEDCOM, nothing. Data was trapped in the SaaS: if FamilyRoots
disappeared or a clan wanted to move to another tool, there was no
"bản sao ngàn đời" (thousand-generation copy) they could download. This is one
of the "không sợ thất lạc" (no fear of loss) production gates identified in
the 2026-07-12 deep review.

## Decision

### Two formats, two purposes
`GET /api/v1/exports/clan?format=json|gedcom` (RequireAdmin, clan-scoped)
serves two deliberately different views of the same clan data:

- **JSON (`familyroots-clan-export`, `format_version: 1`)** — the lossless
  archive. Purpose: disaster recovery / platform independence. Includes
  **everything**, including soft-deleted persons/marriages/parent-child edges
  (flagged `is_deleted: true`, never silently dropped — an archive must not
  erase history), all business columns as raw stored values (not the REST
  `HistoricalDate` nesting — this is a dump, not the API contract), and a
  `documents_manifest` (metadata + short-lived presigned `download_url`s, not
  the blobs themselves). `exported_at` is UTC. Built by the pure serializer
  `app/services/clan_export.py`. "Lossless" applies to the **gia phả itself**
  (persons, memberships, edges, branches, events, document metadata) — the
  archive deliberately does NOT contain operational/platform data: audit logs,
  clan settings, invitations, identity claims, change requests, or user/role
  accounts. Soft-deleted documents (mid-retention) are also excluded — their
  blobs are scheduled to disappear, so a manifest URL would be dishonest.
- **GEDCOM 5.5.1** — the interop view. Purpose: import into other genealogy
  software (Gramps, Ancestry, etc.), which speaks GEDCOM, not FamilyRoots JSON.
  Soft-deleted persons/marriages/parent-child edges are **excluded entirely** —
  GEDCOM consumers have no concept of `is_deleted` and shouldn't have to reason
  about it. Vietnamese concepts with no GEDCOM slot (tên húy, tên thụy, đời,
  chi, lunar dates) are preserved in a structured `NOTE` line rather than lost.
  Built by the pure serializer `app/services/gedcom_export.py`.

### Delivery: synchronous, data-only, manifest not blobs
Both formats are generated and streamed back synchronously in the request —
no async job, no zip of blob contents. At current clan sizes, generating a
JSON dump or a GEDCOM document is fast enough that a background job would be
unverified complexity (YAGNI). Documents are represented in the JSON archive
as a **manifest** (metadata plus a presigned, time-limited `download_url` per
document) rather than the platform zipping every blob into the export —
keeping the archive request cheap and avoiding a second point where storage
failures could break the export.

### Admin-only, sync-only download
The endpoint is `RequireAdmin` — exporting the clan's complete dataset,
including phone/email and soft-deleted records, is a higher-privilege action
than any other read in the API. There is no scheduled/background export; a
clan admin downloads on demand.

### Envelope-exempt
Unlike every other 2xx endpoint (`{"data": ...}`), this endpoint returns the
raw archive as the response body — a file attachment via
`Content-Disposition: attachment; filename="{slug}-gia-pha-{date}.{ext}"` — the
same exemption pattern as `GET /health`.

### GEDCOM mapping is a distinct code path, not JSON-then-convert
`gedcom_export.py` consumes the same `ExportQueryPort` row dicts as
`clan_export.py`, but is its own serializer rather than a transform over the
JSON payload — the two formats have genuinely different inclusion rules
(soft-deleted in/out) and different shapes (denormalized dict archive vs.
GEDCOM's `INDI`/`FAM` record structure), so sharing one code path would mean
constantly branching on format inside a single function. See
[rest-exports-api.md](../contracts/rest-exports-api.md) for the full field/tag
mapping table.

### `format_version` stability rule
`format_version` on the JSON archive bumps only on a **breaking** change to
the archive shape (a field removed, renamed, or reinterpreted) — additive
fields do not bump it. A consumer parsing the archive should branch on
`format_version`, not assume today's shape is permanent.

### Explicitly out of scope (owner decision, 2026-07-12)
- **PDF gia phả book** — deferred; JSON + GEDCOM close the "data trapped"
  gap without needing a rendering pipeline.
- **Import (JSON → restore into the app)** — not built in this PR, but the
  JSON schema is **deliberately designed to make this possible later**
  (stable ids, full lossless field set, explicit soft-delete flags) — it is
  out of scope, not architecturally precluded.
- **Async export jobs / blob zipping** — see "Delivery" above; revisit only if
  clan sizes or document counts grow enough to make synchronous generation
  slow.

## Consequences
Easier: a clan can now get a complete, lossless copy of its own data (JSON) or
hand a GEDCOM file to any standard genealogy tool. The two formats have a
clear separation of concerns — archive vs. interop — so neither format's
constraints (GEDCOM's line-length/tag limits; the archive's need to preserve
soft-deleted rows) compromise the other.

Harder: two serializers to keep in sync with schema changes — adding a new
person/marriage/event column normally means updating both `clan_export.py`
(automatic, since it dumps raw rows) and potentially `gedcom_export.py` (if
the field deserves a GEDCOM tag or NOTE entry; GEDCOM does not automatically
gain new fields the way the JSON archive does). PII (phone/email) is included
in the JSON archive on the premise that this is an admin exporting their own
clan's own data — documented explicitly in
[rest-exports-api.md](../contracts/rest-exports-api.md) rather than assumed.
Import-from-JSON is unbuilt, so today the export is one-way — a clan can leave
with its data, but cannot yet self-serve a restore into a fresh FamilyRoots
clan from that same file.

## Related
- [rest-exports-api.md](../contracts/rest-exports-api.md) — endpoint contract,
  JSON schema, GEDCOM mapping table, PII note.
- [architecture/api-design.md](../architecture/api-design.md) — Exports
  section.
- [ADR-011](011-historical-date-precision.md) — why the JSON archive
  deliberately does *not* use the `HistoricalDate` response shape (it stores
  raw precision/display columns instead).
