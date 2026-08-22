# ADR-049: Contact PII Is the Whole of Field-Level Visibility in v1, the Set Stays Fixed at `phone` and `email`, and the Contract Says So

## Status

Accepted (2026-08-22), by seed **S-053**. **No code changes.** The whole diff is this file, one
new section in [`../contracts/rest-persons-api.md`](../contracts/rest-persons-api.md), and one
index row handed to the coordinator. The seed's `Verification` field says a "keep it fixed" answer
runs no gate, so **no gate was run for the decision**. Two measurements below did run the backend
suite, and they are reported with their dates because they are evidence, not a gate.

Every measurement below was taken on **2026-08-22** in
`.claude/worktrees/design`, at commit `8e137a1`.

## Context

### The question, in one sentence

A field-level visibility rule already ships. It covers exactly two fields, it is hardcoded, and it
is keyed on role plus self. Is two fields, fixed, the right v1 answer, or should the set be
per-clan configurable, or simply larger?

### The correction this ADR is built on

Seed S-020 recorded on 2026-08-13 that field-level visibility "returned no implementation". That
is false, and the reason it is false is worth keeping. S-020 searched for
`field_visibility|visible_fields`, which are column names nobody ever chose. The rule ships as a
tuple constant and a function, so a name search could not see it. **An absence claim built on a
name search is a claim about names, not about behaviour.** ADR-044 Measurement 2 records the same
correction from the other side.

### Measurement 1 — what ships today, read at source

| Source | What it says |
|---|---|
| `backend/app/application/person/handlers.py:31` | `_PII_FIELDS = ("phone", "email")` |
| `:32` | `_ADMIN_ROLE = "admin"` |
| `:48` | `if viewer_role == _ADMIN_ROLE: return` |
| `:49` | `own_person_id = await repo.get_linked_person_id(viewer_user_id)` |
| `:50-54` | for every person that is not `own_person_id`, `setattr(person, field, None)` for each field in `_PII_FIELDS` |
| `:148-150` | the same helper runs on the `PATCH` response |
| `:230-241` | `PersonQueryHandler.redact_pii`, the read-path entry point, delegates to the same helper |
| `backend/app/api/v1/persons.py:126, 267, 337` | the three route call sites: list, batch, get-by-id |

The rule's origin is an owner decision, recorded in the commit that introduced it,
`8dbf159` (2026-07-05):

> Owner decision: within a clan, phone/email are visible only to an admin or the person
> themselves; every other member sees them nulled. Genealogy content (names, dates, places,
> lineage, bio, occupation, …) stays visible to all members — a genealogy tree is meant to be
> shared; only contact details are gated.

### Measurement 2 — the same two-field line is drawn three times, by three independent constants, and all three agree

This is the strongest argument for the set being right, and it was measured rather than asserted:

```
$ date
Sat Aug 22 13:51:21 +07 2026
$ cd backend && uv run python -c "..."
updatable 28
submittable 26
updatable - submittable = ['email', 'phone']
_PII_FIELDS = ('phone', 'email')
EXCLUDED = ['email', 'phone']
all three agree: True
```

The three constants are written in three layers by three different changes:

| Constant | Source | Question it answers |
|---|---|---|
| `_UPDATABLE_FIELDS` (28) | `backend/app/domain/person/entity.py:28-59` | which fields of the aggregate a client may write at all |
| `SUBMITTABLE_PERSON_FIELDS` (26) | `backend/app/domain/change_request/person_changes.py:38-67` | which fields a change request may propose |
| `EXCLUDED_PERSON_FIELDS` | `:71` | the exclusion, kept explicit so a pinning test can assert it is deliberate |
| `_PII_FIELDS` | `backend/app/application/person/handlers.py:31` | which fields a read redacts |

`_UPDATABLE_FIELDS` minus `SUBMITTABLE_PERSON_FIELDS` is exactly `{email, phone}`, and that is
exactly `_PII_FIELDS` and exactly `EXCLUDED_PERSON_FIELDS`. **Three people drew the line between
contact information and gia phả content, independently, and drew it in the same place.** That is
the fact this ADR rests on.

