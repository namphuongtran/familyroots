# ADR-054: The `clan_settings` Table Is Dropped, and a Per-Clan Setting Must Be Designed Rather Than Re-Enabled

## Status

Accepted (2026-08-22). It closes the hand-off ADR-044 § 5 made to the
coordinator by name. **Shipped**: migration `039_drop_clan_settings`, the ORM model, the
`Clan.settings` relationship, and four documents, in one change.

Every measurement below was taken on **2026-08-22** in `.claude/worktrees/backend`, from
commit `206c802`. Postgres 18.4 (`postgres:18-alpine`).

## Context

### The question, in one sentence

After the two column drops, `clan_settings` is a table with zero rows, five unread columns, and an
RLS policy guarding a reader that does not exist. Does it stay, get built out, or go?

### What was verified rather than inherited

The seed said "zero rows, five unread columns". Three seeds have measured this table and each
found something the previous one missed, so it was re-measured rather than quoted forward.

**The empty-table claim holds.** `git grep "ClanSettings("` over the whole tracked tree
returns one line, the class statement. No trigger in `001_initial.py` creates a row — the only
triggers it installs are `trg_<table>_updated_at` (`001_initial.py:925-937`).

**No endpoint reads or writes it.** `grep -rn "settings" backend/app/api/` returns four lines,
all `from app.core.config import settings` and its uses in `events.py:13,126` and
`documents.py:10,43` — the Pydantic settings object, not this table.
`grep -rn "\.settings\b" backend/app/` returns nothing at all, so `Clan.settings`
(`app/models/clan.py:35`) had no consumer.

**"Five unread columns" is true of `backend/app` and false of the tracked tree.**
`default_language` **is** read, at `backend/tests/integration/test_rls_phase10_clan_settings.py:198,
:205, :292`. The RLS payload column was repointed there when `allow_public_tree` was dropped,
and ADR-044's own amendment under Measurement 1 warns about exactly this: "The scope of a
search is part of the claim it supports." The seed inherited the narrower root and stated the
wider claim. **It does not change the decision** — a test writing a value into a table to prove
a policy is not a reader of that column's meaning — but the sentence was wrong as written.

### The three authorities that decided it, none of which was written to answer this question

**1. The design spec refuses to draw it, under a heading that says so.**
`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:1783-1789`, § 7.10d, read at
source:

> **What this screen must not contain.** The `clan_settings` table (`allow_public_tree`,
> `privacy_level`, `tree_display_mode`, `max_upload_size_mb`, `notification_defaults`) is
> largely inert — nothing enforces those knobs today [...] **No toggle for an unenforced
> setting ships**

§ 9-J21 (`:2394-2402`) repeats it as a numbered lesson. The spec owns screen design, and it
has already ruled every column of this table out of the only screen that would have shown
them. **There is no designed screen for this table and there never was.**

**2. The roadmap has no item for it, and its one row that named it is void.**
`docs/architecture/data-model.md:851` said "Roadmap item D3." Measured 2026-08-22:
`grep -rn "D3\b" docs/` returns five hits — `data-model.md:851` itself, and four unrelated
design-decision rows in `plans/2026-08-02-web-spine.md:68` and three spec files. **There is no
roadmap item D3.** The pointer resolved to nothing. The only row in `docs/roadmap.md` that
named the table is the M1 privacy-toggle boundary at `:41`, and it cites
`backend/app/models/clan_settings.py:28,30` for two columns that were dropped the
same day — `:28` is now `notification_defaults` and `:30` is inside a comment.

**3. ADR-044 § 3 already decided nothing creates a row and nothing should**, with three
consequences enumerated. That decision plus an empty table is a table with no future under its
own terms.

### The wall every feature that reached for this table has hit

This is the finding that turns "dead scaffold" into "a trap that keeps costing". Two separate
pieces of work have reached for `clan_settings` as the home for a per-clan setting, and both
declined for the *same* structural reason, which neither inherited from the other:

