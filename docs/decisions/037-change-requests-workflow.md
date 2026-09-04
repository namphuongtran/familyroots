# ADR-037: Change Requests — Adopt the Dormant Table, Editor-or-Admin Review, Three-Way Merge on Approval

## Status
Accepted (2026-08-02 — shipped)

## Context

A `viewer` could read their clan's gia phả but had **no way to report an error in
it** — no suggestion, no correction, nothing. A design review of the UI declined to
draw a "Đề nghị sửa" button because there was no endpoint behind it. The owner
approved building one.

This is the highest-value contribution path the platform was missing. The people who
know a birth date is wrong are usually the relatives reading the tree, not the two or
three members with edit rights.

Three things shaped the design:

1. **A `change_requests` table already existed.** Migration `001_initial` created it,
   `app/models/change_request.py` and `app/schemas/change_request.py` existed, and
   `docs/architecture/data-model.md` marked it *"dormant / not implemented — no
   runtime code references them"*. Its shape: `clan_id`, `requester_id`, `action`
   (create/update/delete), `resource_type` (person/marriage/parent_child/event/
   document), `resource_id`, `payload` JSONB, `status`, `reviewed_by`, `reviewed_at`,
   `review_notes`, `created_at`.
2. **`PATCH /persons/{id}` already requires `expected_version`** and returns
   `409 stale_write` on mismatch (ADR-017), precisely so two concurrent editors
   cannot silently clobber each other.
3. **A change request is a stale write waiting to happen.** A suggestion can sit for
   a week while somebody else edits the same person. Applying a week-old payload
   blindly would destroy the newer edit — exactly the failure ADR-017 exists to
   prevent, reintroduced through a side door.

## Decision

### 1. Scope: `action=update` on `resource_type=person` only

Marriages, parent-child edges, events and documents are **deferred, not rejected**.
The real, immediate need is "a relative spots a wrong birth date and reports it".

Nothing about this build forecloses the rest. `action` and `resource_type` are
carried explicitly through the request body, the aggregate, the storage and the
response — never implied — and the guard is a check against a
`SUPPORTED_OPERATIONS` tuple, not an assumption that person-update is the only
shape. Widening that tuple plus adding the matching apply-branch is the whole
change; **no schema migration and no contract change**. Anything outside the executed
set returns `422 change_request.unsupported_operation`, re-checked at review time as
well as at submit so a row written by a different build cannot be half-executed.

### 2. Adopt the dormant table as-is — no migration

The table was taken exactly as it stands. No new columns, no new migration.

Considered and rejected: adding `base_version` / `base_values` / `requester_note`
columns. The existing `payload` JSONB is already the designated home for
proposal-shaped data, it is already `NULL`-able and unconstrained, and the column set
was designed for a workflow of precisely this shape. Spending a migration to
normalize fields that are (a) only ever read as a unit, (b) never queried or indexed
on, and (c) different per `resource_type`, would buy nothing and would make the
future marriage/event variants *harder* (each would want different columns).

So the payload is a documented storage contract:

```json
{ "changes": {...}, "base_values": {...}, "base_version": 7, "note": "…" }
```

`change_request_mapper.to_domain` reads it defensively — a row written by hand or by
an earlier build degrades to an empty proposal rather than raising on load.

The DB CHECK constraints (`action`, `resource_type`, `status` vocabularies) were left
wider than the executed scope on purpose: they are the storage vocabulary, and
narrowing them would be the migration this decision avoids.

Two consequences worth stating: `change_requests` is **not** in the RLS rollout
(ADR-008), so the explicit `clan_id` predicate on every statement is the *only*
isolation layer for this table — pinned by two-sided isolation tests with positive
controls. And the old `updated_at` trigger dropped by migration 008 stays dropped;
nothing here needs it, since a proposal's payload is immutable after submission and
only the review columns are ever written.

### 3. Reviewers: editor **and** admin

An editor can already make the identical edit unilaterally through
`PATCH /persons/{id}`. Requiring admin approval for the same edit *because it arrived
as a proposal* protects nothing — it only adds latency, and a clan with one busy
admin would stall the entire correction queue, which is the failure mode most likely
to kill the feature in practice.

