# Contract: error-codes

## Type
REST error contract (machine-readable error-code catalog)

## Owner
backend

## Consumers
- web
- mobile

## How to consume

Every non-2xx JSON response from `/api/v1` uses one stable envelope:

```json
{ "error": { "code": "person_not_found", "message": "...", "detail": { } } }
```

- **`code`** is the contract. It is a stable, machine-readable string — branch UI
  logic on it, never on `message`.
- **`message`** is a human-readable string localized server-side from the request's
  `Accept-Language` header (locales: `vi` default/fallback, `en`, `fr`, `zh`). It may
  change wording at any time; never parse it.
- **`detail`** is a code-specific object (often `{}`). Its keys per code are listed
  in the tables below.

Sources of truth in the backend: `backend/app/core/exceptions.py` (envelope, handlers,
domain→HTTP status mapping), `backend/app/core/rate_limit.py` (429), and
`backend/app/i18n/*.json` (`error.<code>` message keys).

## 401 vs 403 — client decision matrix

**401 (any code)** means the credential itself is invalid or absent
(`missing_token`, `invalid_token`, `auth.invalid_credentials`,
`auth.invalid_refresh_token`, `unauthorized`). Client behavior: attempt a token
refresh once; if refresh also fails, sign the user out.

**403** means the credential is valid but policy denies the action — do **not**
refresh or sign out. Route on the code:

| 403 code | Suggested UX |
|---|---|
| `email_not_verified` | Show resend-verification screen (`POST /auth/resend-verification`) |
| `account_deactivated` | Show blocked-account screen; sign-out only on user action |
| `clan_suspended` | Show clan-blocked screen; offer clan switcher if user has other clans |
| `clan_membership_required` | Send to clan-select / membership-pending flow |
| `no_approved_clan_membership` | Send to onboarding (join or create a clan) / approval-pending screen |
| `insufficient_permissions`, other policy codes | Hide/disable the action; show a permission notice |

## Code catalog

Grouped by family. "HTTP" is the status the backend actually emits.

### Auth & session

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `missing_token` | 401 | No `Authorization: Bearer` header on a protected route | — | Refresh/re-login |
| `invalid_token` | 401 | JWT fails JWKS validation (signature, expiry, audience, issuer) | — | Refresh once, then sign out |
| `auth.invalid_credentials` | 401 | Login rejected by identity provider (wrong email/password) | — | Show invalid-credentials message |
| `auth.invalid_refresh_token` | 401 | Refresh token invalid, expired, or revoked | — | Sign out |
| `email_not_verified` | 403 | Login with a valid but unverified email | — | Resend-verification screen |
| `account_deactivated` | 403 | User profile `is_active = false` (checked on every authenticated request — `get_current_user` chokepoint — and at login) | — | Blocked-account screen |
| `auth_provider_unavailable` | 503 | Identity provider outage/misconfiguration (DNS failure, provider 5xx, rejected API key) on any auth path | — | Retry later banner; not a credentials error |

### Registration & onboarding

`POST /auth/register` is **non-enumerating** (ADR-021): there is no code, status,
or response-body difference between "email already has an account" and "new
email" — both return the same 201 `{"data": {"message": "..."}}` (see
[rest-auth-api.md](rest-auth-api.md)). `auth.email_already_exists` no longer
exists — the single raise site, the error-code row, and its 4 i18n entries
were all removed. There is no error row for the register success message
(`auth.registration_received`) either — it's a 201 message key, not an error
code. The clan-input codes below (`auth.clan_id_required_for_join`,
`auth.clan_name_required_for_create`, `auth.clan_slug_taken`, plus
`clan_not_found`) still fire on register and are unchanged: they run
unconditionally before the identity is created, so they return identically
regardless of whether the email exists, and they aren't account-existence
oracles (clan slug/id existence is public data, not a signal about a user's
account).

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `auth.password_too_weak` | 422 | Identity provider rejected the password strength | `detail` (provider text) | Inline field error |
| `auth.registration_failed` | 422 | Identity provider rejected registration for another validation reason | `detail` (provider text) | Inline form error |
| `auth.clan_id_required_for_join` | 422 | Register or onboard with `clan_action=join` but no `clan_id` | — | Form validation |
| `auth.clan_name_required_for_create` | 422 | Register or onboard with `clan_action=create` but missing `clan_name`/`clan_slug` | — | Form validation |
| `auth.clan_slug_taken` | 409 | Creating a clan (register or onboard) whose slug already exists — from the `get_clan_by_slug` pre-check, and (on a concurrent create that both pass the pre-check) from the `uq_clans_slug` `23505` race, mapped by index name to this same code rather than the generic `conflict` | — | Ask for another slug |
| `auth.already_joined_clan` | 409 | Join request for a clan the user is already an approved member of | — | Route into the clan |
| `auth.membership_already_pending` | 409 | Join request while a pending membership request already exists | — | Show approval-pending screen |

