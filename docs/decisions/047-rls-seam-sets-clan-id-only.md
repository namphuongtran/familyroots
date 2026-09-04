# ADR-047: The RLS Seam Sets `app.clan_id` Only, and ADR-008's `app.user_id` Clause Is Corrected by Dated Amendment

## Status

Accepted (2026-08-22). **Nothing is shipped by this ADR.** It is a decision. The
whole diff is this file, a dated amendment inside
[ADR-008](008-rls-defense-in-depth.md), and one index row. **No gate was run, and that is
correct**: no code changed, so there is nothing a gate could measure. The verification
field permits this in the same words.

Every measurement below was taken on **2026-08-22** in the worktree
`.claude/worktrees/design`, at commit `7588fe7`, on branch `seed/s-040-adr-047-rls-gucs`.

## Context

### The question, in one sentence

ADR-008 says the request seam injects a clan **and a user**. The shipped seam injects a clan only.
Is the document wrong, or is the code missing a setting?

### The two sources, quoted

[ADR-008](008-rls-defense-in-depth.md) Decision § 2, at lines 149-150:

> **App-specific GUC context, not Supabase-native.** Inject the active clan/user
> per transaction with `SET LOCAL app.clan_id = …` / `SET LOCAL app.user_id = …`

`backend/app/core/rls.py:63-65`, the whole of what the seam issues:

```python
connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
clan = _request_clan_id.get() or ""
connection.exec_driver_sql("SELECT set_config('app.clan_id', %s, true)", (clan,))
```

The root `CLAUDE.md` rule is that when code and docs disagree, the code is the truth. So the only
question this ADR settles is whether to repair the document or to build the missing half.

### Measurement 1 — nothing anywhere writes `app.user_id`

```
$ grep -rn "app\.user_id" backend/ --include='*.py'
$ echo $?
1
```

Run 2026-08-22. No output, exit 1. The only occurrences of the string in the repository are in
prose that is *about* this disagreement:
`docs/decisions/042-identity-claims-app-layer-isolation-system-session-lockout.md:267-268`, and
`docs/decisions/008-rls-defense-in-depth.md:150` itself.

### Measurement 2 — nothing anywhere reads any GUC except `app.clan_id`

```
$ grep -rho "current_setting('[^']*'" backend/migrations/versions/*.py | sort | uniq -c
   6 current_setting('app.clan_id'
```

Run 2026-08-22. Six literal occurrences, every one of them `app.clan_id`, and no second GUC name
in any policy expression in the tree. They sit in five migrations:
`002_rls_documents_pilot.py:63-64` (two), `027_rls_events_branches.py:26`,
`028_rls_edges.py:30`, `029_rls_persons.py:44`, and `030_rls_change_requests.py:39`.

### Measurement 3 — the seam has two writers, not one, and the seed names only one

The opening citation is `backend/app/core/rls.py:63-65`. That is the `after_begin` writer. There is a
second one:

| Writer | Site | When it runs | What it writes |
|---|---|---|---|
| `after_begin` event on `RlsSession` | `backend/app/core/rls.py:63-65` | at the start of **every** transaction on a request session | `SET LOCAL ROLE` + `app.clan_id` from the ContextVar |
| `get_current_clan_id` | `backend/app/core/security.py:290` | once, mid-request, on the transaction that is **already open** | `app.clan_id` for the resolved clan |

The comment above the second one, at `security.py:285-289`, records why it exists: the transaction
"began (during auth) before the clan was known, so this same session's later queries must be
clan-scoped immediately". Neither writer touches `app.user_id`. The finding does not change the
answer, but a future seed that adds a GUC has **two** sites to change, not one, and this ADR is
where that is written down.

### Measurement 4 — the seam holds no user identity to inject