| Work | What it wanted to store per clan | Why it declined |
|---|---|---|
| ADR-044 § 2 | `privacy_level` | Missing row is the universal case, so the failure direction must resolve to the most restrictive value; and the row creator has to be built first |
| ADR-049 | a configurable PII field set | Recorded at `docs/decisions/README.md:53`: it "lands on `clan_settings`, which ADR-044 measured dead, and 'no row' is universal, so a configurable set must resolve missing to the maximal set or ship as total disclosure" |

**The wall is ADR-044 Measurement 5 case A**: on a stand-in table carrying `035`'s policy
verbatim, an insert with no `app.clan_id` set — which is the register and onboard path, where
a clan is created — is rejected with `new row violates row-level security policy`. So the
obvious row creator does not work, and every feature discovers that separately.

A table that costs a measurement every time it is examined, and returns no value, is not
neutral. It keeps offering itself as an answer, and the answer keeps being wrong for a reason
that is not visible at the table.

### What the drop actually costs, measured

The costs were enumerated before choosing, not after:

- **`docs/architecture/data-model.md` held the only record of two intended JSONB shapes**,
  `approval_config` and `notification_defaults`. Kept: that section is now a tombstone that
  names the five columns and points here, rather than a deletion.
- **ADR-009's RESTRICT set goes from eleven foreign keys to ten.** `009-clan-deletion-restrict.md:26`
  lists `clan_settings` among the eleven, and `tests/integration/test_schema_baseline.py`
  asserts the clan FKs partition exactly. The test set is updated in this change; **ADR-009
  needs a dated amendment, which this ADR may not write** (one change owns one ADR), so the text is
  handed to the coordinator.
- **`infra/supabase/migrations/001_initial_schema.sql:421` still declares the table.** That
  file is **fenced to a concurrent change** this batch and is not touched here. It was already two
  columns out of date before this change; it is now one table out of date. That change repairs it in
  either direction it chooses — deletion removes the divergence, regeneration picks the drop
  up. `docs/ops/migrations.md` "Known risks" already records Alembic as the source of truth.
- **`web/src/domain/capability/capability.ts:92` declares an `editClanSettings` capability**,
  documented at `:91` as `rbac.md:98 "Edit clan settings"`. It is asserted by
  `capability.test.ts:40,72,105`. **It is not a consumer of this table** — its only runtime
  path is `useClanSettingsMutation` → `updateClanSettings` →
  `http-admin-repositories.ts:67`, which calls `PATCH /clans/me`, the clan-**info** endpoint,
  over the `ClanSettings` type at `lib/types/admin.ts:11` that ADR-044 Measurement 2(d)
  already identified as the `clans` row. So the drop breaks nothing in the web client. It does
  leave the capability named after a table that no longer exists, and its `rbac.md` citation
  now points at a removed row. Handed to the coordinator; `web/` is out of scope here.

None of these is a reason to keep an empty table. Each is a reason the change is bigger than
one migration, which is why they are written down.

## Decision

### 1. The `clan_settings` table is dropped whole, by migration `039_drop_clan_settings`

Reversible. The ORM model `app/models/clan_settings.py`, its export from
`app/models/__init__.py`, and the `Clan.settings` relationship at `app/models/clan.py:35` go
with it.

`DROP TABLE` is not a column drop, and the migration says so at length because five things
ride along silently: the `035` RLS policy, the `trg_clan_settings_updated_at` trigger, the
`RESTRICT` foreign key migration `010` installed, the unique constraint on `clan_id`, and the
`familyroots_app` grants. `downgrade()` rebuilds all five explicitly and restores the table as
revision `038` had it, not as `001` created it.

**`upgrade()` refuses to run if the table holds a row.** The decision rests on the table being
empty. That is measured, but a measurement is dated, so the migration re-checks it at run time
and raises rather than deleting data an operator did not know was there.

### 2. Migration `035`'s policy dies with the table on the way up, and is restored on the way down

The seed asked what happens to the policy in both directions, and the answer is not symmetric
with the code, so it is stated rather than left to be discovered.

