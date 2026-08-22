# ADR-044: `allow_public_tree` and `privacy_level` Are Dropped from v1, and the Concept Returns Only as One Column

## Status

Accepted (2026-08-22), by seed **S-016**. **Nothing is shipped by this ADR.** It is a decision.
Seeds **S-017** and **S-018** are the changes that carry it, one column each. No gate was run,
because this file and its index row are the whole diff — the seed's `Verification` field says so.

Every measurement below was taken on **2026-08-22** in `.claude/worktrees/design`, at commit
`1f59cab`.

## Context

### The question, in one sentence

`backend/app/models/clan_settings.py:28` declares `allow_public_tree` and `:30` declares
`privacy_level`. Nothing reads either one. Does v1 enforce them, drop them, or keep them inert?

### The rule this decision has to obey

`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:2400-2402`, read at source:

> A privacy toggle that does not restrict anything is the most harmful control in this
> product — a trưởng họ could set `riêng tư` and reasonably believe the tree is private.
> None of them ship until enforcement does.

That rule is written about a screen. It binds a backend decision because the screen is downstream
of the column: a column that exists is the thing a later agent renders.

### Measurement 1 — the absence claim, re-run today

The seed's absence claim is a measurement, so it was re-run rather than quoted forward.

```
$ date
Sat Aug 22 12:13:42 +07 2026
$ grep -rn "allow_public_tree\|privacy_level" backend/app web/src mobile/lib
backend/app/models/clan_settings.py:28:    allow_public_tree: Mapped[bool] = mapped_column(Boolean, default=False)
backend/app/models/clan_settings.py:30:    privacy_level: Mapped[str] = mapped_column(String(20), default="clan_members")
```

Two hits, both declarations, in one file. No reader in the backend, the web client, or the mobile
client.

> **Amended 2026-08-22 by seed S-017, which dropped `allow_public_tree` and checked first.** The
> command above searches `backend/app web/src mobile/lib`. **`backend/tests` is not in it**, and the
> sentence "no reader in the backend" reads wider than the command supports. One hit lies outside
> that root: `backend/tests/integration/test_rls_phase10_clan_settings.py:270` wrote
> `allow_public_tree = true` and `:284` read it back, as the payload of
> `test_update_of_the_other_clans_settings_touches_no_row`.
>
> **It was never a reader of the column's meaning** — the RLS policy under test does not refer to the
> column, which was only an arbitrary value to update. S-017 repointed it at `default_language`,
> which `_seed_two` writes explicitly, so the closing assertion can no longer pass on a server
> default the way `assert allow_public is False` could. The decision in § 1 is unchanged.
>
> **The scope of a search is part of the claim it supports.** Measurement 2 below already says this
> about names; it applies to roots as well, and this table is the instance.

### Measurement 2 — the same question asked about the **concept**, because a name search is a claim about names

Seed **S-020** established on 2026-08-22 that its own absence claim was false: it had searched for
`field_visibility|visible_fields`, column names nobody ever chose, while a field-level visibility
rule ships as `_PII_FIELDS` and `_redact_person_pii`
(`backend/app/application/person/handlers.py:29-54`). **An absence claim built on a name search is
a claim about names, not about behaviour.** So four further questions were asked. Three of the four
answers are absences, and the fourth is not.

**(a) Is there a reader of a clan's tree or persons who is not an approved member?** No. Every
`@router.*` decorator in `backend/app/api/` was enumerated with its full signature. Exactly five
routes carry no user dependency, all in `auth.py`: `/register` (`:46`), `/login` (`:83`),
`/refresh` (`:103`), `/forgot-password` (`:113`), `/resend-verification` (`:129`). None returns
person or tree data; `/register` returns a constant string (`auth.py:61`). The near misses were
checked rather than assumed: `POST /invitations/{token}/accept` **does** carry
`Depends(get_current_user)` (`invitations.py:95-99`) and returns only `clan_id`, `role` and a
message; `GET /exports/clan` carries `RequireAdmin` (`exports.py:22-31`); all five `get_system_db`
sites (`dependencies.py:144, 149, 167, 174, 359`) sit behind authenticated routes.

