# ADR-036: `persons.avatar_url` Is a Permanent Public URL, Written Only by set-avatar

## Status
Accepted — 2026-08-02

## Context

`persons.avatar_url` is a `varchar(500)` that has existed since the initial schema
(migration `001_initial`). It is echoed on every person, tree, search and event
response. Until now:

- **No backend code ever wrote it.** Nothing populated it from the avatar flow, from
  upload, or from anywhere else.
- **Clients could write anything into it.** It was an ordinary field on
  `PersonCreateRequest` / `PersonUpdateRequest` and in the Person aggregate's
  updatable-field whitelist.
- **`PATCH /documents/{id}/set-avatar` computed a 30-day presigned URL and discarded
  it** — the route returned only `{message, document_id}`, so the URL never reached
  a client and never reached the column.

`docs/contracts/frontend-integration-guide.md` §8 recorded the resulting state
honestly as "⚠️ UNDEFINED — needs backend decision", and warned that a client writing
a presigned URL into the column would watch it silently expire.

Every blob in the system is private today: one bucket (`family-roots-files`), path
isolation by clan prefix, reads through short-lived presigned URLs (`DEFAULT_PRESIGN_TTL
= 3600`). See [storage.md](../architecture/storage.md).

Three options were on the table:

1. **Resolve avatars through the avatar document.** Keep everything private; clients
   call `GET /documents/{id}` for a fresh presign whenever they need to render a face.
   Leaks nothing, but every list of members becomes N presign round-trips, avatars
   cannot be cached or CDN-served, and offline mobile caches expire hourly.
2. **Store a presigned URL in the column.** Cheapest change, and the worst outcome:
   the column silently rots on a schedule with nothing watching it, which is precisely
   the failure the "UNDEFINED" warning was about.
3. **Store a permanent, publicly fetchable URL** into a dedicated public bucket the
   backend writes.

## Decision

**`persons.avatar_url` holds a permanent, publicly fetchable image URL.** The owner
chose this knowing the privacy cost, which is recorded under Consequences below.

The decision is deliberately scoped so that "permanent public URL" cannot become
"arbitrary URL":

### 1. `PATCH /documents/{id}/set-avatar` is the only writer

The use case (`DocumentCommandHandler.set_avatar`) now:

1. loads the document clan-scoped, validates it is a `photo` linked to a person;
2. asserts the document's `clan_id` **and** its storage key prefix match the acting
   clan — a belt-and-braces backstop before anything becomes world-readable
   (`document.avatar_source_outside_clan`, 422);
3. loads the person clan-scoped (a person outside the acting clan is a 404);
4. releases the pooled DB connection (ADR-028) and copies the image into the public
   avatars bucket at **`clans/{clan_id}/avatars/{person_id}`**;
5. stamps the resulting URL on the person via `Person.set_avatar_url`, clears the
   previous avatar documents, and commits — one transaction, two audit rows
   (`document.set_avatar` and `person.update`).

The object path is **clan-prefixed** (the storage tenancy boundary is identical in the
public bucket and the private one), **stable per person**, and **extension-less**:
replacing an avatar upserts the same object, so the stored URL never changes and no
orphan copies accumulate. The format is carried by the stored `Content-Type`.

The route response gains `avatar_url` (additive, non-breaking).

### 2. Clients cannot write `avatar_url`

Rejected with **422**, not silently ignored:

- `PersonCreateRequest` / `PersonUpdateRequest` declare the field with a validator that
  always raises, so a request that sends it gets a `validation_error` naming
  `body.avatar_url`, plus an OpenAPI description pointing at set-avatar. The field is
  `exclude=True`, so it never reaches `model_dump()` and cannot ride into a command DTO.
- Backstops: `avatar_url` is out of the Person aggregate's `_UPDATABLE_FIELDS` (so
  `update()` raises `field_not_updatable`), out of the viewer self-edit whitelist, and
  out of the `CreatePerson` command entirely; `Person.create` rejects it too.

Rejection rather than the "silently drop it" precedent set by `created_by_clan_id`: a
silent drop is exactly what produced the undefined state — a client believes it set an
avatar and nothing did. An accepted arbitrary URL would also turn the field into an
SSRF vector (the backend or another client fetching an attacker-chosen host), a
tracking-pixel vector, and a moderation surface, none of which "permanent public URL"
implies. This **is** a breaking change for any client that was writing the field; see
[rest-persons-api.md](../contracts/rest-persons-api.md).

### 3. A presigned URL can never be stored

`Person.set_avatar_url` accepts only an absolute `http(s)` URL, at most 500 characters,
**with no query string and no fragment**. Every presigned URL carries its signature and
expiry in the query string, so that single structural rule excludes the whole class
(`person.avatar_url_not_permanent`, 422). The rule is expressed in terms of URL shape,
not any provider's URL format, so the domain stays vendor-agnostic.

### 4. A missing or private bucket fails closed

The public bucket is a Supabase dashboard action; this code cannot create it. It is
configured by `SUPABASE_AVATAR_BUCKET`, and before copying anything the adapter checks
that the bucket exists **and** is public-read. A missing, unreachable, private or
unconfigured bucket raises `StorageBucketNotConfiguredError` → **503
`storage_bucket_not_configured`**, its own code so an operator can tell it apart from a
transient outage. Nothing is written: no `is_avatar` flag, no URL. Uploading into a
private bucket would "succeed" and leave a person pointing at a URL that 400s forever,
which is the failure mode this check exists to prevent.