### Clan context & permissions (any clan-scoped endpoint)

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `invalid_clan_id_format` | 400 | `X-Current-Clan-Id` header is not a valid UUID | — | Fix client bug |
| `multiple_clans_no_selection` | 400 | User belongs to >1 clan and sent no `X-Current-Clan-Id` header | — | Show clan switcher, resend with header |
| `clan_membership_required` | 403 | Header clan is not among the user's approved clans; also `POST /me/select-clan` for a clan the user isn't in | `clan_id` (select-clan only) | Clan-select / pending flow |
| `no_approved_clan_membership` | 403 | User has zero approved clan memberships | — | Onboarding / approval-pending |
| `clan_suspended` | 403 | The active clan has been deactivated by the platform | — | Clan-blocked screen |
| `insufficient_permissions` | 403 | Role below the endpoint's required role; also a viewer editing a person that is not their own linked person | — | Hide/disable action |
| `invalid_role_assignment` | 403 | User's stored role value is not a known `ClanRole` (data corruption guard) | — | Contact-admin notice |
| `super_admin_required` | 403 | Platform-admin endpoint hit by a non-super-admin | — | Hide admin area |
| `clan_context_mismatch` | 403 | Claims/invitations route: `clan_id` in the path differs from the `X-Current-Clan-Id` context | — | Re-sync active clan, retry |

### Clans & member administration

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `clan_not_found` | 404 | Clan id does not exist (clan detail, join, platform admin ops) | — | Not-found state |
| `user_not_found` | 404 | Target member/user does not exist in this clan (approve, change role, remove, claims) | — | Refresh member list |
| `user.already_approved` | 409 | Approving a membership that is already approved | — | Refresh list |
| `clan.role_changed_concurrently` | 409 | `PATCH /clans/me/users/{user_id}/role` lost a compare-and-set: the member's role was changed by another admin between this request's read and its write (the row still exists — a concurrent removal instead yields `user_not_found`) | — | Re-fetch the member and retry |
| `invalid_role` | 422 | Role change to a value outside admin/editor/viewer | `allowed` (list) | Fix client bug |
| `clan.last_admin_cannot_demote` | 403 | Demoting the clan's only approved admin (any target, not just self — enforced under a `FOR UPDATE` lock on the clan's admin rows so concurrent demotions can't both pass, ADR-017 sibling fix) | — | Explain: promote another admin first |
| `clan.last_admin_cannot_remove` | 403 | Removing the clan's only approved admin from the clan (same `FOR UPDATE` guard as `last_admin_cannot_demote`, applied to `DELETE /clans/me/users/{user_id}`) | — | Explain: promote another admin first, or transfer admin before removing |
| `clan.cannot_remove_self` | 403 | Admin tries to remove their own membership | — | Explain: use leave/transfer flow |

### Optimistic concurrency (persons, marriages, parent-child) — ADR-017