So approve/reject use the hierarchical `RequireEditor` (editor **or** admin) rather
than an explicit `["admin"]` set. For the same reason there is **no self-approval
ban**: an editor who submits and then approves has done exactly what one PATCH would
have done, and the submission and the approval are separately audit-logged.

Submitting is open to any approved clan member (`RequireViewer`). In practice viewers
are the users. A viewer reads only their own proposals — on both list and detail —
and another member's proposal returns `404`, not `403` (ADR-021: the queue is not an
enumeration oracle).

### 4. Approval applies through the ordinary domain write path

Approval loads the same `Person` aggregate, calls the same `Person.update()` (same
field whitelist, same `death_date >= birth_date` invariant), and saves through the
same `PersonRepository.save(expected_version=…)` conditional UPDATE as a normal
PATCH. It is not a second write path.

It is **composed** differently, and deliberately so: rather than calling
`PersonCommandHandler.update()` (which commits its own UoW), the change-request
handler holds both repositories on **one** UoW. The person edit and the status flip
therefore commit together, with both aggregates' domain events dispatched in that
transaction. Reusing the handler would have split the operation across two commits,
leaving a window where the edit landed but the proposal was still `pending` — the
approval and the edit it caused must not be able to come apart.

The audit trail records both: `change_request.approve` and `person.update`, the
latter attributed to the **reviewer** — they authorized the write and are accountable
for it. The requester is on the earlier `change_request.submit` row.

### 5. Staleness: a three-way merge, not a version equality check

**This is the load-bearing decision.**

At submission we capture *two* things about the target: its `version`
(`base_version`) and its **current value for each proposed field** (`base_values` —
only the proposed fields, not a full row copy). At approval, the proposal is
applicable per field:

| target's current value | verdict |
|---|---|
| `== base` — nobody touched this field | **apply**: the proposal overwrites only what the requester actually saw |
| `== proposed` — somebody already made this exact correction | **apply**: re-applying an identical value is a no-op, not a lost update |
| anything else | **conflict**: applying would silently destroy a newer edit |

Any conflict refuses the whole approval with `409 change_request.target_conflict`,
carrying `{field, base, current, proposed}` per conflicting field. Approval is
all-or-nothing — a partly-applied proposal is never reported as approved. The
proposal stays `pending`, so it is not silently consumed.

When the merge passes, the write still uses `expected_version = <freshly read
version>` (not `base_version`): the merge has decided the old proposal is applicable,
and the conditional UPDATE closes the remaining window against a writer that commits
between our read and our write — that one still gets `stale_write`.

**Alternatives rejected:**

- **Strict OCC (`expected_version = base_version`).** The obvious answer, and wrong
  here. On any actively-maintained person almost every week-old proposal would 409 —
  including a birth-date correction blocked because somebody fixed a typo in the
  biography. A correction queue with a near-100% false-conflict rate is a queue
  nobody uses, and the pressure would then be to add a "force approve" escape hatch,
  which is last-write-wins wearing a hat.
- **Last-write-wins (apply the payload unconditionally).** Silently destroys the
  newer edit. This is the exact failure ADR-017 was written to prevent; reintroducing
  it behind an approval button would be worse than not shipping the feature, because
  the loss would be invisible to both members.
- **Per-field partial apply** (apply the non-conflicting fields, flag the rest). The
  reviewer would be told "approved" while part of what they read was not applied.
  The requirement is that "approved" always means the target holds the proposed
  values.

**Reviewers are shown the movement before they act.** Every response carries a
`target` block: `base_version`, `current_version`, `is_stale`, `is_deleted`, and the
per-field `conflicts`. `is_stale: true` with `conflicts: []` is the normal harmless
case (somebody edited a different field) and approval succeeds. Clients gate the
Approve affordance on `conflicts` and `is_deleted`. There is deliberately no
force-approve: overriding another member's edit is a decision made explicitly on the
persons endpoint, with that member's value in front of you.

### 6. Soft-deleted and restored targets

- **Deleted at submit time** → `404 person_not_found`. A deleted person is invisible
  on every read path; a proposal cannot be raised against a record the requester is
  not allowed to see.