**(b) Does a graded visibility mechanism already exist under another name?** Yes — four of them,
and **not one is about who may read the clan.** They are worth naming so that a later reader does
not mistake any of them for prior art:

| Mechanism | Source | What it actually restricts |
|---|---|---|
| PII redaction | `application/person/handlers.py:29-54`, applied at `:148` and `persons.py:126, 267, 337` | two fields, `phone` and `email`, from a non-admin viewing anyone but their own linked person |
| Change-request queue scoping | `application/change_request/handlers.py:274, 290-294` | which rows of the queue a `viewer` sees — their own proposals only, as a 404 |
| Viewer self-edit whitelist | `application/person/handlers.py:117-135` | write side: which fields a `viewer` may change on their own linked person |
| Clan user-list asymmetry | `docs/contracts/rest-clans-api.md:59, 70, 78-80`, ADR-039 | `email` appears on the admin-only pending queue and never on the viewer-readable member list |

Two things that look like the mechanism and are not: `profile=summary|detail|full` is caller-chosen
and takes no role input (`api/v1/persons.py:99-106`, `tree.py:39`), and `app/core/fieldsets.py` is
sparse-fieldset plumbing with no actor argument. Absent entirely: living-person hiding, any
`visibility` column on any table, any per-person or per-branch flag.

**(c) Does a client name the concept in any language?** No. `web/src` and `mobile/lib` return zero
hits for the identifiers and zero for the concept, searched in English and Vietnamese
(`privat|privac|riêng tư|công khai|chia sẻ|share|visib`). None of the four backend locale files
(`backend/app/i18n/{vi,en,zh,fr}.json`), the four web message files, or the two mobile `.arb` files
carries a privacy, visibility or sharing key.

**(d) The one hit that is not an absence, and it is the reason this measurement exists.**
`web/src/lib/types/admin.ts:11` declares `export interface ClanSettings`. **It is not this table.**
Its fields are `id, name, slug, description, origin_place, founded_year, avatar_url, motto,
ancestral_hall_location, clan_rules, is_active, created_at, updated_at, stats` — the `clans` row,
matching `backend/app/schemas/clan.py:29-46`. Its only consumer renders four inputs and no toggle.
A name search for "clan settings" in the web client therefore lands on a type that has nothing to
do with `clan_settings`, which is exactly the shape of the S-020 trap running in the other
direction.

### Measurement 3 — the table is empty, and **every** column in it is dead, not only these two

The precondition S-010 and S-020 added to the seed is that nothing constructs a `ClanSettings`.
Re-run today, it holds, and it is broader than the seed says.

```
$ grep -rn "ClanSettings(" backend/app
backend/app/models/clan_settings.py:13:class ClanSettings(TimestampMixin, Base):
```

One hit, the class statement. Each of the seven data columns was then searched on its own name:

| Column | Hits outside `app/models/clan_settings.py` |
|---|---|
| `approval_config` | none |
| `default_language` | none |
| `tree_display_mode` | none |
| `allow_public_tree` | none |
| `notification_defaults` | none |
| `privacy_level` | none |
| `max_upload_size_mb` | one comment, `app/core/config.py:127`, saying it is not wired |

The only application reference to the table is the `Clan.settings` relationship
(`app/models/clan.py:35`), and `grep -rn "\.settings\b" backend/app` returns no consumer of it.
`001_initial.py:930-937` creates only `trg_<table>_updated_at` triggers, so nothing populates the
table either.

**So `clan_settings` is not a live table with two dormant columns. It is a dead table**, and these
two are two of seven. That is a finding S-016 did not have; it is recorded in § 5 rather than acted
on here.

### Measurement 4 — the value domain **is** written down, and the seed's claim is corrected

