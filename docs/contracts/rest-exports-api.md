# Contract: exports-api

## Type
REST API (file download — **envelope-exempt**, see below)

## Owner
backend

## Consumers
- web (clan admin settings)
- mobile (clan admin settings) — lower priority; downloads are naturally a
  desktop-browser workflow but the endpoint is not restricted by client

## Schema
Base route: `/api/v1/exports`

Headers:
- Authorization: Bearer \<jwt\>
- X-Current-Clan-Id: \<uuid\>

Core operation:
- `GET /exports/clan?format=json|gedcom`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `format` | string, pattern `^(json\|gedcom)$` | `json` | Invalid value → 422 (Pydantic query pattern), not a 4xx from the handler |

Role: **RequireAdmin** — this is the only export surface and it returns the
clan's complete dataset (see PII note below), so it is gated one level higher
than the rest of the read API (viewer/editor cannot call it → 403).

### Envelope-EXEMPT
Unlike every other 2xx endpoint in this API (`{"data": ...}` — see
[Response envelope](README.md#response-envelope)), this endpoint's response
body **is the file itself** — raw JSON bytes or raw GEDCOM text, not wrapped
in an envelope. The same exemption `GET /health` already has. Headers:

```
Content-Type: application/json            (format=json)
Content-Type: text/x-gedcom                (format=gedcom)
Content-Disposition: attachment; filename="{clan_slug}-gia-pha-{YYYY-MM-DD}.{json|ged}"
```

`{clan_slug}` is the clan's `slug` column; `{YYYY-MM-DD}` is today's date
(server-local calendar date at request time — informational, not a timezone guarantee) — not `exported_at` from the payload,
though in practice they're the same calendar day.

### PII note
The JSON archive includes **phone and email** (wherever `persons` stores
them) and every other business column, including soft-deleted records. This
is intentional: the caller is a clan **admin** exporting **their own clan's**
data for backup/portability, not a third party. There is no field-level
redaction or opt-out — if this changes (e.g. a future non-admin export
audience), that needs a new ADR, not a silent contract change here.

## JSON format (`format=json`)

Built by the pure serializer `app/services/clan_export.py` (unit-tested in
`tests/unit/test_clan_export_serializer.py`, integration-tested end-to-end in
`tests/integration/test_clan_export_json.py`). Top-level shape:

```jsonc
{
  "format": "familyroots-clan-export",
  "format_version": 1,
  "exported_at": "2026-07-12T10:00:00+00:00",   // UTC, server clock
  "clan": { /* full clans row */ },
  "persons": [
    {
      /* every persons column as raw stored values — full/birth/courtesy/
         posthumous/alias names, gender, birth/death dates + *_precision +
         *_display, lunar_birth_date/lunar_death_date, places, religion,
         nationality, occupation, education, title_rank, biography, notes,
         avatar_url, version, is_deleted, ... */
      "generation": 3   // graph-computed đời (thủy tổ = 1); null if
                        // unreachable from any clan founder
      // NOTE: dates are raw scalar + *_precision/*_display columns here —
      // NOT the REST HistoricalDate {date,precision,display,lunar} object.
      // This is an archival dump, not the API response contract (ADR-011).
    }
  ],
  "clan_memberships": [
    {
      "membership_id": "...", "person_id": "...", "role": "...",
      "stored_generation": 1, "is_founder": true, "branch_id": "...",
      "joined_at": "...", "created_at": "...", "updated_at": "..."
    }
  ],
  "branches": [ /* full branches rows */ ],
  "marriages": [ /* full marriages rows, incl. soft-deleted flagged is_deleted */ ],
  "parent_child": [ /* full parent_child rows, incl. soft-deleted flagged */ ],
  "events": [ /* full events rows */ ],
  "documents_manifest": [
    {
      /* live documents only (is_deleted = false) — full documents row: */
      "id": "...", "clan_id": "...", "person_id": "...", "title": "...",
      "document_type": "...", "description": "...", "taken_date": "...",
      "taken_place": "...", "original_filename": "...", "mime_type": "...",
      "file_size_bytes": 12345, "storage_path": "...", "is_avatar": false,
      "created_by": "...", "created_at": "...", "updated_at": "...",
      "download_url": "https://...",           // presigned, DEFAULT_PRESIGN_TTL (~1h)
      "download_url_expires_at": "2026-07-12T11:00:00+00:00"
    }
  ]
}
```

Rules:
- **Lossless**: `persons`/`marriages`/`parent_child` include soft-deleted rows,
  flagged via their `is_deleted` column — an archive must not silently drop
  history. `documents_manifest` is **live-only** (`is_deleted = false`) since a
  soft-deleted document's presign would point at a blob mid-retention-countdown.
- **`clan_memberships` is split out of the denormalized `persons` JOIN row** —
  membership fields (`role`, `stored_generation`, `is_founder`, `branch_id`,
  `membership_id`, `joined_at`, `created_at`, `updated_at`) never appear on the
  `persons` entries; they live only in `clan_memberships`, keyed by `person_id`.
- **`generation`** on each person is graph-computed via the same base-generation
  logic the tree endpoints use (not `clan_memberships.stored_generation`, which
  is deprecated as a display source — see [ADR-012](../decisions/012-computed-generation-mother-attribution.md)).
  Founder resolution uses the same deterministic `find_clan_founder` ordering
  (`joined_at` ascending, `person_id` tiebreak) as the tree endpoints — see
  [ADR-026](../decisions/026-single-founder-designation.md). Since migration
  `023_one_founder_per_clan`, a clan can have **at most one** live founder
  (`uq_clan_memberships_one_founder` partial unique index), so "multiple
  founders" is no longer reachable against a live/current schema; the ordering
  is retained purely as a tolerance for pre-023 archives or a downgraded
  database, where legacy data could still carry more than one live-flagged
  founder row for a clan.
- **`exported_at`** and `documents_manifest[].download_url_expires_at` are UTC
  ISO-8601 timestamps (`datetime.now(UTC)`), not clan-local time.
- Serialization is `ensure_ascii=False` (Vietnamese diacritics readable raw in
  the file) and `default=str` for UUID/date/datetime values.

### `format_version` stability rule
`format_version` bumps only on a **breaking** change to this archive shape (a
field removed, renamed, or reinterpreted). Additive fields do **not** bump it.
Consumers should branch on `format_version`, not assume the current shape is
permanent. See [ADR-020](../decisions/020-clan-export-formats.md).

## GEDCOM format (`format=gedcom`)

Built by the pure serializer `app/services/gedcom_export.py`, GEDCOM 5.5.1,
pure stdlib. This is the **interop view**: soft-deleted persons, marriages,
and parent-child edges are **excluded entirely** (not flagged — dropped), so
downstream genealogy software never has to reason about `is_deleted`. The
mapping table below mirrors `tests/unit/test_gedcom_export.py` — the file that
pins this behavior; if that suite's assertions change, update this table in
the same PR.

| FamilyRoots concept | GEDCOM output |
|---|---|
| Header | `0 HEAD` / `1 SOUR FamilyRoots` / `1 SUBM @SUB1@` / `1 GEDC` / `2 VERS 5.5.1` / `2 FORM LINEAGE-LINKED` / `1 CHAR UTF-8`, plus a `0 @SUB1@ SUBM` / `1 NAME FamilyRoots Export` submitter record (required by 5.5.1 when HEAD references one) |
| Trailer | `0 TRLR` |
| Person → `INDI` | One `0 @In@ INDI` per **live** person (soft-deleted excluded), xref assigned deterministically by ascending `person.id` string sort — repeated exports of unchanged data are byte-identical |
| `full_name` | `1 NAME <full_name>` |
| `gender` | `1 SEX M\|F\|U` — `male`→M, `female`→F, anything else (`unknown`, unrecognized values) → U |
| `birth_date` / `death_date` + `*_precision` | `1 BIRT`/`1 DEAT` with `2 DATE <value>` when the exact date is present: `exact`→`D MON YYYY`, `month`→`MON YYYY`, `year`→`YYYY`, `circa`→`ABT YYYY`, `unknown`/null precision → tag emitted with no `DATE` line |
| `birth_date`/`death_date` **null** but `*_display` set (approximate-only date) | `1 BIRT`/`1 DEAT` with `2 NOTE <display text>` fallback instead of silently dropping the date — no `DATE` line in this case |
| `birth_name`, `posthumous_name`, đời (generation), branch name, `lunar_birth_date` | One structured `1 NOTE FamilyRoots: ten_huy=...; ten_thuy=...; doi=N; chi=...; lunar_birth=...` line, each key present only when that field has a value (all keys optional, order fixed) |
| `biography` | Its own `1 NOTE <biography>` line (separate from the structured VN-concept note above) |
| Marriage → `FAM` | One `0 @Fn@ FAM` per **live** marriage between two live persons; `HUSB`/`WIFE` assigned by gender (`female`+`male` pair → the male is `HUSB`; any other combination, including same-gender or unknown, → `person1_id` is `HUSB`) |
| `status == "divorced"` | `1 DIV` on that FAM |
| `spouse_order` present | `1 NOTE spouse_order=N; status=<status>` |
| Parent-child edges | Children attach via `1 FAMC @Fn@` on the child; edges are grouped per child and paired up (sorted, deterministic) against an existing marriage FAM when both parents match a married couple, otherwise a synthetic single-parent (or unmarried-couple) FAM is created for the leftover parent(s) |
| `relationship_type != "biological"` (e.g. `adopted`) | `2 PEDI <relationship_type>` under that child's `FAMC` line — no separate `ADOP` tag |
| Spouse back-references | `1 FAMS @Fn@` on each spouse, one line per FAM they belong to |
| Long/multiline text (`NAME`, `NOTE`, `DATE`) | `\r\n`/`\r` normalized to `\n`; each `\n`-delimited segment becomes its own `CONT` line at `level+1`; within a segment, UTF-8 byte length over `_FOLD_BUDGET_BYTES` (200) folds into `CONC` continuations one level below the line being continued (i.e. `level+2` when continuing a `CONT` segment; never splitting a multi-byte character), keeping every physical line ≤ 255 bytes (GEDCOM 5.5.1's hard limit) |
| Literal `@` in any emitted value | Escaped as `@@` (xref pointers like `@I1@` are emitted separately via f-strings and are never escaped) |
| Soft-deleted persons/marriages/parent_child | **Excluded entirely** — not present anywhere in the output |

Not mapped to any GEDCOM tag (no `OCCU`/`RELI`/`PLAC`/`BURI`/tomb emission in
the current serializer): occupation, religion, birth/death/burial place,
tomb location. These remain JSON-archive-only fields; a future pass could add
them to the structured NOTE or standard GEDCOM tags if interop demand
justifies it.

## Versioning & Compatibility Rules
- Non-breaking: adding a new optional field to the JSON archive (does not bump
  `format_version`); adding a new key to the GEDCOM structured NOTE.
- Breaking: removing/renaming/reinterpreting a JSON archive field (bumps
  `format_version`); changing what GEDCOM excludes (e.g. including
  soft-deleted rows) or the tag mapping for an existing field.
- A new export format (e.g. a future PDF book) is additive — a new `format`
  enum value, not a breaking change to `json`/`gedcom`.
- This endpoint's envelope-exempt status is itself a stable contract — do not
  wrap it in `{"data": ...}` without a version bump and an ADR.

## Related
- [ADR-020](../decisions/020-clan-export-formats.md) — why two formats, why
  synchronous/manifest-not-blobs delivery, admin-only rationale.
- [architecture/api-design.md](../architecture/api-design.md) — Exports
  section.
- [rest-documents-api.md](rest-documents-api.md) — the presigned-URL mechanism
  reused for the manifest.