### Measurement 3 — every surface that can return a person's `phone` or `email`, enumerated

The question "is the set right" is only answerable if the reach of the set is known. Two searches
bound it.

```
$ grep -rn "^    phone\|^    email" backend/app/schemas/person.py
backend/app/schemas/person.py:59:    phone: str | None = Field(None, max_length=50)     # PersonCreateRequest
backend/app/schemas/person.py:60:    email: str | None = Field(None, max_length=255)   # PersonCreateRequest
backend/app/schemas/person.py:117:    phone: str | None = Field(None, max_length=50)    # PersonChangeFields
backend/app/schemas/person.py:118:    email: str | None = Field(None, max_length=255)   # PersonChangeFields
backend/app/schemas/person.py:224:    phone: str | None = None                          # PersonResponse
backend/app/schemas/person.py:225:    email: str | None = None                          # PersonResponse

$ grep -rln "PersonResponse" backend/app
backend/app/api/v1/persons.py
backend/app/schemas/person.py
backend/app/application/person/handlers.py
```

Two of the six hits are request shapes. **`PersonResponse` is the only response projection in the
backend that declares either field**, and it is referenced from exactly two modules. Every other
person projection was read and carries neither: `PersonMini` (`:248-263`), `PersonSummary`
(`:266-287`), `PersonDetail` (`:290-298`), `PersonSearchResult` (`:317-328`).

So the reach is five routes plus one archive:

| Surface | Guard | Redacted |
|---|---|---|
| `GET /persons` | `RequireViewer` (`persons.py:94`) | yes, `:126` |
| `GET /persons/{id}` | `RequireViewer` (`:317`) | yes, `:337` |
| `POST /persons/batch` | `RequireViewer` | yes, `:267` |
| `PATCH /persons/{id}` | `RequireViewer` (`:362`) | yes, in the handler at `handlers.py:148` |
| `POST /persons` | `RequireEditor` (`:196`) | **no, deliberately**: the response echoes values the creator just sent (commit `8605043`) |
| `GET /exports/clan` | `RequireAdmin` (`exports.py:30`) | **no**: `export_query_port.py:35-47` opens `SELECT p.*` at `:38`, so both fields ride out whole |

Two near misses, both checked rather than assumed. `POST /persons/{id}/restore` is decorated
`responses=ok(PersonResponse)` (`:398`) but returns `{"data": {"message": ..., "id": ...}}`
(`:414`), so no person field reaches the wire. `GET /persons/search` returns
`PersonSearchResult`, which has no contact field.

The export is not a gap this ADR closes. It is admin-only, admins see contact details anyway, and
the design spec already requires the download to warn about it in Vietnamese
(`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:2048-2053`), with the contract
carrying the same note at `docs/contracts/rest-exports-api.md:48-49`.

That contract also asks this ADR a direct question, at `rest-exports-api.md:52-54`: "There is no
field-level redaction or opt-out — if this changes (e.g. a future non-admin export audience), that
needs a new ADR, not a silent contract change here." **The answer is no.** ADR-049 does not change
the export, and there is no non-admin export audience.

### Measurement 4 — the failure direction, checked at both layers, and it is closed

The seed requires this ADR to name the failure direction and to verify at source whether the
shipping code closes it. **It does, at two independent layers.**

**Layer 1, the authorization gate, refuses an unresolvable role outright.** `require_role`
(`backend/app/core/permissions.py:41-68`) reads the caller's `user_clan_roles` row for the active
clan and:

- `:57-58` — no row, or `is_approved` false, raises `ForbiddenError("no_approved_clan_membership")`.
- `:60-63` — a stored role string outside `{admin, editor, viewer}` raises
  `ForbiddenError("invalid_role_assignment")`, because `ClanRole(row.role)` raises `ValueError`.

So a role that cannot be resolved does not reach the redaction function at all. The request is
refused. There is no super-admin bypass in this path: `grep -rn "super_admin"` over
`core/security.py` and `core/permissions.py` returns only `get_super_admin` (`security.py:211-220`),
a separate dependency, and Measurement 3 shows no platform-admin route serializes a
`PersonResponse`.