S-016 says `privacy_level` is "a `String(20)` whose value domain is not stated anywhere the seed
found", and S-018 offers "the domain is genuinely undecided" as a possible finding. **Neither is
true.** The domain is stated, at `docs/architecture/data-model.md:836`, read at source today:

```
| `privacy_level` | VARCHAR(20) | DEFAULT 'clan_members' | `private`, `clan_members`, or `public` |
```

The domain is decided. What is missing is every mechanism that would make it mean anything:

- **Nothing enforces it.** `grep -rn "privacy_level\|allow_public_tree" backend/migrations/` returns
  two lines, both column definitions in `001_initial.py` (`:600`, `:603`). There is no `CHECK`
  constraint, no PostgreSQL enum, and no validator anywhere. The ORM type is a bare `String(20)`.
- **One of the three values duplicates the other column.** `privacy_level = 'public'` and
  `allow_public_tree = true` are the same fact, with nothing reconciling them and no source saying
  which wins.
- **One of the three values has no defined meaning.** `private` is more restrictive than
  `clan_members`, and no source in this repository says private **from whom**. In a product whose
  unit of sharing is the clan, and whose `viewer` role is defined as "Read-only access to all clan
  data" (`docs/architecture/rbac.md:26`), a level below `clan_members` is either "admins only" or
  nothing. Nobody has decided which.
- **One of the three values is what the system already does**, unconditionally: `clan_members`.

So the domain is not undecided. It is **documented, unenforced, and one third meaningless.**

### Measurement 5 — what "create the row" costs, measured rather than predicted

Migration `035_rls_clan_settings` gave the table the migration-027 predicate on both halves. The
seed requires this ADR to say what creates the row. That depends on a fact nobody had measured, so
it was measured on a throwaway database, on the same Postgres the suite uses — a stand-in table
carrying `035`'s policy verbatim, and a `NOBYPASSRLS` role standing in for `familyroots_app`.
Postgres 18.4 (`postgres:18-alpine`), 2026-08-22:

```
--- A: insert with NO app.clan_id set (the register/onboard path) ---
ERROR:  new row violates row-level security policy for table "cs"

--- B: same insert WITH the GUC set to that clan (a clan-scoped request) ---
INSERT 0 1
 rows_visible_to_that_clan = 1

--- C: read with NO GUC, one row present (inserted privileged first) ---
 rows_visible_with_no_guc  = 0
 rows_actually_in_table    = 1
```