`version` is returned on every `PersonResponse`/`MarriageResponse`/`ParentChildResponse`
and `expected_version` is a **required** field on the matching PATCH request body
(missing it is a plain 422 Pydantic validation error, not a code below).

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `stale_write` | 409 | `PATCH /persons/{id}`, `PATCH /relationships/marriages/{id}`, or `PATCH /relationships/parent-child/{id}` sent an `expected_version` that no longer matches the row's current `version` (someone else updated, deleted, or restored it first). Also reachable on `POST /change-requests/{id}/approve` when a concurrent writer commits between the merge check and the write — a genuine race, not the week-old-proposal case, which is `change_request.target_conflict` | `current_version` (int — the row's actual current version) | Re-fetch the record (or read `current_version` directly), re-apply the user's edit on top of the fresh data, resubmit with the new `version` |

Change requests carry an **age-tolerant** variant of the same protection: a proposal
records the target's `version` *and* its per-field values at submission, and approval
runs a three-way merge instead of a bare version equality check — so a week-old
correction to `birth_date` still applies after somebody rewrote `biography`, while a
competing edit to `birth_date` itself is refused with `change_request.target_conflict`
(ADR-037).

### Invitations

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `invitation.pending_exists` | 409 | Inviting an email that already has a **live** (non-expired) pending invitation in this clan (a timed-out one is lazily expired and re-invite succeeds — M11). Two fresh concurrent invites that both pass the pre-check and race to insert now also surface this code — the loser's `uq_clan_invitations_pending` `23505` is mapped by index name, not the generic `conflict` | — | Show existing invitation |
| `invitation.not_found` | 404 | Invitation id/token does not exist | — | Invalid-invitation screen |
| `invitation.not_pending` | 409 | Accept/revoke on an invitation already accepted, revoked, or expired-marked | — | Refresh state |
| `invitation.expired` | 409 | Accepting an invitation past its expiry | — | Ask inviter to re-send |
| `invitation.already_member` | 409 | Accepting an invitation to a clan the user already belongs to | — | Route into the clan |
| `invitation.email_mismatch` | 403 | Accepting an invitation addressed to a different email | — | Explain: sign in with invited email |

### Claims (linking a user account to a person)

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `claim_not_found` | 404 | Claim id does not exist (review, cancel) | — | Refresh claims list |
| `claim.not_owned` | 403 | Cancelling a claim owned by another user | — | Hide action |
| `claim.not_pending` | 409 | Approve/reject/cancel on a claim no longer pending | — | Refresh state |
| `user_already_has_pending_claim` | 409 | Creating a claim while another of the user's claims is pending | — | Show pending claim |
| `user_already_linked_to_person` | 409 | Claiming (or admin-linking) when the user is already linked to a person | — | Show current link |
| `person_already_linked_to_user` | 409 | Claiming a person already linked to another user | — | Explain conflict |
| `user_already_linked` | 409 | Approving a claim whose user got linked in the meantime | — | Refresh state |
| `person_already_linked` | 409 | Approving a claim / admin-linking when the person got linked in the meantime | — | Refresh state |
| `user_not_linked_to_person` | 404 | Unlinking a user who has no linked person | — | Refresh state |
| `user_not_in_clan` | 403 | Admin-linking a user who is not a member of the acting clan | — | Explain: invite user first |
| `person_not_controlled_by_this_clan` | 403 | Unlink/admin-link on a person another clan controls | — | Explain cross-clan restriction |
| `person_has_no_controlling_clan` | 403 | Reviewing a claim for a person with no controlling clan | — | Contact-support notice |
| `only_clan_admin_can_review_claims` | 403 | Non-admin of the controlling clan reviews a claim | — | Hide action |

### Change requests (propose-and-review corrections) — ADR-037

