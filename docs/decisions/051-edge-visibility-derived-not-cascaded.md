# ADR-051: Person Soft-Delete Does Not Cascade to Its Edges — an Edge's Visibility Is Derived, Not Stored

## Status
Accepted (2026-08-22, seed S-055) — **decision only, no code in this ADR's pull
request**. Amends [ADR-006](006-soft-vs-hard-delete.md)'s update of 2026-07-02 by
the dated amendment carried in that file. The work it leaves is seed S-056, and
that work is **not** a cascade; see § 8.

## 1. What was decided before, and what is different now

ADR-006's update dated **2026-07-02** says, in full:

> Person/Marriage/ParentChild FKs use `ON DELETE RESTRICT` (persons are never
> hard-deleted). Soft-deleting a person currently leaves its edges live … **Decision:**
> soft-deleting a person will also soft-delete its edges; `restore` re-activates only
> the edges hidden by that same delete.

It was never built. Re-measured **2026-08-22**: `Person.soft_delete`
(`backend/app/domain/person/entity.py:267`) sets the person's own three flags and
emits `PersonDeleted`; `Person.restore` (`:282`) clears them and emits
`PersonRestored`. `grep -rn "PersonDeleted" backend docs` outside
`backend/app/domain/person`, run 2026-08-22, returns one catalogue row
(`docs/contracts/domain-events-catalog.md:78`), three prose references
(`backend/CLAUDE.md:72`, `docs/architecture/domain-rules.md:119,173`), one module
docstring (`person_query_port.py:11`), three test references, and three `SEEDS.md`
lines. **No consumer.** The edge rows still carry `is_deleted = false`.

**Seed S-054 landed on 2026-08-22 and closed the half a client can see.** The three
batch reads that showed an edge to a soft-deleted person now hide it, using a
`NOT EXISTS` anti-join over both endpoints: `get_marriages_batch` and
`get_parent_child_links_batch` via the shared helper `_no_deleted_endpoint`
(`backend/app/infrastructure/persistence/person_query_port.py:84`, applied at
`:119` and `:146`), and `get_stats_for_persons` via the same predicate written
inline in raw SQL (`backend/app/infrastructure/persistence/person_repository.py:274,281`).
They now agree with `get_timelines_batch` and the tree builder, which already
joined the counterpart person.

So the question this ADR answers is **not** "does a client see an edge to a deleted
person" — that is closed. It is narrower and it is about the data: **should the
edge rows themselves be flagged, and if so, how does `restore` tell the edges the
cascade hid from an edge an admin deleted first.**

## 2. Decision

**Person soft-delete does not cascade to `marriages` or `parent_child`. An edge's
visibility is derived on read, not stored on the row.**

The rule, stated once, is the definition of a visible edge:

> An edge is visible when **its own** `is_deleted` is `false` **and neither endpoint
> person's** `is_deleted` is `true`.

Three consequences follow immediately, and they are the point:

- **No migration, no marker column, no event consumer, no trigger.** There is no
  cascade state, so nothing has to record it.
- **ADR-006's second clause is satisfied exactly**, not approximately. An edge hidden
  only because its endpoint was deleted becomes visible again the moment that person
  is restored, because the person's flag is one of the three inputs. An edge an admin
  deleted through `DELETE /relationships/marriages/{id}` before the person was deleted
  keeps its own `is_deleted = true` and stays hidden after the restore. That is
  precisely "re-activates only the edges hidden by that same delete", with nothing
  stored to tell the two apart.
- **ADR-006's first clause is withdrawn.** The edge rows are not flagged. The amendment
  is dated in `006-soft-vs-hard-delete.md`; that update is not rewritten.

## 3. The failure direction, and how it is closed

**Requirement:** an edge whose cascade state cannot be determined stays **hidden**
rather than reappearing.

**How this shape closes it: there is no cascade state to determine.** Visibility is a
total function of three booleans that always exist on rows the read already touches.
There is no marker that can be absent, no event that can be dropped, no write that can
be half-applied.

The predicate is a **disjunction of hiding conditions** — hide when the edge's own flag
is set, **or** when either endpoint is deleted — so an edge appears only when all three
flags are affirmatively `false`. Missing or unreadable information cannot make an edge
appear. It can only hide one. That is the safe direction, and it is a property of the
predicate's shape rather than of any code path remembering to be careful.