- **Deleted between submission and review** → approval refused with
  `409 change_request.target_deleted`, and `target.is_deleted` shows why. Editing a
  record that no longer appears in the gia phả and reporting "approved" would be a
  lie about a visible outcome. The reviewer restores first, or rejects.
- **Deleted and then restored** → delete and restore each bump `version` (ADR-017),
  so `is_stale` is `true`, but neither touches a proposed field, so `conflicts` is
  empty and approval succeeds. This falls out of the merge rule rather than needing a
  special case — which is a good sign the rule is the right one.
- **Rejection has no target preconditions at all.** A proposal against a deleted or
  heavily-conflicted record is exactly what a reviewer needs to be able to clear.

### 7. Proposable fields are narrower than the Person whitelist

`phone` and `email` are **not** proposable. The review surface echoes the target's
*current* value for every proposed field so the reviewer can see what would be
overwritten; allowing contact PII there would leak an ordinary member's details into
the queue for any editor, bypassing the redaction the person read path applies
(L11). Contact details are not gia phả content and are not what relatives correct.
`avatar_url` is excluded because it is set by the document/avatar flow, not typed.

> **Amended 2026-08-22 by [ADR-049](049-contact-pii-is-the-whole-field-visibility-rule.md),
> ADR-049 — read `(L11)` above as
> [ADR-049](049-contact-pii-is-the-whole-field-visibility-rule.md).** `L11` names nothing in
> the tree today. ADR-049 § "Measurement 8b" counted six files citing it and none defining
> it, and this ADR was one of the six.
>
> **The history is one step longer than ADR-049 recorded, re-measured 2026-08-22 by seed
> the same pass.** ADR-049 says the label "entered with commit `8dbf159` on 2026-07-05, where it is
> a label from a review list that was never committed". It *was* committed. `git log -S"L11"`
> run over the whole tree, rather than over `backend/`, returns `bae1ee4` (2026-07-04) one
> commit earlier, which added `docs/architecture/backend-review-2026-07-04.md`. That file
> defined `L11` in a single sentence, quoted here because the file no longer exists:
>
> > L11 within-clan PII by default (`GET /persons profile=full`).
>
> So the label was a **finding**, not a rule: it named the defect, never the redaction that
> answers it. The citations were therefore thin on the day they were written, 2026-07-05.
> They became dangling on 2026-07-12, when `733decc` deleted that review document whole
> (`git diff-tree -r --name-status 733decc` reports `D`, 151 lines). ADR-049 is not amended
> here, because this ADR may not edit another; the correction is handed to the coordinator.
>
> **The rest of § 7 stands unchanged**, and the
> sentence above is left exactly as written, including the dangling label, because this file
> is a dated record of what was believed on 2026-08-02 and erasing the citation would erase
> the evidence that an ADR rested on one. The five citing sites under `backend/` were
> repointed on 2026-08-22; this one is corrected by this note instead, because
> `docs/decisions/README.md` asks that prior ADRs stay immutable except for Status updates,
> and ADR-047 § 3 draws the line at an **append** rather than a rewrite.
>
> What the redaction rule actually is, now that it has a definition: ADR-049 § 1 fixes the
> set at exactly `phone` and `email` and makes it non-configurable, and § 2 gives an
> `editor` or `viewer` those fields for "their own linked person only". § 7's own reasoning
> is unaffected and ADR-049 § 3 restates its point from the other side: `_PII_FIELDS` and
> `EXCLUDED_PERSON_FIELDS` are separate constants that happen to agree, so "if a future
> change adds a third field to the read redaction and not to the change-request exclusion,
> the review queue republishes what the read path just hid."

Unknown field names are **rejected** (`422 change_request.field_not_submittable`),
never silently dropped — Pydantic ignores extras by default, so the whitelist check
runs *before* validation, otherwise a misspelled field would be quietly discarded and
a proposal stored that the requester never made.

The whitelist is written out explicitly rather than derived from the Person
aggregate's private set, so production code never reads a private name; a unit test
pins the two together (`SUBMITTABLE_PERSON_FIELDS` must be a strict subset, and the
difference must be exactly the three documented exclusions) so they cannot drift.