Scope today is `action=update` on `resource_type=person`. See
[rest-change-requests-api.md](rest-change-requests-api.md).

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `change_request_not_found` | 404 | Change-request id does not exist, belongs to another clan, or a `viewer` asked for a proposal they did not submit (viewers are scoped to their own; the 404 rather than 403 keeps the queue non-enumerating, ADR-021) | — | Refresh the queue |
| `change_request.not_pending` | 409 | Approve/reject on a proposal already approved or rejected. Checked **before** any target write, so a double-approve cannot re-apply the edit | `status` (the current status) | Refresh state |
| `change_request.target_conflict` | 409 | Approval blocked by the three-way merge: a proposed field's current value is **neither** the value captured at submission **nor** the value proposed — i.e. somebody wrote a different value there in the meantime. Movement on fields the proposal does *not* touch never raises this. Nothing is written (all-or-nothing) and the proposal stays `pending` | `conflicts` (list of `{field, base, current, proposed}`), `base_version`, `current_version` | Render the diff; either reject, or apply a merged value via `PATCH /persons/{id}` and then reject. There is no force-approve |
| `change_request.target_deleted` | 409 | Approving a proposal whose target person is currently soft-deleted. Rejection is still allowed | `person_id` | Offer restore-then-approve, or reject |
| `change_request.unsupported_operation` | 422 | An `action`/`resource_type` combination this build does not execute (anything but `update`+`person`). Re-checked at review time, not only at submit | `action`, `resource_type`, `supported` (list of `{action, resource_type}`) | Hide the affordance for unsupported types |
| `change_request.no_changes` | 422 | Submitted with an empty `changes` map | — | Form validation |
| `change_request.field_not_submittable` | 422 | `changes` names a field that is not proposable: `phone`/`email` (contact PII, excluded so the review surface cannot leak it), `avatar_url`, anything the Person aggregate never allows, or an unknown field name — unknown keys are rejected, never silently dropped | `fields` (list of offenders), `allowed` (list) | Show which fields are rejected |

Also raised on these routes: `person_not_found` (404 — target absent from the acting
clan, or soft-deleted at submit time), `validation_error` (422 — a malformed value in
`changes`, or `resource_id` omitted on an update), `stale_write` (409 — a concurrent
writer committed between the merge check and the write), `insufficient_permissions`
(403 — a viewer calling approve/reject), and `invalid_cursor` (400).

### Persons

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `person_not_found` | 404 | Person id not visible in the acting clan (get, update, delete, link targets, relationship endpoints, document/event `person_id`) | sometimes `person_id` or `person_ids` (list) | Not-found state |
| `field_not_updatable` | 403 **or** 422 | 403: viewer self-edit touched non-whitelisted fields (`fields`: list). 422: update payload contained a field the aggregate never allows (`field`: single name) — also on branch/marriage/parent-child/event updates | `fields` (403) / `field` (422) | Show which fields are rejected |
| `person.death_before_birth` | 422 | `death_date` earlier than `birth_date` (any create/update path) | `birth_date`, `death_date` | Inline date validation |

See also **Optimistic concurrency** above: `PATCH /persons/{id}` requires
`expected_version` and can return `stale_write` (409).

