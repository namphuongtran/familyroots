# ADR-038: `persons` RLS — Fix the RETURNING/`persons_sel` Collision in the ORM, Not in the Policy

## Status
Accepted, shipped (2026-08-02). Amends the Phase-4 entry of
[ADR-008](008-rls-defense-in-depth.md); no migration — migration `029_rls_persons`
stays exactly as written.

> 🇻🇳 **Tóm tắt:** Tạo người mới (`POST /api/v1/persons`) **thất bại** khi chạy dưới
> role RLS thật: Postgres kiểm tra dòng `RETURNING` bằng policy **SELECT**, mà
> `persons_sel` đòi phải có `clan_memberships` — trong khi `save_with_membership`
> buộc phải chèn `persons` **trước** rồi mới tới `clan_memberships`. Cách sửa dễ nhất
> (nới `persons_sel` cho phép `created_by_clan_id = GUC`) làm mất một tính chất cô lập
> đang có: xoá membership thì dòng họ đó phải **không còn đọc được** người đó nữa. Vì
> vậy ta **không đụng vào policy** — chỉ tắt `eager_defaults` trên ORM để bỏ mệnh đề
> `RETURNING`. CSDL vẫn là nơi sinh `created_at`/`updated_at`/`version`.

## Context

Migration `029_rls_persons` (ADR-008 Phase 4) gave `persons` per-command policies:

```sql
persons_sel FOR SELECT USING (EXISTS (SELECT 1 FROM clan_memberships m
                                      WHERE m.person_id = persons.id
                                        AND m.clan_id = <app.clan_id GUC>))
persons_ins FOR INSERT WITH CHECK (created_by_clan_id = <app.clan_id GUC>)
persons_upd FOR UPDATE USING (<membership>) WITH CHECK (true)
persons_del FOR DELETE USING (<membership>)
```

`persons` is M:N, so membership lives in a second table and `save_with_membership`
must insert the `persons` row **before** its `clan_memberships` row — the FK forces
that order. 029's author saw this and routed around it *for INSERT*, choosing
`WITH CHECK (created_by_clan_id = GUC)` and recording the reason in the migration's
docstring.

What that reasoning missed: **Postgres also matches a `RETURNING` row against the
SELECT policy.** So on one transaction as `familyroots_app` with the GUC set
correctly:

```
INSERT INTO persons (...)                          -- succeeds (persons_ins)
INSERT INTO persons (...) RETURNING created_at     -- ERROR: new row violates
                                                   -- row-level security policy
```

The membership predicate cannot hold yet, so the read-back half of the statement is
rejected even though the write half was authorised. SQLAlchemy 2.0's
`eager_defaults="auto"` appends `RETURNING version, created_at, updated_at` to every
`persons` INSERT (those three columns have server defaults), so **every** person
create takes this path.

It stayed invisible because the app connects as a bypass role in local/CI runs and,
until `test_change_requests.py::TestUnderRlsSession`, no test drove an HTTP write
through a real non-bypass `RlsSession`. It is a hard production failure the moment
RLS enforcement is live for `persons`.

Only `persons` is exposed to this: every other RLS-covered table (`documents`,
`events`, `branches`, `parent_child`, `marriages`) has a same-row column predicate
(`clan_id` / `created_by_clan_id`) that is satisfied by the row being inserted, so
their `RETURNING` clauses pass.

## Decision

**Remove the read, not the policy.** `app/models/person.py` sets:

```python
__mapper_args__ = {"eager_defaults": False}
```

SQLAlchemy stops emitting `RETURNING` for `persons`. The `server_default`s stay on
the columns, so **the database remains the authority** for `created_at`,
`updated_at` and `version` — only the read-back was removed, and nothing consumed
it: the create response is built from the domain entity
(`PersonResponse.model_validate(person)`), which carries its own timestamps, and the
optimistic-concurrency version is re-read by an explicit `session.refresh` on the
UPDATE path.

`029_rls_persons` is left byte-for-byte alone. No new migration, no policy change, no
change to any query plan.

### Alternatives rejected

**1. Widen `persons_sel` to `<membership> OR created_by_clan_id = GUC`.** The obvious
fix, and the dangerous one. It is not a cross-clan leak — `created_by_clan_id` is set
from the GUC at insert — but it silently destroys a property the system relies on:
today, removing someone's `clan_memberships` row makes them invisible to that clan.
Under the widened policy a person clan A created stays readable by clan A forever,
membership or not. Verified empirically before discarding: with the widened policy
installed, a person with origin A and **zero** membership rows is returned by
`SELECT id FROM persons` under GUC = A.