**Layer 2, the redaction itself, puts revealing behind the guard and redacting on the default path.** `handlers.py:48` reads
`if viewer_role == _ADMIN_ROLE: return`. Revealing requires a positive match on the exact string
`"admin"`. Redaction is the fall-through. Any other value, including an empty string, an unexpected
role name, or a future fourth role nobody remembered to classify, takes the redacting branch.
**That is the correct direction and it is not an accident**: commit `8605043` says the literal was
named `_ADMIN_ROLE` in order "to harden the string compare".

This ADR pins that direction as a term rather than leaving it as an implementation detail
(§ 3 below).

### Measurement 5 — the redaction is real, and no test proves any route performs it

This is the finding that changes what this ADR has to say, so it was measured rather than argued.

The seed states that `backend/tests/integration/test_person_pii_visibility.py` "proves both sides
end to end". Read at source, **it proves the function, not the route.** The test calls the
redaction itself, at `:74`, `:79`, and `:84`:

```
    other = await handler.get(GetPerson(person_id=target, clan_id=clan_id))
    assert other.phone == "0900000000"  # present before redaction
    await handler.redact_pii([other], viewer_role="viewer", viewer_user_id=viewer_id)
    assert other.phone is None and other.email is None
```

No HTTP request is issued. The same is true of every other PII test:
`backend/tests/unit/application/test_person_pii_visibility.py` calls `redact_pii` directly at
`:51, 59, 66, 73, 80`, and `backend/tests/unit/domain/test_person_handlers.py:84` and `:111` exercise the
command handler. The two route-level suites replace the call with a no-op fake:
`backend/tests/test_persons.py:60` and `backend/tests/unit/api/test_persons_batch_endpoint.py:85-86`.

So the three call sites at `persons.py:126, 267, 337` are the load-bearing part of the rule and
nothing tests them. That is a prediction, so it was tested by planting the failure, per
`.claude/rules/seeds.md` § "Two questions that catch it":

```
### BASELINE, unmodified tree
$ date
Sat Aug 22 13:55:34 +07 2026
$ TEST_PG_DB_NAME=familyroots_test_s053 uv run pytest -q
1351 passed in 60.06s (0:01:00)

### DEFECT PLANTED: persons.py:337-339 deleted, so GET /persons/{id} no longer redacts
$ git diff --stat
 backend/app/api/v1/persons.py | 3 ---
 1 file changed, 3 deletions(-)
$ date
Sat Aug 22 13:56:46 +07 2026
$ TEST_PG_DB_NAME=familyroots_test_s053 uv run pytest -q
1351 passed in 59.21s
$ uvx ruff check .
All checks passed!

### RESTORED
$ git checkout -- backend/app/api/v1/persons.py
$ date
Sat Aug 22 13:57:56 +07 2026
```

**Deleting the redaction from `GET /persons/{id}` changes no test result and no lint result.** The
defect was then reverted with `git checkout --`, and the section of `persons.py` was re-read to
confirm the call is back.

This is the exact shape `.claude/rules/seeds.md` § "A test pins an outcome, not a setting" was
adopted for, and it is a fourth instance of it. The suite asserts that a function redacts, which is
a fact the function's own body guarantees. It does not assert the outcome anyone cares about, which
is that **the response body a route sends contains no stranger's phone number.**

Two things this finding is **not**, stated so it is not overstated:

- **It is not a live leak.** All three call sites are present and correct on `main` at `8e137a1`,
  read at source in Measurement 3. Nothing is disclosed today.
- **It is not a claim that the redaction logic is untested.** Eight cases cover it: five in
  `tests/unit/application/test_person_pii_visibility.py` (`:49, 55, 63, 71, 77`), two in
  `tests/unit/domain/test_person_handlers.py` (`:84, 111`), and one against a real database in
  `tests/integration/test_person_pii_visibility.py:48`. They are good tests of the function. The gap is the wiring, and it is one
  `await` line per route away from silence.