`backend/app/core/rls.py:35` declares one ContextVar, `_request_clan_id`. There is no user
equivalent, in that module or beside it. `set_request_clan_id` is called from exactly one place,
`backend/app/core/security.py:289`, and cleared on request teardown at
`backend/app/core/database.py:81-83`. Adding `app.user_id` is therefore not a one-line change to
`rls.py`. It is a second ContextVar, a second population site inside `get_current_user`
(`security.py:108`), a second clear on teardown, and a second write in each of the two writers
above.

### Measurement 5 — the line numbers other ADRs use to cite ADR-008 have already gone stale

The numbers in the opening citation were warned to move, and they did. The same is true of
the numbers in the ADRs. Checked on 2026-08-22 against ADR-008 **before** this ADR's amendment was
inserted:

| Citation, and where it is written | What ADR-008 actually holds at that line today |
|---|---|
| "ADR-008 line 135", ADR-042:267 | line 135 is the closing line of the Vietnamese summary, `rủi ro nhất, nên làm **pilot 1 bảng trước** rồi mở rộng.` |
| "at lines 100-107, “false security”", ADR-042:42 and again at ADR-042:286 | lines 100-107 are the "Not yet" paragraph. The words "false security" are at line 121 |
| "which ADR-008 lines 89-90 leaves until every table is covered", ADR-042:272 | lines 89-90 are Phase 5 prose. `FORCE ROW LEVEL SECURITY` is at lines 104-105 |
| "per ADR-008 lines 103-105", for the bypassing role, ADR-042:127 | lines 103-105 are the tree-function caveat and `FORCE`. The bypassing-role sentence is at lines 119-120 |
| "ADR-008 Phase 4 says the same at lines 56-59", ADR-042:36 | still correct |

Four of the five distinct claims resolve to a real line that does not hold them. That is the
failure mode which passes every mechanical link check: the pointer is valid, and the target is
wrong. They are not repaired here, because ADR-042 is not this seed's file and repairing them is a
separate change. The amendment this ADR inserts sits **below** all five spans, at ADR-008 line 156,
so it does not move any of them further.

**None of this was carelessness, and that is the point.** `ADR-008 line 135` was *correct* when
ADR-042 was written. Commit `634a0c5`, "feat(backend): enable clan-isolation RLS on change_requests
", dated 2026-08-22, added 16 lines to ADR-008 and removed 1 — a net shift of 15, which is
exactly `135 → 150`. `git show 634a0c5^:docs/decisions/008-rls-defense-in-depth.md | sed -n '135p'`
still prints the `app.user_id` clause, run 2026-08-22. Two seeds landing the same day were enough.

The durable lesson, for whoever writes the next ADR: **cite an ADR by its section, and treat the
line number as a hint.** ADR-008 § 2 does not move. `008:135` survived one working day.

## Decision

### 1. The shipped seam is correct as it stands. `app.user_id` is not added.

Option (b) is rejected. Five reasons, in increasing order of seriousness.

1. **Nothing would read it.** Measurement 2: no policy in the tree names a second GUC. A setting
   written on every request transaction and read by nothing is the dead-token defect the seed
   itself names, and it is the same shape as the "false security" warning that is the reason
   ADR-008 exists (ADR-008 lines 116-124).

2. **The one candidate table is out of scope, by this seed's own text and by an accepted ADR.**
   The table a user-keyed policy would key on is `identity_claims`, whose `user_id` column exists
   at `backend/app/models/identity_claim.py:27-31`. `identity_claims` is out of scope here and
   belongs to ADR-042, and
   [ADR-042](042-identity-claims-app-layer-isolation-system-session-lockout.md) lines 102-109
   already decided what policy that table gets: a deny-all tripwire,
   `identity_claims_system_session_only … USING (false) WITH CHECK (false)`. Choosing (b) would
   mean naming a policy that contradicts an ADR accepted the same day, on a table this seed
   forbids touching.