**2. Scope the provenance escape hatch to the transient window** —
`<membership> OR (created_by_clan_id = GUC AND NOT EXISTS (SELECT 1 FROM
clan_memberships m2 WHERE m2.person_id = persons.id))`, i.e. visible via provenance
only while the person has no memberships at all. Tighter, but still wrong here, for
three reasons:

- It fails the same property test. "No memberships at all" is exactly the state a
  person is left in when their **last** membership is removed, so the origin clan
  keeps reading them. Verified empirically alongside variant 1.
- It contradicts an already-pinned behaviour:
  `test_rls_phase4_persons::test_non_member_edge_person_is_hidden` asserts that a
  person with origin A and no membership is hidden from A.
- It costs every person read. The `NOT EXISTS` is per-row, and — worse than its own
  cost — putting the membership `EXISTS` under an `OR` blocks the planner from
  pulling it up into an index-backed semi-join, turning it into a per-row SubPlan.
  `test_rls_phase4_persons::test_persons_rls_membership_subquery_is_index_backed`
  exists precisely because that subquery's plan is load-bearing.

**3. Python-side defaults for the affected columns.** Also removes the `RETURNING`,
but by moving timestamp authority out of the database — clock skew between app
instances, and `TimestampMixin` is shared by every model, so the blast radius is the
whole schema for a `persons`-only problem. `eager_defaults=False` gets the same
effect scoped to one mapper with the DB still generating the values.

**4. Deferrable FK so the membership row can be inserted first.** Would fix the
ordering at the root and need no policy change, but it fights SQLAlchemy's unit-of-work
insert sort (which orders by FK dependency) and weakens immediate integrity feedback on
every membership write, to buy nothing the mapper flag doesn't.

## Consequences

Easier:
- Person creation works under the non-bypass role with the isolation model 029
  established completely intact — no policy widened, no read plan changed.
- The `persons_sel` membership predicate stays a single index-backed `EXISTS`.

Harder — **the constraint this fix works within, for the next author**:
- `persons_sel` still rejects reading a `persons` row back before its
  `clan_memberships` row exists. Any new write path against `persons` must either
  insert the membership first or avoid `RETURNING`. A future column with a
  `server_default` on `persons` is safe (the mapper flag covers it), but a hand-written
  `INSERT INTO persons … RETURNING …`, a `RETURNING`-based bulk/GEDCOM import, or
  removing `eager_defaults=False` would reintroduce the failure. Pinned by
  `tests/integration/test_rls_person_create.py::TestReturningIsStillRejectedByThePolicy`,
  which asserts both halves: the raw `INSERT … RETURNING` is still denied, and the
  compiled ORM `persons` INSERT carries no `RETURNING` clause.
- The same collision will appear on any future table given a policy whose SELECT
  predicate depends on a row written **after** it. Prefer same-row column predicates
  when a table can have one.

## Verification

`tests/integration/test_rls_person_create.py` drives `POST /api/v1/persons` through a
real non-bypass `RlsSession` (the `test_change_requests.py::TestUnderRlsSession`
pattern) and covers:

- the create succeeds, both rows land, and the person is readable on a fresh RLS
  transaction;
- the DB is still the timestamp/version authority (`created_at`, `updated_at`,
  `version` are populated server-side);
- PATCH after create still bumps `version`;
- two-sided clan isolation on read, write and list;
- **the property the rejected fixes destroy** — after deleting the
  `clan_memberships` row, the origin clan gets a 404 over HTTP *and* the row is
  absent from `SELECT id FROM persons` on an RLS session, where only the policy can
  hide it;
- `created_by_clan_id` grants no visibility even to a person with no memberships at
  all.

Negative control: with `eager_defaults=False` removed, 9 of the 11 tests fail with
`(psycopg.errors.InsufficientPrivilege) new row violates row-level security policy
for table "persons"` on
`INSERT INTO persons (…) RETURNING persons.version, persons.created_at, persons.updated_at`.

## Related
- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md) — Phase 4 is the policy this amends
- [ADR-002: Single Schema Clan-Scoped Multitenancy](002-clan-scoped-multitenancy.md)
- [ADR-017: Optimistic Concurrency](017-optimistic-concurrency.md) — the `version` column read back on the UPDATE path
- `backend/migrations/versions/029_rls_persons.py` — immutable and unchanged; its docstring's INSERT-only account of the ordering trap is completed here
- `backend/tests/integration/test_rls_person_create.py`