### Measurement 6 — what a per-clan field set would have to land on, re-run today

The seed's second option is a per-clan configurable set. That lands on `clan_settings`, which is
ADR-044's territory, so its precondition was re-run rather than quoted forward.

```
$ date
Sat Aug 22 13:51:21 +07 2026
$ grep -rn "ClanSettings(" backend/app
backend/app/models/clan_settings.py:13:class ClanSettings(TimestampMixin, Base):
```

One hit, the class statement. Nothing constructs the object. ADR-044 Measurement 3 found the same
thing about all seven data columns and concluded, at
`044-privacy-toggles-dropped-from-v1.md:122`: "**So `clan_settings` is not a live table with two
dormant columns. It is a dead table**". ADR-044 § 3 then decided that **nothing creates a
`clan_settings` row and after that ADR nothing should**, and its Measurement 5 case A showed why the
obvious creator does not work: an insert during clan creation runs on the clan-less register
session and is rejected by migration `035`'s `WITH CHECK` with "new row violates row-level security
policy".

ADR-044 also named this decision as explicitly not its own, at
`044-privacy-toggles-dropped-from-v1.md:396`: "**Field-level visibility**, which is seed S-053 and
ADR-049. It is a different question — which *fields* of a person a member sees, not who may read
the clan at all."

### Measurement 7 — the fields a reader might want added, each answered at source

| Candidate | Where it is today | Why it is not contact PII |
|---|---|---|
| `residence_place` | `person_changes.py:58`, inside `SUBMITTABLE_PERSON_FIELDS` | It is a place, and where a branch settled is gia phả content that relatives correct. It is proposable by design |
| `biography`, `notes` | `:64-65`, submittable | Free text a member may already write about a relative. Hiding it from members removes the thing the product is for |
| `religion`, `nationality`, `occupation`, `education_level`, `title_rank` | `:59-63`, submittable | Biography, and the owner decision at commit `8dbf159` names `occupation` by example as content that stays visible |
| `avatar_url` | absent from every whitelist (ADR-036) | **The sharpest case, and it is the argument against extending.** ADR-036 says at `036-public-avatar-urls.md:142-144, 152-153`: "**Member photographs become retrievable by anyone holding the URL, without authentication, regardless of clan.**… The URL is guessable to anyone who learns a clan id and a person id, both of which appear in ordinary API responses to any member of that clan." Nulling it in a response would hide a value that any member can already fetch anonymously. That is a control that restricts nothing |

The design spec's rule about controls that restrict nothing is at
`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:2400-2402`, quoted in ADR-044 § "The
rule this decision has to obey":

> A privacy toggle that does not restrict anything is the most harmful control in this product — a
> trưởng họ could set `riêng tư` and reasonably believe the tree is private. None of them ship until
> enforcement does.

### Measurement 8 — the contract does not mention the rule, and `L11` names nothing

Two documentation defects, both confirmed today.

**(a) The persons contract is silent.** `docs/contracts/rest-persons-api.md` was read in full at
`8e137a1`, all 177 lines, before this change added to it. It documents the envelope, the edge-visibility rule, `avatar_url`, and optimistic
concurrency. It never says that `phone` or `email` can come back `null` because of who is asking.
**A client today cannot tell a redacted `phone` from a person who has no phone number**, because
both are JSON `null`.

**(b) `L11` is a dangling citation.** Six files cite it as the authority for this rule:

```
$ grep -rln "L11" .
backend/app/application/person/handlers.py
backend/tests/unit/api/test_persons_batch_endpoint.py
backend/tests/unit/application/test_person_pii_visibility.py
backend/tests/unit/domain/test_person_handlers.py
backend/tests/integration/test_person_pii_visibility.py
docs/decisions/037-change-requests-workflow.md
```

**Nothing in the repository defines `L11`.** All six are citing sites. `git log -S"L11"` shows it
entered with commit `8dbf159` on 2026-07-05, where it is a label from a review list that was never
committed. ADR-037 § 7 (`037-change-requests-workflow.md:191`) cites it too, so an ADR rests on it.
This is the citation defect that passes every mechanical check: the pointer resolves, because the
files exist, and it fails, because none of them holds the claim.