### Relationships

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `marriage_not_found` | 404 | Marriage id not found in the acting clan | — | Refresh |
| `parent_child_not_found` | 404 | Parent-child edge id not found in the acting clan | — | Refresh |
| `self_marriage_not_allowed` | 422 | Marriage where both spouses are the same person (domain pre-check; the DB CHECK `ck_marriages_marriages_no_self` is a backstop mapped to this same code if the pre-check is ever bypassed) | — | Form validation |
| `self_parent_not_allowed` | 422 | Parent-child edge where parent == child (domain pre-check; the DB CHECK `ck_parent_child_parent_child_no_self` backstops to this same code) | — | Form validation |
| `relationship.too_many_biological_parents` | 409 | Child already has 2 biological parents in this clan (checked on create, and on a PATCH that changes `relationship_type` to `biological`, excluding the edge being updated) | — | Explain limit |
| `relationship.parent_too_young` | 422 | Biological parent < ~12 years older than child, **and both** birth dates have `precision == "exact"` (checked on create and on a `relationship_type` PATCH). If either birth date is an estimate (`year`/`month`/`circa`/`unknown`), the same age gap does **not** raise this code — the edge is created with a `meta.warning` instead (ADR-011; M5, review 2026-07-18) | `min_age_gap`, `actual` | Show age-gap message |
| `relationship.creates_cycle` | 422 | Edge would make a person their own ancestor (unbounded ancestor walk, no depth cap) | — | Explain cycle |
| `relationship.duplicate_parent_child` | 409 | Identical parent-child edge already exists in this clan | — | Refresh |
| `relationship.duplicate_marriage` | 409 | Active marriage between the two persons already exists in this clan (checked on create, and on a PATCH that flips `status` from `divorced` to any non-divorced status, excluding the marriage being updated) | — | Refresh |
| `relationship.duplicate_spouse_order` | 409 | Two-sided, per-person, orientation-independent (ADR-029): the same person would end up with two active (`status <> divorced` — married, widowed, or separated) marriages sharing the same `spouse_order`, checked across **both** `person1_id` and `person2_id` — checked on create/update when `spouse_order` is set or `status` is non-divorced, and backstopped by the (person1-keyed) partial unique index `uq_marriages_spouse_order` for same-orientation races (a raw `23505` at that index is now mapped by the integrity-error handler to **this** code — by index name — rather than the generic `conflict`, so pre-check and race outcomes match). Accepted consequence: a person can't be the same-rank spouse in two simultaneous live marriages (over-rejects rare polyandry cases — see ADR-029) | — | Ask for a different vợ cả/vợ hai/... order, or refresh to see the current ordering |
| `relationship.divorce_before_marriage` | 422 | `divorce_date` earlier than `marriage_date` (ADR-029). On create, the standard 422 `validation_error` from a Pydantic cross-field validator; on `PATCH /relationships/marriages/{id}`, this domain code — a pre-write check computes the effective (post-PATCH) date pair and rejects before any DB round-trip. The DB CHECK `ck_marriages_marriages_divorce_after_marriage` backstops to this code (422) if the pre-check is ever bypassed, instead of a raw 500 | — | Inline date validation |

A large-but-legal age gap is **not** an error: the link is created and the response
carries `meta.warning` (free text) in the 2xx envelope.

See also **Optimistic concurrency** above: `PATCH /relationships/marriages/{id}` and
`PATCH /relationships/parent-child/{id}` require `expected_version` and can return
`stale_write` (409).

### Branches

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `branch_not_found` | 404 | Branch id (or `parent_branch_id`) not found in the acting clan | `branch_id` | Refresh |
| `branch_cannot_be_own_parent` | 422 | Setting a branch's parent to itself | — | Form validation |

### Documents & storage

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `document_not_found` | 404 | Document id not found in the acting clan | — | Refresh |
| `invalid_document_type` | 400 | Upload with a `document_type` outside the allowed set | — | Form validation |
| `invalid_mime_type` | 400 | Upload MIME type not allowed | `allowed` (list) | Show allowed types |
| `file_too_large` | 400 | Upload exceeds the size limit | `max_bytes` | Show size limit |
| `document_not_linked_to_person` | 422 | Setting a document as avatar when it has no `person_id` | — | Explain requirement |
| `only_photo_can_be_avatar` | 422 | Setting a non-photo document as avatar | — | Explain requirement |
| `document.avatar_source_outside_clan` | 422 | Clan backstop on set-avatar: the document's storage key is not under the acting clan's prefix (ADR-036) | `document_id` | Should be unreachable — report it |
| `person.avatar_url_invalid` | 422 | A published avatar URL was not an absolute http(s) URL within 500 chars (server-side invariant, ADR-036) | `max_length` | Should be unreachable — report it |
| `person.avatar_url_not_permanent` | 422 | A published avatar URL carried a query string or fragment, i.e. was presigned/expiring (ADR-036) | — | Should be unreachable — report it |
| `storage_not_found` | 404 | Referenced storage object missing from the storage backend | — | Treat as missing file |
| `storage_unavailable` | 503 | Storage backend outage/misconfiguration | — | Retry-later banner |
| `storage_bucket_not_configured` | 503 | The public avatars bucket is missing, unreachable, or not public-read — an operator action, not a transient outage (ADR-036) | — | "Avatars unavailable in this environment"; a retry will not help |