Case C ends with a privileged read proving the row was there, because on an empty table a denial
assertion proves nothing on its own (S-012's rule, restated by S-010).

**Read case A against the obvious implementation.** "Auto-create a settings row when a clan is
created" is precisely what `docs/architecture/data-model.md` claimed already happened until S-010
corrected it on 2026-08-22. Clan creation runs in `POST /auth/register`, on the request session,
with no clan GUC: `backend/app/api/v1/auth.py:17` imports `get_current_user` and nothing else from
`app.core.security`, so no route in that file can have one. Under `035`'s `WITH CHECK`, that insert
is case A.

This is not an analogy. It is the **same failure S-010 measured on `user_clan_roles`** the same
day: `add_membership` (`auth_repository.py:69-88`) inserts on that same clan-less session, and both
onboard flows raise `psycopg.errors.InsufficientPrivilege` and answer 500.

So creating the row has exactly two shapes, and neither is a default:

1. **On the system session**, the ADR-048 precedent — a privileged provider for the clan-create
   path, or a raw statement on `get_system_db`.
2. **Lazily, on the first clan-scoped write**, where case B shows the GUC is already set.

### Measurement 6 — a public tree has no honest clan to scope to, and no document imagines its reader

`get_current_clan_id` (`backend/app/core/security.py:249-268`) selects the caller's **approved**
`user_clan_roles` rows, raises `no_approved_clan_membership` when there are none (`:257-258`),
validates any `X-Current-Clan-Id` header against that list (`:267`), and only then sets the GUC at
`:290`. The clan a request is scoped to is **derived from membership**.

An anonymous public-tree route has no membership. Its clan can only come from the URL, which the
caller chooses. Setting `app.clan_id` from a caller-supplied value means RLS layer 2 stops being a
second layer on that route: the caller names their own tenant and the policy agrees. That route
would have **one** layer of clan isolation where every tree route has two — the shape ADR-048
recorded for `POST /invitations/{token}/accept`, where the token is the layer.

The documents say the same thing by omission. The permission matrix in
`docs/architecture/rbac.md` has a header row at `:62` with four columns — `super_admin`, `admin`,
`editor`, `viewer` — and **there is no fifth**. Its `FAMILY TREE` section (`:96-98`) grades the
tree across those four and no others. `docs/architecture/multi-tenancy.md:77-80` describes
active-clan resolution as validating approved membership and rejecting a suspended clan, and
nothing else. Neither file contains a row, a column, or a sentence for an anonymous, logged-out, or
non-member reader of a tree.

**So the architecture set rests on an unstated assumption that every reader is an approved member
of exactly one active clan.** `allow_public_tree` has nothing to attach to: no dependency yields
"no clan and no user", no policy evaluates without `app.clan_id`, and no document defines the role
of the reader it would create.

### What the three options share, and the fourth shape

The seed offers: enforce both, delete both, or keep both and note them in a contract. All three
read "delete" as the expensive, irreversible option and "keep" as the cautious one.

**The precondition inverts that ordering, and this is what the seed's own text did not name.**
Deleting a column is normally frightening because rows are lost. There are **no rows** —
Measurement 3, with Measurement 5 case C showing what a row would even look like. So for these two
columns, delete is the option that is exactly reversible and loses nothing: the down migration
re-adds a column of the same type with the same `server_default`, and the table is empty either
way, so the round trip is exact.

The fourth shape follows. **The question is not "keep or delete". It is "delete, on what terms of
return" — and the two columns get different terms.** That is the per-column difference S-016 asked
for, and it is a real one rather than the same answer written twice.

## Decision

### 1. `allow_public_tree` is dropped, and this column does not come back (S-017)

Dropped by a reversible migration. The **concept** it names may return one day. **This column may
not.**

`privacy_level = 'public'` and `allow_public_tree = true` are the same fact (Measurement 4), and
the documented domain makes that explicit rather than inferred. Reintroducing a boolean beside a
level would put two authorities on one question, which is the defect ADR-027 exists to prevent —
there it was two ways to compute đời, here it is two ways to say "public". `privacy_level` can
express `allow_public_tree` completely; the reverse is false. So the boolean is the redundant one,
and this ADR closes that door now rather than leaving it to whoever builds the feature.

It is also the specific control the design spec refuses by its Vietnamese label: `Cho phép xem công
khai` (`specs/2026-08-02-design-system-and-screens.md:1787-1789`).

### 2. `privacy_level` is dropped from v1, and it may return on four named terms (S-018)

Dropped by a reversible migration. It is the right **shape** for the concept and the wrong
**type**, and Measurement 4 shows its documented domain is undefended and one third meaningless.

`String(20)` with no `CHECK` means an unrecognized value is a value. A branch reading an
unrecognized value most plausibly falls through to its permissive arm, which is the failure
direction the design rule forbids. Adding the constraint today would produce a better-typed dead
column; adding it on return costs the same migration.

**If it returns, it returns with all four of these in one change:**

| Term | What it means |
|---|---|
| **Value domain, closed at the database** | NOT NULL, `DEFAULT 'clan_members'`, and a `CHECK` constraint or a PostgreSQL enum. The domain is `clan_members` plus every value the same change actually enforces. `private` does not re-enter the domain until a source states private **from whom** — Measurement 4. A value outside the domain is rejected at write time, never interpreted at read time |
| **Enforcement point, named** | The dependency that decides who may read a clan's tree: `get_current_clan_id` (`app/core/security.py:245-295`) together with `RequireViewer` (`app/api/v1/tree.py:38`). A privacy level is a **widening** of that gate, so it belongs inside it — not in a query handler, not in a repository, and not in the RLS policy (§ 4) |
| **Failure direction, closed** | A missing row, an unreadable row, NULL, or an unrecognized value all resolve to the **most restrictive** level the domain holds, which is `clan_members` today. Never to `public`. This is not a preference. Measurement 3 shows **every** clan has no row, so "missing" is the universal case, and if missing meant `public` this ADR would be describing a total disclosure |
| **The row creator, built first and on the right session** | Measurement 5. Nothing can read the column before something writes a row, and the shape a reader reaches for first — insert during clan creation on the request session — is rejected by the live policy |

### 3. Nothing creates a `clan_settings` row, and after this ADR nothing should

The seed requires this ADR to say what creates the row and with what defaults, or to record that
nothing does and what follows. **Nothing does, and that is now a decision rather than an
omission.** Three consequences, stated so they are not rediscovered:

- **The defaults already exist, in the database, and they are not the ORM's.**
  `001_initial.py:594-607` gives every column `NOT NULL` and a `server_default`:
  `default_language 'vi'`, `tree_display_mode 'vertical'`, `allow_public_tree false`,
  `privacy_level 'clan_members'`, `max_upload_size_mb 10`. The `default=` values in
  `app/models/clan_settings.py` are Python-side and apply only when the ORM constructs the object,
  which nothing does. A future creator does not need to supply values. It needs to supply a row.
- **One default is already wrong.** `max_upload_size_mb` defaults to `10` while the enforced limit
  is `Settings.MAX_UPLOAD_SIZE_MB`, 50 (`app/core/config.py:120-128`,
  `app/models/clan_settings.py:31-35`, and `data-model.md:820-825` records the disagreement).
  Creating rows today would give every clan a stored value that contradicts the enforced one.
- **A row is an eleventh RESTRICT blocker on clan deletion.** `clan_settings.clan_id` is one of
  ADR-009's eleven `ON DELETE RESTRICT` foreign keys (`009-clan-deletion-restrict.md:26`, applied
  by `010_clan_fk_restrict.py:34`, which converted `001_initial.py:589`'s original CASCADE). With
  no rows the table blocks nothing. There is no clan-delete endpoint today — measured 2026-08-22,
  `grep -rn "delete_clan\|delete(Clan" backend/app` returns nothing — so this is a cost to a manual
  deletion and to whoever builds that endpoint, not a live defect.

### 4. RLS is not the enforcement point for privacy, and migration `035` stays exactly as it is

A reader who has just finished the Phase 1-11 rollout will reach for the policy. It cannot carry
this rule, for two independent reasons:

- **It scopes the wrong thing.** `clan_settings_clan_isolation` answers "which clan's settings row
  may this session see". A privacy level answers "may this caller see this clan at all". The second
  question is decided **before** a clan is selected, and Measurement 5 case C shows the request
  session reads zero rows before the GUC is set.
- **On a public route the GUC is caller-supplied** (Measurement 6), so a policy keyed on it grants
  exactly what the caller asked for.

Enforcement is application-layer, at the gate named in § 2. RLS stays what ADR-008 made it: a
backstop against a missed `WHERE clan_id`, not an authorization system.

### 5. What this ADR does not drop, and what it hands to the coordinator

Measurement 3 found all seven data columns unread, so this is a dead table rather than a live table
with two dormant columns. **This ADR drops two columns and nothing else**, because the other five
were not in the seed and one of them is named out of scope by it.

That leaves a finding rather than a change: after S-017 and S-018 land, `clan_settings` is a table
with zero rows, five unread columns, and an RLS policy guarding a reader that does not exist. That
is a new seed or an `Owed` row, and it belongs to the coordinator.

Two documents also promise this feature and should be corrected by whoever owns them, in a change
that is not this one:

- `docs/architecture/rbac.md:113-115` carries `View clan settings` and `Edit clan settings` rows in
  the permission matrix. No endpoint reads or writes the table, so those two rows describe
  capabilities that cannot be exercised. This is the J22 defect from the design spec, verbatim: **a
  permission matrix is not evidence that an endpoint exists.**
- `docs/contracts/rest-clans-api.md:168` says "Adding new clan settings fields is non-breaking",
  using "clan settings" to mean the `PATCH /clans/me` clan-info body rather than this table. It is
  the only mention of settings in the whole contract set, and it reads as covering the table.

## Consequences

### What this buys

- The most dangerous control in the product cannot be rendered, because the field a client would
  bind to stops existing. The design rule at `specs/2026-08-02-design-system-and-screens.md:2400`
  becomes something the schema enforces rather than something everyone has to remember.
- **The columns stop being documentation that outranks the documentation.** A column is read by the
  next agent as a statement of intent. This repository has three dated instances of a stale
  statement costing real work, each read at source: `roadmap.md:125-129` listing audit
  `ip_address`/`user_agent` as dormant when both had shipped (the paragraph that adopted seeds,
  `.claude/rules/seeds.md`, and S-020); `data-model.md`'s "auto-created with new clans" (S-010);
  and a `Not verified` row claiming no dated restore drill existed when `docs/ops/backup-restore.md`
  already carried one from 2026-07-12 (S-021). This ADR becomes the record instead, and an ADR is a
  place that is read on purpose.
- S-017 and S-018 each become one reversible migration with no behaviour change, which is the
  smallest a seed can honestly be.

### What this does not buy, stated plainly

- **No response changes and no behaviour changes.** Nobody could observe these columns before and
  nobody can after. Anyone measuring "did this change an API" will correctly find that it did not.
- **It does not make any tree private that was not private already**, and it does not make one
  public. Every tree route already requires an authenticated caller, a validated approved
  membership, and at least `viewer` (`app/api/v1/tree.py:35-38`). That was the only rule before and
  it is the only rule after.
- **A person's avatar stays anonymously fetchable, and no privacy level would have covered it.**
  ADR-036 is explicit, at `036-public-avatar-urls.md:142-143, 152, 155`: "Member photographs
  become retrievable by anyone holding the URL, without authentication, regardless of clan", the
  URL "is guessable to anyone who learns a clan id and a person id, both of which appear in
  ordinary API responses to any member of that clan", and "Deleting the document does not revoke
  the URL." So the product already has one
  anonymous surface. `allow_public_tree` would have been the second, not the first, and whoever
  builds the concept has to decide what a privacy level means for a URL that is already public.
- **The clan export is the other place clan data leaves whole.** `GET /exports/clan` is admin-only
  (`exports.py:22-31`), and its query port returns raw `SELECT *` rows
  (`export_query_port.py:38`), so `phone` and `email` ride out unredacted. That is consistent with
  § (b) above — admins see PII anyway — but a future privacy level has to say whether it touches
  the archive.
- **The dead table is not cleaned up** (§ 5).

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| **Enforce both before any screen exposes them** (the seed's option 1) | It is not one change. It is a row creator that survives Measurement 5 case A, a public read path, a clan resolution that does not come from membership (Measurement 6), a redaction rule for a caller with no role, and a decision about what `private` means (Measurement 4). That is a milestone, not a seed, and nothing shipping needs it |
| **Keep both and note them in a contract** (the seed's option 3) | The note would protect against a client rendering a toggle for a field **no API returns** — and Measurement 2(c) shows no client names the concept in any of the ten locale files. It buys nothing that is not already true, leaves the trap in the schema, and adds a second place to record the same fact, which the seeds rule calls a second place to be wrong. It is also hard to write: `rest-clans-api.md` has no clan-settings shape to attach it to, and its one existing "clan settings" sentence means something else (§ 5) |
| **Keep `privacy_level`, drop `allow_public_tree`** | The nearest miss, and the leading candidate until Measurement 4. Keeping the more expressive column saves no work on return — a constrained enum column is one migration either way — while keeping exactly the defect § 2 describes: an unconstrained `String(20)` whose documented domain includes one value that duplicates another column and one that nobody has defined. If it must be re-typed on return, it can be re-added on return |
| **Keep `allow_public_tree`, drop `privacy_level`** | Strictly worse. It keeps the *less* expressive column, and it is the exact switch the design spec refuses by name |
| **Keep both and add a `CHECK` constraint now** | It closes the domain and nothing else. There is still no reader, no writer, no row, and no enforcement point, so it produces a better-typed dead column and a migration that must be written again when the real domain is decided |
| **Create the row now, so a future reader has something to read** | Measurement 5 case A: the obvious creator is rejected by the live policy. § 3: the row would carry a `max_upload_size_mb` that contradicts the enforced limit, and would activate a RESTRICT blocker. All cost, no reader |
| **Drop the whole `clan_settings` table** | Out of scope (§ 5). `max_upload_size_mb` is named out of scope by the seed and the other four columns were not examined by it. The finding is handed over instead |
| **Leave it alone and write a `Not verified` row** | The facts are verified, not unverified. Six measurements above are dated and re-runnable. There is nothing to defer |

## What this ADR deliberately does not decide

- **Whether FamilyRoots ever ships public trees.** It decides that v1 does not, and that the
  concept returns as one column on § 2's terms. It takes no position on the product question.
- **What `private` should mean.** Measurement 4 records that nobody has decided. Deciding it is
  part of the change that brings the column back, not part of dropping it.
- **`clan_settings.max_upload_size_mb`**, named out of scope by S-016 and already documented as
  dead at `app/core/config.py:126-127`.
- **The other four unread columns, and the fate of the table itself** (§ 5).
- **The two documents that promise the feature** (§ 5). They are named, not edited: this seed owns
  one file.
- **Field-level visibility**, which is seed S-053 and ADR-049. It is a different question — which
  *fields* of a person a member sees, not who may read the clan at all.
- **The RLS policy on `clan_settings`.** Migration `035` is untouched. § 4 says why it is not the
  enforcement point; it does not argue for removing it.

## Related

- Seed **S-016** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seeds **S-017** and
  **S-018**, which carry one column each.
- Seed **S-010**, which found the empty-table precondition and measured on `user_clan_roles` the
  clan-less write failure that Measurement 5 reproduces for `clan_settings`.
- Seed **S-020**, whose own false absence claim is the reason Measurement 2 exists.
- [ADR-008](008-rls-defense-in-depth.md) and migration `035_rls_clan_settings` — the policy this
  table carries, and § 4 on why it is not an authorization layer.
- [ADR-009](009-clan-deletion-restrict.md) — the RESTRICT foreign key a settings row would activate.
- [ADR-027](027-doi-single-authority.md) — the single-authority rule that § 1 applies to two
  columns instead of two đời computations.
- [ADR-036](036-public-avatar-urls.md) — the one anonymous surface the product already has.
- [ADR-039](039-clan-user-list-identity-asymmetry.md) — the graded field exposure in Measurement 2.
- [ADR-048](048-invitation-accept-runs-on-the-system-session.md) — the precedent for a route with
  one layer of clan isolation, stated plainly, which is what a public tree route would be.
- [`../superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
  §7.10d and §9-J21 — the design rule this decision obeys, and §9-J22 for the matrix defect in § 5.
- [`../architecture/multi-tenancy.md`](../architecture/multi-tenancy.md) and
  [`../architecture/rbac.md`](../architecture/rbac.md) — who may read a clan's tree today, and the
  matrix that has no fifth column.