3. **The GUC would be invisible on the sessions that touch that table anyway.** ADR-042 Fact 1
   (its lines 25-41) establishes that both claim handlers are wired to `get_system_db`
   (`backend/app/infrastructure/dependencies.py:144` and `:149`), and `get_system_db`
   (`backend/app/core/database.py:86-93`) hands out `AsyncSessionLocal`, which has no RLS seam
   attached (`database.py:49-53`, and `register_rls_session_events` is applied only to
   `RlsSession` at `database.py:62`). A GUC set by the request seam is not set on those sessions.
   So the setting would be inert **and** absent exactly where it was wanted: two independent
   failures, not one.

4. **It does not finish the job it was wanted for.** ADR-042 lines 269-271 record the finding and
   its own limit: a user-keyed policy "would have been the one shape that fits `GET /m/claims`",
   and "it would still leave the admin queue unsolved". The four claim routes split
   (ADR-042 lines 45-58): two have no clan context, one is keyed on the reviewing admin's active
   clan, and one on the claimant's. One GUC does not cover that set. A user-keyed policy is half
   an answer to a table that needs a redesign, and ADR-042 lines 261-263 already say that
   redesign is its own ADR.

5. **`app.user_id` was never the load-bearing half of ADR-008 § 2.** Read § 2 whole: its subject
   is *app-specific GUCs rather than Supabase-native `request.jwt.claims`/`auth.uid()`*, so that
   the same policies run on plain Postgres and on Supabase. That argument shipped and is true.
   `app.user_id` was an example in a list, and every policy actually written since keys on clan,
   because clan is what this product isolates on (ADR-002).

### 2. ADR-008 is corrected by a dated amendment placed beside the wrong sentence

The correction is appended, not substituted. The 2026-06 sentence stays legible and a dated note
sits next to it saying what is true now, who decided, and where the evidence is. Three reasons for
that shape:

- **An ADR is a dated record.** `docs/decisions/README.md` says to "keep prior ADRs immutable
  except for Status updates". Deleting the clause would make the file look like it always
  described the shipped seam, and would erase the evidence that the seam was designed one way and
  built another. That erasure is the defect, not the stale sentence.
- **The repository already does this to this file.** ADR-008 lines 64-79 carry a "Phase 4
  follow-up (2026-08-02, ADR-038 — no migration)" note appended inside its Status section. The
  amendment below is the same move applied to a Decision clause.
- **The note goes beside § 2, not only in Status.** § 2 is the sentence an agent greps to and
  reads first, which is how this defect reached ADR-042 in the first place. A correction filed
  only in Status leaves the wrong sentence unmarked.

### 3. Why this clause is amended when ADR-043 declined to amend a neighbouring one

[ADR-043](043-audit-notification-rls-posture.md) lines 315-317 looked at ADR-008 § 1's promise of
"a separate privileged `SYSTEM_DATABASE_URL`", found it was never built, and chose to "note the
disagreement rather than editing an accepted ADR". That is not overturned here, and the two
choices are consistent:

- ADR-043 declined a **rewrite**. This ADR performs an **append**. Nothing in ADR-008 is deleted
  or reworded here, so the record ADR-043 was protecting is still intact after this change.
- The amendment was asked for in those exact terms: "a dated amendment, not a silent rewrite".
  ADR-043 asked for no such thing.

The `SYSTEM_DATABASE_URL` sentence is deliberately left alone. It is out of scope here,
ADR-043 owns it, and it is a different disagreement.

## What a later seed must establish before adding `app.user_id`

This is the half of the decision that is worth carrying forward. Any seed proposing the GUC must
show all five, in its own text, from source:

1. **A named table and a named column** the policy keys on, where the column is one the
   `familyroots_app` role can read.
2. **A reading path on a request session.** The handler must be wired to `get_db`
   (`database.py:73-83`), not `get_system_db`. Today no `identity_claims` handler is
   (`dependencies.py:144`, `:149`).
3. **A resolution point earlier than the query, or a mid-transaction re-apply.** The user id must
   be in the ContextVar before the transaction that needs it, or the seed must add the second
   writer the clan id already has at `security.py:290`, for the same reason.