## Decision

### 1. The field set is fixed at `phone` and `email`, and v1 does not make it configurable

The set stays exactly `_PII_FIELDS = ("phone", "email")`. It is not per-clan, not per-person, not
per-branch, and not settable by any API.

The reason is Measurement 2. This is not a set somebody guessed at. It is the same partition of the
person aggregate that three separate changes arrived at independently, in three layers, and all
three agree exactly. The line is between **contact information about a living person** and
**gia phả content**, and every other writable column of `persons` falls on the content side
(Measurement 7).

**A configurable set would also be a control whose only reachable effect is to expose more.**
Measurement 6 shows every clan has no `clan_settings` row, so "no row" is the universal case. A
per-clan set therefore has to resolve "missing" to the maximal set, `{phone, email}`, or it ships
as total disclosure on day one. Once "missing" means maximal, the only thing an admin can do with
the control is remove a field from it. That is a switch labelled privacy whose sole function is to
publish contact details, which inverts what a trưởng họ would read it to mean.

### 2. The roles that see each field, stated exactly

Both fields carry the same rule. There is no per-field grading.

| Viewer | Sees `phone` and `email` of |
|---|---|
| `admin` of the active clan | every person in the clan |
| `editor` | their own linked person only |
| `viewer` | their own linked person only |
| anyone with no linked `user_profiles.person_id` | nobody, including themselves, because self cannot be resolved |
| a `super_admin` who is not also an `admin` of that clan | nobody. There is no platform bypass (Measurement 4) |

"Their own linked person" means `user_profiles.person_id` for the calling user, resolved once per
request by `repo.get_linked_person_id` (`handlers.py:49`).

Two carve-outs, both already shipped and both kept:

- **`POST /persons` does not redact its own response.** The creator supplied the values in the same
  request. Redacting them would hide the caller's own input from the caller.
- **Writes are governed separately, and more narrowly.** A `viewer` may write `phone` and `email`
  on their own linked person and on nobody else (`handlers.py:120-140`). Read visibility and write
  permission are two rules; this ADR owns the read one.

### 3. The failure direction is closed, and closed is now a term rather than an implementation detail

**An unresolvable viewer role redacts. It never reveals.** Measurement 4 verified this holds today
at both layers. This ADR makes it a term that a later change must preserve:

| Term | What it means |
|---|---|
| **Reveal is the guarded branch** | The code must test for a role that *may* see contact details and return early, exactly as `handlers.py:48` does. It must never test for a role that may not and redact inside that branch. A fourth role added tomorrow must default to redacted without anybody remembering to classify it |
| **An unresolvable role never reaches the redaction** | `require_role` refuses a missing membership, an unapproved one, or a role string outside the enum (`permissions.py:57-63`). A caller whose role cannot be established gets a 403, not a person |
| **A redacted field is `null`, and `null` is not a promise** | The wire carries no marker distinguishing "redacted" from "empty". § 4 makes that a stated contract term rather than an accident, and § 5 records what it costs |
| **Adding a field means changing both constants** | `_PII_FIELDS` and `EXCLUDED_PERSON_FIELDS` (Measurement 2) are separate constants that happen to agree. If a future change adds a third field to the read redaction and not to the change-request exclusion, the review queue republishes what the read path just hid. Whoever adds a field changes both, or writes down why not |

### 4. `docs/contracts/rest-persons-api.md` states the rule, in this change

The contract gains a section naming the two fields, the roles, the routes, and the one consequence
a client can actually trip over: **`null` is ambiguous by design.** A client must not render "no
phone number on file" from a `null`, and must not cache a `null` read by one viewer and serve it to
another. That is Measurement 8(a), closed here rather than deferred.

### 5. What is not decided here, and is handed over as a seed

Measurement 5 found that no test proves any route calls the redaction, and proved it by planting
the defect and watching 1351 tests stay green. **This ADR does not fix that**, because fixing it is
a build with its own gate and its own negative control, and `.claude/rules/seeds.md` forbids closing
two seeds in one pull request. The finding is handed to the coordinator as a proposed seed, with
the measurement above as its evidence.