The residual risk moves from the data to the code: **a new read that carries half the
predicate.** That risk is real and is named in § 8. It is bounded by three things: the
single helper `_no_deleted_endpoint` (`person_query_port.py:84`), the trap paragraph in
`backend/CLAUDE.md` under "A soft-deleted person and a soft-deleted edge are two
different things", and the test obligation in § 8, which must pin the **outcome** (what
a read returns) and not a setting, per `.claude/rules/seeds.md`.

Note the asymmetry that makes this workable: a stored cascade has the failure direction
running the **wrong** way. A cascade that is lost mid-transaction leaves the edge row
`is_deleted = false` — visible to any reader that trusts the row — with no record that
the cascade was owed. A derived rule cannot fail that way because it is recomputed on
every read.

## 4. Why not cascade — five reasons, each measured at source on 2026-08-22

### 4.1 The restore half can be rejected by the database, and half-applied

This is the reason that decided it, and it was not visible from the seed.

Migration `022_edge_write_serialization` early-returns from the AFTER guard when the
new row is soft-deleted (`backend/migrations/versions/022_edge_write_serialization.py:164`),
so **cascading a delete is cheap**. Re-activating an edge is not: it is an
`is_deleted → false` UPDATE, which runs the full guard — the biological-parent cap
(`:201`) and the recursive ancestry walk (`:209`).

Both of those count **only live rows** (`AND is_deleted = false`, `:198` and `:211`),
and so do the two unique backstops: `idx_parent_child_unique_edge ... WHERE is_deleted
= false` (`:331-333`) and `idx_marriages_unique_pair ... WHERE status <> 'divorced' AND
is_deleted = false` (`:324-328`), plus `uq_marriages_spouse_order ... WHERE spouse_order
IS NOT NULL AND is_deleted = false AND status <> 'divorced'`
(`backend/migrations/versions/015_data_integrity.py:55-58`).

**So a cascade takes the person's edges out of every database invariant while the person
is hidden, and the gap is writable.** Two concrete sequences, both reachable today:

| Step | Under a cascade | Under the derived rule |
|---|---|---|
| Father `P` and mother `M` are `C`'s two biological parents | live | live |
| Admin soft-deletes `P` | `P→C` flips to `is_deleted = true`, leaves the bio-cap count | `P→C` stays `is_deleted = false`, stays in the count |
| Editor adds biological parent `Q→C` | count sees 2 (`M`, `Q`) — **accepted** | count sees 3 — **rejected**, `relationship.too_many_biological_parents` |
| Admin restores `P` | re-activating `P→C` makes the count 3 — the trigger **raises** | `P→C` was never hidden in the data; restore is a single-row flag flip and cannot fail |

The marriage table has the same shape through `spouse_order`: while `A` is hidden, `B`
can take `A`'s freed `spouse_order` slot with a new spouse, and restoring `A` then
collides with `uq_marriages_spouse_order` and surfaces as a `23505` → 409.

**Under a cascade, restoring a person is a multi-row edge write that the database may
refuse in the middle.** The person is restored, some edges are back, one raised. That is
exactly the "graph inconsistent with no record of it" the seed warns about, reached
without any dispatcher losing anything. Under the derived rule the conflicting write is
rejected at the moment someone tries to make it, which is the moment a human is present
to be told.

### 4.2 The cascading restore is an edge write, so it takes ADR-025's per-clan advisory lock

`trg_parent_child_clan_lock` is declared `BEFORE INSERT OR UPDATE OF parent_id,
child_id, relationship_type, is_deleted ON public.parent_child`
(`022_edge_write_serialization.py:151-154`), and **`is_deleted` is in that column list**,
so both halves of a cascade fire it.

**The two halves then diverge, and the asymmetry is deliberate in 022.** The lock body is
guarded: `IF NOT NEW.is_deleted THEN PERFORM pg_advisory_xact_lock(728116,
hashtext(NEW.created_by_clan_id::text)); END IF;` (`:140-142`). So a cascading **delete**
fires the trigger and skips the lock, and the AFTER guard early-returns on it too
(`:164`). **A cascading delete really is cheap.** A cascading **restore** is the opposite:
it is an `is_deleted → false` UPDATE, so it takes the per-clan lock once per edge and then
runs the full AFTER guard on each.