4. **Both writers and the teardown clear.** `rls.py:63-65`, `security.py:290`, and
   `database.py:81-83`. Missing the third leaks a stale identity into a reused context.
5. **Stated fail-closed behaviour when the GUC is unset**, matching ADR-008 § 3: an unset value
   must mean zero rows, never all rows.

A seed that cannot show all five is proposing a dead token, and this ADR is the reason to say no.

## Consequences

Easier:

- ADR-008 § 2 and `backend/app/core/rls.py` now describe the same seam, so an agent who reads the
  ADR first does not build against a setting that does not exist.
- The next agent who wants a user-keyed policy has a checklist instead of a rediscovery.
- ADR-042's open finding is closed with an answer rather than left as a standing question.

Harder:

- **Nothing mechanically stops this drifting again.** The seam's test,
  `backend/tests/integration/test_rls_activation.py:70-84`, asserts that `current_user` is
  `familyroots_app` and that `app.clan_id` holds the right value. It does not assert that the seam
  sets *nothing else*, and no test compares the seam against ADR-008's prose. A guard is possible
  and is named as a follow-up below; it is not built here, because building it means touching
  `backend/**` and this seed is documentation only.
- ADR-008's Decision section now carries an inline amendment, so it must be read to the end of the
  clause rather than skimmed. That cost is accepted; the alternative is a sentence that is wrong.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Delete `/ SET LOCAL app.user_id = …` from ADR-008 § 2 | It is a silent rewrite. The file would then claim it always described the shipped seam, and the evidence that design and build diverged is gone |
| Add the GUC now and let a later change find a reader | The dead-token defect, and it pre-empts a decision ADR-042 says needs its own redesign ADR |
| Add the GUC and key a policy on `identity_claims.user_id` | Contradicts ADR-042 lines 102-109, which ADR-042 is already committed to, and touches a table out of scope here |
| Record the disagreement only in this ADR, leaving ADR-008 untouched, as ADR-043 did for `SYSTEM_DATABASE_URL` | It leaves the wrong sentence unmarked in the file an agent reads first, which is precisely how this reached ADR-042. This ADR asks for the amendment; ADR-043 did not |
| Put the rule in `.claude/rules/` so every session loads it | Ruled out: this is a decision about one seam, and decisions live in ADRs. A rules file loaded in every session is the wrong home for a fact about one module |

## What this ADR deliberately does not decide

- **Any new policy**, on any table. Out of scope here.
- **`identity_claims`.** ADR-042 decided it and its migration builds it.
- **Whether the identity-claim flow should be clan-scoped**, which ADR-042 lines 261-263 already
  reserve for a redesign ADR of its own.
- **ADR-008 § 1's `SYSTEM_DATABASE_URL` sentence.** A different disagreement, recorded by ADR-043
  lines 25-29 and left open by ADR-043 lines 315-317. Out of scope here.
- **`FORCE ROW LEVEL SECURITY`**, which ADR-008 lines 104-105 leaves until every table is covered.
- **Whether a guard test should assert the exact set of settings the seam applies.** It is worth
  building and it is not built here, because it is `backend/**` work and this seed is documentation
  only. Proposed as follow-up work.

## Related

- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md) — the ADR
  this one amends. § 2 at lines 149-150 is the corrected clause; § 3 is the fail-closed rule that
  precondition 5 above preserves.
- [ADR-042: `identity_claims` Keeps Application-Layer Clan Isolation](042-identity-claims-app-layer-isolation-system-session-lockout.md) —
  raised this finding at its lines 267-271 and deferred it to a seed. That deferral ends here.
- [ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies](043-audit-notification-rls-posture.md) —
  the neighbouring ADR-008 disagreement, and the precedent § 3 above reconciles with.
- [ADR-002: Single Schema Clan-Scoped Multitenancy](002-clan-scoped-multitenancy.md) — why every
  shipped policy keys on clan and none keys on user.