The end state that seed needs is a test that **sends a request and reads the response body**, per
the rule's own table: a `viewer` calling `GET /persons/{id}` for a stranger reads `"phone": null`
out of the JSON, and an `admin` calling the same route reads the number. One case per route, four
routes.

## Consequences

### What this buys

- **The rule becomes readable by the people who have to obey it.** It shipped in July as a tuple
  constant, a helper, and a review label that names nothing (Measurement 8b). After this change a
  client developer reads it in the contract and a backend developer reads the reasoning here.
- **A `null` stops being a silent ambiguity.** It stays ambiguous on the wire, which is the correct
  design, but the ambiguity is now documented, so a client that renders "chưa có số điện thoại" from
  a `null` is a bug the contract catches rather than a surprise in production.
- **The two-constant coupling is written down before it breaks** (§ 3, last row). Today the two
  agree because one change wrote both. Nothing enforces it.
- **`clan_settings` gains no new reason to exist.** ADR-044 left it a dead table with five unread
  columns and handed the cleanup to the coordinator. A per-clan field set would have revived it as
  the first live consumer, and would have had to solve the row-creation problem ADR-044 measured and
  declined.

### What this does not buy, stated plainly

- **No behaviour changes, and no response changes.** Anyone measuring "did this change an API" will
  correctly find that it did not. Every field that was `null` before is `null` after, for the same
  callers.
- **It does not close the untested wiring** (§ 5). The gap Measurement 5 proved is real and stays
  open until that seed lands. Between now and then, the redaction rests on three lines that no test
  is watching.
- **It does not redact the clan archive.** `GET /exports/clan` returns both fields whole
  (Measurement 3). That is consistent, because the route is admin-only and an admin sees contact
  details anyway, but a reader looking for "where does PII leave this system" should find the export
  named here.
- **It does not repoint the six `L11` citations** (Measurement 8b), although it is the definition
  they were reaching for. Five are under `backend/`, so changing them is a code change with a gate,
  and that belongs with the seed in § 5. The sixth is ADR-037, which stays as written because prior
  ADRs are immutable here except for status updates.