### 8. `changes` keeps the write date shape

Dates inside `changes` (and inside `target.conflicts`) are the scalar `birth_date` +
`birth_date_precision` + `birth_date_display` triple, **not** the `HistoricalDate`
response object every other date field uses (ADR-011). `changes` is a *proposed
request body*, not a rendered record: wrapping it would mean a reviewer's client
could not feed it straight back into `PATCH /persons/{id}` as the manual-merge
fallback, which is the recommended flow on a conflict. This is a documented exception
in `docs/contracts/README.md`, not an oversight.

Mechanically, `PersonUpdateRequest` was split so it derives from a shared
`PersonChangeFields` base (the same fields, minus `expected_version`). A proposed
edit is therefore validated by exactly the same field definitions and bounds as a
direct PATCH, from one declaration — no second, drifting copy.

## Consequences

**Easier.** A viewer can finally contribute. The correction that motivated the whole
feature — "the birth date on my great-grandfather is wrong" — now has an endpoint, an
auditable trail, and a reviewer pool wide enough that it will actually be worked. The
merge rule means an old proposal stays applicable through unrelated editing activity,
which is the difference between a queue that drains and a queue that rots.

**Harder.** There are now two staleness codes on the same underlying concern —
`stale_write` (a version race, ADR-017) and `change_request.target_conflict` (a
per-field merge failure). Clients must handle both, and the distinction has to be
explained in the contract, which it is. The `target` block also makes every
change-request read a two-query operation (proposals, then one batched person
snapshot for the page); that is a deliberate cost for not making reviewers approve
blind, and it is batched so it never becomes N+1.

**Deferred.** Marriages, parent-child edges, events and documents remain
unproposable. `change_requests` is still outside the RLS rollout, so its isolation is
single-layer (application) rather than defense-in-depth — a candidate for a future
RLS phase. And there is no notification when a proposal is submitted or reviewed:
reviewers must visit the queue. All three are additive follow-ups, none blocks this.

## Incidental finding — person *creation* is broken under a live RLS session

Verified while adding the non-bypass-session tests below (`TestUnderRlsSession`).
This is **pre-existing and unrelated to change requests** — it reproduces with a bare
`POST /api/v1/persons` and no change-request code involved — but it is recorded here
because it is the first place it was measured.

With `RLS_ENABLED=True` (the default) on a request session, `POST /api/v1/persons`
fails with `InsufficientPrivilege: new row violates row-level security policy for
table "persons"`. Isolated with a minimal probe on one session and one transaction,
with `current_user = familyroots_app` and `app.clan_id` correctly set:

| statement | result |
|---|---|
| `INSERT INTO persons (…, created_by_clan_id = <GUC>, …)` | **succeeds** |
| the same INSERT plus `RETURNING created_at` | **fails** |

So it is not the `persons_ins` `WITH CHECK` (migration 029 handles that by keying it
on `created_by_clan_id`, not membership). It is the `RETURNING` clause: PostgreSQL
evaluates the returned row against the **SELECT** policy, and `persons_sel` requires a
`clan_memberships` row that does not exist yet — `save_with_membership` inserts
`persons` before `clan_memberships`, exactly the ordering migration 029's own
docstring calls out for the INSERT check but does not follow through to `RETURNING`.
The ORM always emits `RETURNING created_at, updated_at` because those columns have
server defaults, so every ORM person-create hits it.

It is invisible today because no test drives an HTTP write through `RlsSession` — the
Phase 1–4 RLS tests all exercise repositories directly, and every route-level test
overrides `get_db` with a privileged sessionmaker.

Not fixed here: it is ADR-008 / migration-029 territory, needs its own migration
(likely a membership-independent SELECT policy for the just-inserted row, or dropping
the server defaults so no `RETURNING` is emitted), and fixing it inside this change
would be unscoped. `TestUnderRlsSession` therefore seeds its target person through a
privileged session and says so, so the RLS coverage it *does* provide — that
`change_requests` has the grants it needs and that approval's person UPDATE satisfies
`persons_upd` — is honest about its boundary.