That is the same conclusion § 4.1 reaches by a different route. **A cascade's cost and its
risk are both concentrated in the restore half** — the half ADR-006's second clause is
about, and the half nobody exercises until an admin has already made a mistake. Restoring
a person with a dozen edges would take a clan-wide edge-write critical section and run a
dozen recursive ancestry walks inside it, blocking every other edge edit in that clan.
See [ADR-025](025-per-clan-edge-write-serialization.md) for why that lock is per-clan and
what it already costs. Not cascading costs nothing here, because a person write touches no
edge row and fires no edge trigger at all.

### 4.3 The event-consumer site is ruled out by the dispatcher, and the ADR must say so

The seed names three possible sites. Taking them in turn, and this reasoning stands
whichever way the decision had gone:

| Site | Verdict |
|---|---|
| A `PersonDeleted` consumer | **Ruled out.** `backend/CLAUDE.md` ("Unit of Work + domain events") records the dispatcher is the in-process `InMemoryEventDispatcher` and that in-process events are **not** durable integration events; the repo-root `CLAUDE.md` "Never Do" says the same. A cascade delivered this way can be lost, and a lost cascade is worse than no cascade, because the graph is then inconsistent with nothing recording it |
| The command handler | Possible, and it is what a cascade would have used: it is inside the UoW transaction, so it commits or rolls back with the person. It still pays 4.1 and 4.2 in full |
| A database trigger on `persons` | The only site that cannot be lost, since it runs inside the same statement. It also pays 4.1 and 4.2, and it puts genealogy policy in PL/pgSQL where `app/domain/` cannot see it |

**Because this ADR does not cascade, none of the three runs.** Had it cascaded, the
ranking above is the answer: trigger over handler, and never the event consumer.

### 4.4 The export surface argues against the cascade, not for it

The seed asks whether an export reads the edge tables directly, and says to establish it
rather than assume. **Established, 2026-08-22, at source.**

`SqlAlchemyExportQueryPort` reads both edge tables with raw SQL and **no `is_deleted`
filter at all** (`backend/app/infrastructure/persistence/export_query_port.py:55-66`) —
`SELECT * FROM marriages WHERE created_by_clan_id = :clan` and the same for
`parent_child`. `documents` is the only table there that filters (`:76`). So yes: the
export reads the edge tables directly, and it reads every row.

What the two formats then do with those rows differs, and both cut against a cascade:

- **GEDCOM already applies exactly this ADR's derived rule, in memory, and has since it
  was written.** `backend/app/services/gedcom_export.py:62` builds `live_persons`, and
  `:68-81` keeps a marriage or a parent-child edge only when it is itself live **and both
  endpoints are in `persons_by_id`**, which contains live persons only. The interop export
  therefore already agrees with S-054's reads with no cascade anywhere. This is documented
  behaviour: `docs/contracts/rest-exports-api.md` says soft-deleted persons, marriages and
  parent-child edges are "**Excluded entirely** — not present anywhere in the output".
- **The JSON archive is lossless by contract, and a cascade would make it lossy.**
  `docs/contracts/rest-exports-api.md` states the rule: "`persons`/`marriages`/`parent_child`
  include soft-deleted rows, flagged via their `is_deleted` column — an archive must not
  silently drop history." The archive carries `persons[].is_deleted`, so a consumer has the
  three inputs and can apply this ADR's rule itself. **Flag the edge and that stops being
  true**: an importer reading `is_deleted = true` on a marriage cannot tell an admin who
  deleted that marriage from a spouse who was deleted underneath it — the exact distinction
  ADR-006's second clause exists to preserve. Restoring that distinction inside the archive
  is what the marker column of § 5.1 is for, and it would have to be added to
  `rest-exports-api.md` as a new archive field.

So the "an export or a future consumer reading the edge tables directly sees what the API
sees" argument, checked rather than assumed, **does not survive**. One format already sees
what the API sees. The other deliberately sees more, and cascading would degrade what it
sees rather than improve it.

### 4.5 The schema carries no marker that works, so a cascade genuinely costs a migration

The seed asks whether the marker could be something the schema already carries. Three
candidates, all rejected:

- **`deleted_at` compared against the person's** — the rule the seed names as an
  alternative to a column. It is wrong in the two-endpoint case, and the case is ordinary.
  `Person.soft_delete` stamps `datetime.now(UTC)` per person (`entity.py:270`). Take edge
  `A–B`. Delete `A` at `T1`: the cascade stamps the edge `T1`. Delete `B` at `T2`: the edge
  is already deleted, so the cascade skips it and the stamp stays `T1`. Restore `A` at `T3`:
  the edge's `deleted_at` equals `A`'s, so the rule re-activates it — **while `B` is still
  deleted**. The data is now inconsistent, and only S-054's read filter is hiding it.
- **`deleted_by`** — a cascade writes the same actor as the person delete, so it cannot
  separate a cascade from an admin who deleted the edge and then the person in one session.
- **`version`** (ADR-017 optimistic concurrency) — a monotonic counter, not a provenance
  record. It says a row changed, never why.

## 5. The shapes that were rejected

### 5.1 Cascade with a marker column

Add something like `deleted_by_person_cascade UUID NULL` to `marriages` and
`parent_child`, set to the person id on cascade, cleared on restore.

**Honest, and the only stored shape that keeps ADR-006's promise.** Rejected because it
buys a promise the derived rule already keeps for free, at the price of a migration on two
tables, a new archive field in `docs/contracts/rest-exports-api.md`, plus the whole of
§ 4.1 and § 4.2, which the marker does nothing to fix. The marker records **why** an edge
is hidden; it does not make the restore write succeed when the trigger has decided the
graph moved on.

### 5.2 Cascade with no marker, and drop the restore-symmetry promise

Cheapest cascade. Rejected on the failure direction. With no marker, `restore` either
re-activates every edge touching the person — which resurrects edges an admin deleted on
purpose, the wrong direction — or re-activates none, which leaves the restored person with
a silently emptied graph and no record of which edges were hidden by whom. Both are worse
than today, and the second is the specific outcome the seed names as unacceptable in
reverse.

### 5.3 The single global variant, considered and not adopted

Cascading in a `persons` trigger and never restoring the edges at all (an admin re-creates
them by hand) was considered. It fails § 4.1's second column for a different reason: after
the delete, the edge rows are out of the unique indexes, so re-creating "the same" edge can
land a second live row for the same pair, and the archive then carries both.

## 6. What this ADR does not claim

- **It does not claim the derived rule is applied everywhere today.** It is not. See § 8.
- **It does not claim a cascade is unimplementable.** § 5.1 is implementable and honest. It
  claims a cascade is not worth it, for the five reasons in § 4.
- **It does not change ADR-006's soft-vs-hard table.** Persons, marriages and parent-child
  edges stay soft-deleted, each by its own explicit delete. `Document` still sits under
  [ADR-019](019-document-soft-delete-purge.md), and `Event` and `Branch` stay hard-deleted.