- **It takes no position on whether FamilyRoots ever ships per-clan privacy.** It decides that v1
  does not, on the grounds in § 1.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| **Make the field set per-clan configurable** (the seed's option 2) | Four reasons, in order of weight. **(1)** It has no row to live in: `clan_settings` is a dead table (Measurement 6, ADR-044 Measurement 3), and ADR-044 § 3 decided nothing should create a row, having measured that the obvious creator is refused by migration `035`. **(2)** The failure direction cannot be made to help: "no row" is universal, so missing must resolve to the maximal set, and a control that can only ever be relaxed from maximal is a privacy switch whose sole function is to publish. **(3)** It is not single-agent-sized: a row creator on the right session, a value domain closed at the database, an admin endpoint, four locales, and a screen. ADR-044 called the identical shape "a milestone, not a seed". **(4)** Nothing asks for it: `grep` for the concept across `web/src`, `mobile/lib` and all ten locale files returned zero in ADR-044 Measurement 2(c) |
| **Extend the fixed set without making it configurable** (the seed's option 3) | There is no field to add. Measurement 2 shows three independent constants agree on where the line is, and Measurement 7 answers every plausible candidate at source. `avatar_url` is the one worth naming twice: ADR-036 made it anonymously fetchable, so redacting it in a response would restrict nothing, which is precisely the control the design spec forbids at `specs/2026-08-02-design-system-and-screens.md:2400-2402`. Adding a field with no protective effect is worse than adding none, because it reads to the next agent as evidence the field is protected |
| **Keep the rule fixed and say nothing** (do only the ADR) | Fails the seed's end state and leaves Measurement 8(a) standing. The contract is the file a client reads before rendering a person card, and it is the file that currently implies `phone` is simply a nullable string |
| **Add a `redacted: true` marker, or a per-field visibility map, to the response** | It converts a silent ambiguity into a precise disclosure. A marker tells any member exactly which relatives have a phone number on file, which is contact metadata about the same living people the rule exists to protect. It also breaks `PersonResponse` for every client to solve a problem no client has reported |
| **Return `403` instead of `null` when a viewer asks for a person with contact details** | Same disclosure, more expensive. A `403` on one person and a `200` on another is a per-person oracle, and it would break `GET /persons` and `POST /persons/batch`, where one page mixes persons the viewer may and may not see contact details for |
| **Move the redaction into the RLS policy so no route can forget it** (the fix Measurement 5 invites) | Wrong layer, for ADR-008's reason and ADR-044 § 4's. RLS decides which **rows** a session may see; this rule blanks two **columns** of a row the caller is entitled to read. Postgres has column privileges, but they are granted to a database role, and every request in this system runs as the one `familyroots_app` role whose only per-request variable is `app.clan_id` (ADR-047). There is no per-caller role to grant against |
| **Move the redaction into `PersonResponse` itself, so serialization cannot skip it** | The most attractive alternative to Measurement 5's finding, and it is out of scope here rather than wrong. It is a code change with a gate, it needs the viewer threaded into the schema layer, and § 5 hands the whole question to a seed with a measured failure to justify it. Deciding the mechanism before that seed measures the options would be this ADR guessing |
| **Write a `Not verified` row instead of an ADR** | The facts are verified. Eight dated, re-runnable measurements are above, two of them full suite runs |

## What this ADR deliberately does not decide

- **The mechanism that makes the rule impossible to bypass** (§ 5). It records that no test watches
  the three call sites, proves it, and hands the fix over.
- **Whether the clan archive should redact.** Named in Measurement 3 and in Consequences, decided
  nowhere. ADR-044's Consequences already flagged that a future privacy level would have to say
  whether it touches the archive; the same is true here.
- **`clan_settings` and its five remaining unread columns.** ADR-044 § 5 handed that to the
  coordinator and this ADR adds no claim on it.
- **Whether `phone` and `email` should be on `persons` at all**, rather than on the user account.
  It is a real question, it is a data-model question, and no source in this repository has asked it.
- **Write permissions.** § 2 names the read rule. The viewer self-edit whitelist
  (`handlers.py:120-140`) is a separate rule with a separate test, unchanged here.
- **Repointing the six `L11` citations** (Measurement 8b), which is a code change.

## Related

- Seed **S-053** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seed **S-020**, whose
  false absence claim is the reason this is a decision rather than a build.
- [ADR-044](044-privacy-toggles-dropped-from-v1.md) — the dead `clan_settings` table, the reason a
  per-clan set has nowhere to live, and the ADR that named this question and handed it here (`:396`).
- [ADR-037](037-change-requests-workflow.md) § 7 — the same two fields excluded from
  `SUBMITTABLE_PERSON_FIELDS`, so the review queue cannot republish what the read path hides.
- [ADR-039](039-clan-user-list-identity-asymmetry.md) — the other graded field exposure in this
  product: an account's `email` on the admin-only pending queue and never on the member list. A
  different `email` from this one, on a different table.
- [ADR-036](036-public-avatar-urls.md) — why `avatar_url` cannot be protected by redaction.
- [ADR-008](008-rls-defense-in-depth.md) and [ADR-047](047-rls-seam-sets-clan-id-only.md) — why RLS
  is not the enforcement point for a column-level rule.
- [`../contracts/rest-persons-api.md`](../contracts/rest-persons-api.md) — the contract section this
  ADR requires, landed in the same change.
- [`../contracts/rest-exports-api.md`](../contracts/rest-exports-api.md) § "PII note" and
  [`../contracts/rest-change-requests-api.md`](../contracts/rest-change-requests-api.md) `:93-94` —
  the two other contracts that already name these fields.
- [`../../.claude/rules/seeds.md`](../../.claude/rules/seeds.md) § "A test pins an outcome, not a
  setting" — the rule Measurement 5 is a fourth instance of.