This also changes the ordering guarantee: set-avatar used to be a pure-DB write that
tolerated a storage outage by returning `presigned_url: null`. It cannot be any more —
it publishes a blob, so a storage failure is now a truthful 503 and the avatar is
simply not set. `is_avatar = true` with no reachable object is a half-applied state
with a permanently wrong URL attached to a person.

### Operator action required before this works in an environment

Nothing about the avatar path functions until the bucket exists. Create in the Supabase
dashboard (Storage → New bucket):

| Setting | Value | Why |
|---|---|---|
| Name | `family-roots-avatars` | Must match `SUPABASE_AVATAR_BUCKET`. **Must not be** `family-roots-files` — that bucket stays private. |
| Public bucket | **on** (public read) | The whole point; the adapter refuses to publish if this is off. |
| Allowed MIME types | `image/jpeg, image/png, image/webp, image/heic` | Only photos are ever published here. |
| File size limit | ≥ `MAX_UPLOAD_SIZE_MB` (default 50 MB) | Avatars are copies of documents already accepted at that limit. |

- **Cache-Control** is set per object by the backend to
  `max-age=AVATAR_CACHE_CONTROL_SECONDS` (default 300). Because the object path is
  stable per person, a replaced avatar keeps its URL, so this window is how long a
  stale portrait can still be served. Raise it for cacheability, lower it for freshness.
- **CORS**: none is required for `<img src>` rendering, which is what clients do. Add
  an allow-list of the web/mobile origins only if a client starts fetching avatar bytes
  via `fetch`/XHR (e.g. to canvas-crop them).
- Write access is the service-role key only, which the backend already holds; no
  anonymous write policy should be added.

## Consequences

### The privacy trade-off, stated plainly

**Member photographs become retrievable by anyone holding the URL, without
authentication, regardless of clan.** A public bucket has no viewer, no role, and no
tenant. Concretely:

- Anyone with the link — a forwarded message, a browser history, a referrer header, a
  shared screenshot — can fetch a clan member's portrait. There is no login wall.
- Clan isolation stops at the database and the object path. It governs **who can cause
  a photo to be published** and **where it lands**, not who can read it afterwards.
  Once published, a clan A avatar is as readable by clan B, and by a stranger, as by
  clan A.
- The URL is guessable to anyone who learns a clan id and a person id, both of which
  appear in ordinary API responses to any member of that clan. A member of clan A who
  later leaves keeps the ability to fetch the avatars they saw.
- **Deleting the document does not revoke the URL.** `DELETE /documents/{id}` is a soft
  delete (ADR-019) and the retention purge removes only the *private* blob; the
  published public object is not currently deleted by any code path. Until that gap is
  closed, the honest statement is that publishing an avatar is effectively
  irreversible from the application. See "Known gaps" below.

The owner accepted this. It is recorded here rather than quietly forgotten, and it is
the thing to re-read before extending the same pattern to any other image.

### Other consequences

- Avatars render from a plain `<img src>`, are CDN- and browser-cacheable, and survive
  offline in mobile caches. No presign round-trip per face in a member list.
- One extra storage round-trip per set-avatar (bucket check + download + upload).
  set-avatar is rare; document reads are unchanged.
- A person who belongs to two clans has **one** `avatar_url`, because the column is on
  the clan-independent `persons` row. Either clan's editors may replace it — the same
  authority they already hold over every other field of a shared person — and the
  published object then sits under whichever clan set it. This is existing shared-person
  semantics, not a new isolation hole, but it is worth knowing.
- Storage cost grows by one duplicated image per person with an avatar. Bounded and small.

### Known gaps (deliberately not closed here)

1. **No unpublish.** Soft-deleting or purging the avatar document, or soft-deleting the
   person, leaves the public object and the stored URL in place. Closing this needs a
   delete of the public object plus nulling `avatar_url`, wired into the document
   delete/purge and person delete paths. Tracked as a follow-up; called out in
   [storage.md](../architecture/storage.md).
2. **Orphan reconciliation** in the public bucket has the same shape as the existing,
   still-deferred private-bucket gap (ADR-019).
3. **No moderation.** Any photo an editor can upload can be published. The existing MIME
   and size checks are the only filter.

## Related

- [ADR-019](019-document-soft-delete-purge.md) — soft delete + retention purge; the
  lifecycle the "no unpublish" gap sits inside
- [ADR-008](008-rls-defense-in-depth.md) / [ADR-002](002-clan-scoped-multitenancy.md) —
  the isolation layers that govern publishing but not reading
- [ADR-028](028-no-external-io-holding-db-connection.md) — why the blob copy releases
  the pooled connection first
- [storage.md](../architecture/storage.md) — bucket layout and the operator checklist
- [rest-documents-api.md](../contracts/rest-documents-api.md),
  [rest-persons-api.md](../contracts/rest-persons-api.md),
  [frontend-integration-guide.md §8](../contracts/frontend-integration-guide.md)