- **It does not touch the write guards.** A soft-deleted `person_id` is still `404
  person_not_found` on marriage, parent-child, event and document creation
  (`docs/architecture/domain-rules.md`, "A soft-deleted person is invisible to every write
  guard"). That guard is what keeps a hidden person from acquiring new edges, and it is
  load-bearing for § 4.1's right-hand column.

## 7. Consequences

**Easier.**
- Restoring a person is a single-row flag flip that cannot be rejected by an edge trigger
  and cannot be partially applied. Its edges come back with it, and only those.
- Person delete and restore fire no edge trigger, so they take no per-clan edge lock
  (ADR-025) and never queue behind another editor's relationship edit.
- No migration, no marker, no archive field, no event consumer on a dispatcher that is not
  durable.
- Every database invariant — the biological-parent cap, acyclicity, both unique pair
  indexes, `spouse_order` uniqueness — keeps counting the hidden edges, so a conflicting
  edge is refused at the moment someone writes it rather than at restore time.
- The JSON archive stays lossless and stays able to express the distinction ADR-006 cared
  about, because it carries all three flags rather than one merged one.

**Harder.**
- **The rule has to be applied by every reader, and forgetting half of it is silent.** This
  is the whole cost of the decision and it is not small. A read that filters only the edge's
  own `is_deleted` compiles, passes, and hands out an edge to a person the same API answers
  `404` for. § 8 names what closes it.
- The edge tables keep rows that are live in the data and invisible in the API. Anyone
  reading `marriages` directly in `psql` sees more than the API shows, and must apply the
  rule by hand. This is stated in `docs/contracts/rest-exports-api.md`'s lossless rule
  already; a database-level view is a possible future convenience and is not built here.
- The `NOT EXISTS` anti-join costs about `0.13 ms` on the marriages batch read for 100 ids
  (`0.115 ms` → `0.246 ms`, measured by S-054 on PostgreSQL 18.4 against 20,000 persons /
  10,000 marriages; the numbers and the plans are in `person_query_port.py`'s module
  docstring). A stored flag would have been free at read time. That is the trade, and it was
  already paid by S-054.

## 8. What is left, and it is not a cascade — the brief for S-056

**Closed 2026-08-22 by S-056, exactly as briefed below and with nothing added.** The two
reads now go through `MarriageReadPort` / `ParentChildReadPort`
(`backend/app/domain/relationship/query_port.py`), implemented by
`SqlAlchemyMarriageReadPort` / `SqlAlchemyParentChildReadPort`
(`backend/app/infrastructure/persistence/relationship_repository.py`), which reuse
`_no_deleted_endpoint` rather than copying it. The command handlers still call the
repositories' unfiltered `get_by_id`. The section is kept as written because it is the
reasoning, not a to-do list. **No column, no `PersonDeleted` consumer, no trigger, no
migration.**

**Two by-id reads still carry half the predicate. Found 2026-08-22 while writing this ADR;
the seed did not name them.**

`SqlAlchemyMarriageRepository.get_by_id` (`backend/app/infrastructure/persistence/relationship_repository.py:151-160`)
and `SqlAlchemyParentChildRepository.get_by_id` (`:191-200`) filter the clan and the edge's
**own** `is_deleted` only. `MarriageQueryHandler.get_by_id` and
`ParentChildQueryHandler.get_by_id` (`backend/app/application/relationship/handlers.py:197-198`
and `:205-206`) are pass-throughs. So **`GET /relationships/marriages/{id}` and
`GET /relationships/parent-child/{id}` still return an edge whose endpoint person is
soft-deleted**, which is the same defect S-054 fixed on the three batch reads, reached by id
instead of by person.

**The fix is not to add the predicate to `get_by_id`, and this is the part worth writing
down.** The same repository method loads the row for the **write** paths —
`handlers.py:69` and `:114` (marriage update, delete) and `:158` and `:184` (parent-child
update, delete). Hiding the row there would take away an admin's ability to delete or repair
an edge that touches a soft-deleted person, and would leave that row unreachable through the
API entirely. **The derived rule belongs on the read projection, not on the shared loader.**

So S-056 is: give the two by-id **reads** their own accessor carrying the same predicate the
batch reads carry — reuse `_no_deleted_endpoint` (`person_query_port.py:84`) rather than
writing a third copy — and leave the command handlers on the unfiltered loader. The test
must pin the **outcome**: with a spouse soft-deleted, `GET /relationships/marriages/{id}`
answers `404` while `DELETE /relationships/marriages/{id}` still succeeds for the same id,
and the negative control deletes the predicate and watches the first assertion fail.

**S-056 builds no cascade, adds no column, and adds no `PersonDeleted` consumer.** If a later
reader believes it should, re-open this ADR rather than adding one, and start with § 4.1.

## Related
- [ADR-006](006-soft-vs-hard-delete.md) — selective soft-delete by aggregate. Its update of
  2026-07-02 is amended by this ADR, by dated amendment in that file.
- [ADR-025](025-per-clan-edge-write-serialization.md) — the per-clan advisory lock and the
  unique backstops a cascade would have to write through (§ 4.1, § 4.2).
- [ADR-023](023-parent-child-db-backstop.md) — the `parent_child` guard ADR-025 amends.
- [ADR-019](019-document-soft-delete-purge.md) — the one aggregate that did change its
  delete posture, and the shape of that write-up.
- [ADR-020](020-clan-export-formats.md) and
  [rest-exports-api.md](../contracts/rest-exports-api.md) — the lossless-JSON and
  GEDCOM-excludes rules checked in § 4.4.
- [ADR-017](017-optimistic-concurrency.md) — the `version` column rejected as a marker in
  § 4.5.
- [architecture/domain-rules.md](../architecture/domain-rules.md) — the soft-delete bullets
  and the write-guard paragraph § 6 relies on.