Note: the three upload-validation codes are emitted with **400** (domain
`ValidationError` falls through the domain→HTTP mapper's default), unlike other
validation codes which are 422. Branch on the code, not the status.

### Events

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `event_not_found` | 404 | Event id not found in the acting clan | — | Refresh |
| `invalid_event_type` | 422 | Event created/updated with an unknown `event_type` | `event_type` | Form validation |

### Tree

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `clan_founder_not_found` | 404 | Tree requested without `root_person_id` and the clan has no founder | — | Prompt to set founder |
| `tree_empty` | 404 | Tree/branch query produced zero nodes | — | Empty-tree state |
| `same_person_path` | 422 | Kinship path requested between a person and themself | — | Form validation |
| `tree_too_large` | 422 | Tree exceeds the node cap for one response | `max_nodes`, `actual_nodes` | Ask user to narrow scope (subtree / fewer generations) |

### Generic / system

| code | HTTP | raised when | detail keys | client handling |
|---|---|---|---|---|
| `validation_error` | 422 | FastAPI request-body/query validation failed (including a PATCH body missing the required `expected_version`) | `fields` (list of dotted locations) | Map to form fields |
| `conflict` | 409 | Generic conflict; also the safety net for a DB unique-violation race (SQLSTATE 23505) | — | Refetch and retry |
| `rate_limited` | 429 | Too many requests to `/api/v1/auth/*` (20/min per IP, sliding window) | `retry_after` (seconds) | Back off; see header note below |
| `internal_error` | 500 | Unhandled server error (details logged server-side only) | — | Generic error state; safe to retry |
| `database_unavailable` | 503 | Transient DB operational failure mid-request — dropped connection, pool exhaustion, DB restart/shutdown, or resource exhaustion (SQLAlchemy `OperationalError`). NOT our-bug DB errors (`ProgrammingError`/`DataError`), which stay `internal_error` 500 (ADR-032) | — | Retry-later banner; safe to retry with backoff |
| `bad_request` | 400 | Bare 400 normalized into the envelope | `hint` (string, optional) | Generic |
| `invalid_cursor` | 400 | Malformed or tampered `cursor` query param on any cursor-paginated list endpoint — bad base64, non-JSON payload, or valid JSON missing the expected fields (e.g. `full_name`/`id`, `created_at`/`id`) | — | Drop the cursor and refetch the first page; cursors are opaque, never construct one client-side |
| `unauthorized` | 401 | Bare 401 normalized into the envelope | `hint` (optional) | As per 401 rule above |
| `forbidden` | 403 | Bare 403 normalized into the envelope | `hint` (optional) | Hide/disable action |
| `not_found` | 404 | Unknown route, or bare 404 | `hint` (optional) | Not-found state |
| `method_not_allowed` | 405 | HTTP method not supported on the route | `hint` (optional) | Fix client bug |
| `http_error` | varies | Bare HTTPException with a status outside the mapped set | `hint` (optional) | Generic error state |

### 429 and Retry-After

`rate_limited` responses (currently only on `/api/v1/auth/*`) always carry both a
`Retry-After: <seconds>` response header and `detail.retry_after` (same value).
Clients should wait that long before retrying; do not sign the user out.

## Footnotes: i18n cross-check (as of 2026-08-02)

- Every code above has an `error.<code>` translation in all four locale files
  (`vi`, `en`, `fr`, `zh`), and the locale files are key-identical. Enforced by
  `tests/unit/test_i18n_coverage.py` (both directions: every raised code has a `vi`
  key, and no locale lags the union).
- Orphan keys — present in i18n but never raised by any code path (likely legacy;
  do not branch on them): `error.document_not_linked_to_member`,
  `error.member_not_found`, `error.relationship.already_married`,
  `error.relationship.duplicate_edge`, `error.relationship.unusual_age_gap`
  (the age-gap advisory ships as `meta.warning`, not an error),
  `error.relationship_not_found`, `error.same_member_path`, `error.validation`.

## Versioning rules

- `code` strings are a **frozen public contract**. Adding, renaming, or removing a
  code — or changing a code's HTTP status or `detail` shape — is a contract change:
  update this catalog **and** all four `backend/app/i18n/*.json` files in the same PR,
  and notify web/mobile consumers.
- Additive changes (new codes) are preferred; renames/removals need a migration note.