**Up:** Postgres drops a table's policies with the table. There is no separate statement and
no warning. Migration `035` is left on disk untouched and stays in the chain as history;
re-running it after `039` is not a supported path and nothing in the chain does.

**Down:** `039.downgrade()` re-runs `035`'s two statements verbatim — `ENABLE ROW LEVEL
SECURITY`, then `CREATE POLICY clan_settings_clan_isolation` with the migration-027 predicate
on both `USING` and `WITH CHECK`. **A claim this ADR nearly shipped, corrected before it landed.** The first draft said a
downgrade that forgot the policy would leave `tests/integration/test_rls_activation.py` red at
`038`. **That is backwards**, and reading the guard at source
(`test_rls_activation.py:443-471`) rather than reasoning from its name is what caught it. The
guard reads RLS-enabled tables from the catalogue and asserts the set **equals** the union of
its four posture sets. Measured 2026-08-22 on two throwaway databases: at `038` with this
downgrade applied the catalogue returns 14 RLS tables including `clan_settings`; at head it
returns 13 without it. Since § 3 removes `clan_settings` from every posture set, a **correct**
downgrade makes that assertion fail with "RLS scope drifted", while a downgrade that skipped
the policy would leave RLS disabled, keep the table out of the catalogue set, and **pass**.

Two things follow. **The guard is pinned to head**, which is where the suite runs, and it is
right about head — `clan_settings` must not be added back to it to make a downgraded database
pass. **And nothing in the suite proves the policy is restored**, so what proves it is the
`cmp` on the catalogue dump and the exercised two-sided isolation in this seed's verification,
not a test. This is the repository's own "a test pins an outcome, not a setting" rule catching
a claim mid-write: the sentence was plausible, named a real file, and would have survived every
mechanical check.

### 3. `clan_settings` leaves the RLS coverage set; its name is not moved to an exemption list

`tests/integration/test_rls_activation.py` loses `"clan_settings"` from
`_CLAN_ISOLATED_TABLES`, and `tests/integration/test_rls_phase10_clan_settings.py` is deleted
whole.

**This is the `audit_logs` rule running forwards rather than backwards.** It established that when
a table fits none of the guard's sets, you add a set rather than push the name into one that
passes. The converse is this: when a table leaves the schema, its name leaves the guard
entirely. It is not parked in an exemption list, because an exemption row is a second place to
record a fact and therefore a second place to be wrong.

**Onboard coverage survives the file deletion, and that was checked before deleting.**
`test_rls_phase10_clan_settings.py:361,387` drove both onboard flows over the RLS seam to
prove Phase 10 broke neither. `test_rls_login_two_clans.py:265,307`
(`test_onboard_create_writes_a_user_clan_roles_row_with_no_clan_selected` and its join
variant) drives the same two flows over the same seam and is untouched.

### 4. A per-clan setting must be designed, not re-enabled

The single most likely misreading of this ADR is "recreate the table when a setting is needed".
**That repeats the mistake.** Whoever builds per-clan configuration solves these first, and
the schema is the last part, not the first:

| Term | What it means |
|---|---|
| **A row creator that survives the policy** | ADR-044 Measurement 5. The obvious creator — insert during clan creation, on the request session with no clan GUC — is rejected. It runs on the system session (the ADR-048 precedent) or lazily on a clan-scoped write |
| **A failure direction closed at the most restrictive value** | "No row" is not an edge case here, it is the universal case. A missing row, an unreadable row, NULL, or an unrecognised value all resolve to the most restrictive setting the domain holds. ADR-044 § 2 and ADR-049 both reached this independently |
| **A named reader, before the column** | Every one of the seven columns this table ever had was written before anything read it, and not one reader ever arrived. Build the reader first and let it say what it needs |
| **A value domain closed at the database** | `NOT NULL`, a default, and a `CHECK` or enum. The old `privacy_level` was proved to accept `'wide-open'` without complaint, which is what an unconstrained `String(20)` buys |

### 5. Two documents stop promising a feature no endpoint backs

**A decision that leaves the misleading documents standing has not been made**, so both land
in this change.

- **`docs/architecture/rbac.md`**: the `CLAN SETTINGS` block and its `View clan settings` and
  `Edit clan settings` rows are removed, and the ASCII role tree at `:15` now reads
  `Edit clan info (PATCH /clans/me)` instead of `Manage clan settings`. A dated note under the
  matrix records the J22 rule — **a row in this matrix is not evidence that an endpoint
  exists** — where a reader meets it.
- **`docs/contracts/rest-clans-api.md`**: "Adding new clan settings fields is non-breaking"
  now says **clan info**, names the `clans` columns it means, and states that there is no
  per-clan settings resource. This was the only mention of settings in the whole contract set.

### 6. Two further unbacked rows in `rbac.md` are recorded and deliberately left standing

Found while removing the settings rows, both verified at source, both left alone because
deciding their fate is not this seed's to make:

- **`Export tree as PDF`** (all four roles ✅). `grep -rni "pdf" backend/app/api/ backend/app/application/`
  returns **nothing**. This is J22's *original* instance — the design spec removed the button
  it had drawn from this row and recorded the lesson at `:2404-2409` — and the row that caused
  it is still here, three rows above the two this ADR removed.
- **`Configure notification settings`** (all four roles ✅). There is no notifications module
  in `backend/app/api/v1/`; the only related routes are `POST`/`DELETE /me/fcm-token`
  (`auth.py:175,190`), which register a device rather than a preference. The column that would
  have held clan defaults, `clan_settings.notification_defaults`, goes with this table.

Both are named in the note added to `rbac.md` under § 5, so the next reader meets the finding
at the row rather than in a chat reply.

## Consequences

### What this buys

- **The trap stops being re-derived.** Two pieces of work have already paid to discover that
  this table cannot take a per-clan setting. The third would have paid again.
- **The schema stops contradicting the documents.** Before this change, four documents
  described a feature and the schema declared it, while no endpoint existed. Now none do.
- **One dead `SELECT` leaves the auth path.** `Clan.settings` was `lazy="selectin"`, so every
  load of a `Clan` ORM entity emitted a second query against `clan_settings` — including
  `get_clan_by_slug` and `get_clan_by_id` on the register and onboard paths, where it returned
  zero rows under `035`'s policy. That query is gone.
- **The RLS coverage set shrinks by a name that taught nothing.** Its policy was correct,
  cheap, and inert, and a green two-sided isolation proof for it was never evidence that
  anything used the table. That lesson is now in `backend/CLAUDE.md` rather than in a table.

### What this does not buy, stated plainly

- **No behaviour changes and no response changes.** No endpoint read or wrote this table, no
  contract documented its shape, and no row ever existed. Anyone measuring "did this change an
  API" will correctly find that it did not.
- **It decides nothing about per-clan configuration as a product idea.** It decides that the
  current table is not the way in, and § 4 fixes what the way in has to include.
- **The round trip is not exact on `attnum`, and it is the tidier direction.** At `038` the
  live columns are `1,2,3,4,5,7,9,10,11` — the gaps at 6 and 8 are tombstones from `037` and
  `038`, and Postgres never reuses a dropped `attnum`. `CREATE TABLE` cannot reproduce a gap,
  so `downgrade` returns `1..9` contiguous. This is the mirror of the `privacy_level` finding that
  `ADD COLUMN` could not restore ordinal position either. Everything that carries meaning
  round-trips identically, proved by `cmp` against a database that never carried `039`.
- **`infra/supabase/migrations/001_initial_schema.sql` is now one table out of date**, and
  this ADR does not fix it. It belongs to the concurrent change this batch.
- **`web`'s `editClanSettings` capability keeps its name and loses its `rbac.md` citation.**
  Nothing breaks; it never touched this table.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| **Keep the table and build the row creator** (ADR-044 § 5 costs it out) | It builds a writer for a column nobody reads, on a session that has to be chosen (system versus lazy clan-scoped), and the first row would carry `max_upload_size_mb = 10` while the enforced limit is 50 (`app/core/config.py:120-128`) — so every clan would gain a stored value that contradicts the enforced one. It would also activate an eleventh `RESTRICT` blocker on clan deletion for a row nothing uses. All cost, no reader. **This is the option that most resembles progress and delivers least** |
| **Keep it dormant and write down that it is dormant** | The seed's own "costs least and buys least", and it was the leading candidate. It lost on evidence: **the warning-at-the-table approach had already been tried on this exact table and did not stop the cost.** `app/models/clan_settings.py:29-32` carried a five-line "NOT wired yet — do NOT start reading it" comment about `max_upload_size_mb`, mirrored at `app/core/config.py:126-127`. That comment warns about one column's default. It does not say the table has no rows and that nothing can create one on the request session, which is the fact ADR-044 and ADR-049 each had to establish on their own. A dormancy note would have to carry the whole of Measurement 5 to be worth more than the two ADRs that already carry it |
| **Drop only the three remaining scalar columns, keep the table** | Strictly worse than either end. It leaves a table with `approval_config` and `notification_defaults`, the same empty-table problem, the same policy, the same selectin, and a fourth migration in the same series. It optimises for the size of the diff rather than the state of the tree |
| **Delete the ORM model but leave the table in the database** | The schema is the thing a later agent reads as intent, and `test_schema_baseline.py` compares the ORM to Alembic, so this would fail the gate immediately. It also inverts the repository's own rule that the code is the truth |
| **Wait for the concurrent change to settle `infra/supabase/migrations/` first** | Considered seriously, because that file is the one real divergence this change creates. Rejected because that change repairs the divergence in **either** direction it chooses, its two options are deletion and regeneration-from-Alembic, and both absorb this drop. Sequencing the decision behind it would trade a known, tracked, one-file divergence for a delay, and ADR-044 § 5's hand-off is already the second batch old |
| **Write a `Not verified` row instead of deciding** | Nothing here is unverified. Every claim above is dated and re-runnable, and the seed is a decision seed: shipping the wrong answer is worse than shipping nothing, but shipping *no* answer is what left the table in this state for two batches |

## What this ADR deliberately does not decide

- **Whether FamilyRoots ever ships per-clan configuration.** It decides that the current table
  is not the way in, and § 4 names what the way in must include.
- **The fate of `infra/supabase/migrations/`** — a concurrent change.
- **The two remaining unbacked `rbac.md` rows** (§ 6). Named, measured, and left standing.
- **`web`'s `editClanSettings` capability and its stale `rbac.md` line citations.** Out of
  scope; handed to the coordinator.
- **Any amendment to ADR-009 or ADR-044.** One seed owns one ADR. The text for both is handed
  to the coordinator.

## Related

- [ADR-044](044-privacy-toggles-dropped-from-v1.md) — § 5 handed this question over by name;
  Measurement 3 is the empty-table proof, and Measurement 5 is the row-creation wall § 4 rests
  on. The decision and its two column drops carried it.
- [ADR-049](049-contact-pii-is-the-whole-field-visibility-rule.md) — reached the same wall from
  the field-visibility side, independently.
- [ADR-008](008-rls-defense-in-depth.md) and migration `035_rls_clan_settings` — the policy
  this table carried, and the clearest case in the repository of a correct policy guarding a
  reader that never arrived.
- [ADR-009](009-clan-deletion-restrict.md) — the `RESTRICT` set that goes from eleven foreign
  keys to ten. **Needs a dated amendment.**
- [ADR-050](050-user-clan-roles-clan-keyed-mutations.md) — the other half of the Phase 10 work, which
  named both tables.
- [`../superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
  § 7.10d and § 9-J21, which refuse to draw this table, and § 9-J22, the matrix rule § 5 and
  § 6 apply.
- [`../ops/migrations.md`](../ops/migrations.md) — the chain, and the `039` paragraph.
