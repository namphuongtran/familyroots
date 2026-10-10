# ADR-059: `user_profiles` and `user_fcm_tokens` Are User-Owned and Stay Outside Layer 2

## Status

Accepted (2026-10-04). Resolves issue #160, "The RLS posture for user_profiles and user_fcm_tokens,
which no ADR decides", on the map in issue #158. The maintainer chose every option below in a
grilling session on 2026-10-04.

> **Amendment (2026-10-04, issue #169):** the third clause of § 2 is now enforced. The veto in
> `test_the_not_clan_owned_list_names_only_tables_the_schema_agrees_are_global` follows chains of
> NOT NULL foreign keys to any depth, read from `pg_constraint` and `pg_attribute.attnotnull`, and
> refuses an exemption for any table whose chain ends at a table with a `*clan_id` column or a
> foreign key to `clans`. A MATCH FULL key with one NOT NULL column counts as a NOT NULL link,
> because MATCH FULL refuses a row that mixes NULL and non-NULL key values. Two negative controls
> stay in the suite and run the gate's own body.
> `test_the_exemption_veto_refuses_a_table_whose_not_null_chain_reaches_a_clan` plants a table with
> a NOT NULL `person_id` and a grandchild behind it, must see both refused, then makes the link
> nullable and must see them pass.
> `test_the_exemption_veto_follows_a_match_full_key_that_one_not_null_column_binds` does the same
> for a MATCH FULL key and its MATCH SIMPLE twin. The sentences below that call the clause prose,
> or owed to #169, describe the state before this amendment.

> **Amendment (2026-10-10, issue #251): § 5's second event fired, and
> [ADR-066](066-the-application-database-lives-in-the-supabase-project.md) answers it.** On
> 2026-10-10 the maintainer moved the application database into the Supabase project. So the § Context
> paragraph "The production application database is not the Supabase database" describes the state
> before this amendment.
>
> **The answer is a grant, not a policy.** Migration `042` revokes everything `anon` and
> `authenticated` hold in `public`, on tables, sequences and routines, and in the login's default
> privileges. Removing `public` from the Data API's exposed schemas is the second lock.
>
> **§ 3's posture and § 4's accepted risk stand unchanged for the request role**: both tables stay
> outside layer 2, and `familyroots_app` can still read every row. The Data API, which § 5 feared,
> holds nothing on them. § 5's first event, `app.user_id`, is untouched and still reopens this.
>
> **§ 5 item 2 understated the exposure.** It said the clan-keyed tables would fail closed and these
> two would not. No policy in the chain names a role, so every policy applies to `anon`. Three of
> them do not read `app.clan_id`: `user_clan_roles_sel`, `user_clan_roles_ins` and `audit_logs_ins`.
> Measured on a fresh `supabase/postgres:17.6.1.084` with the chain stopped before `042`, `anon` with
> no clan GUC did two things:
>
> - it read `user_profiles.email`;
> - it inserted an approved `admin` row into `user_clan_roles`.
>
> After `042`, both answer `permission denied for table`. ADR-066 § Context has the readings.

**This ADR ships no runtime code.** The diff is this file, its index row, a glossary, and citation
edits in three places that named this decision as owed: the two reason strings in
`_NOT_CLAN_OWNED_TABLES`, `docs/architecture/multi-tenancy.md`, and `docs/ops/local-supabase.md`.
The reason strings live in `backend/tests/**`, so the backend full quality gate applies, even though
no assertion changed.

Every reading below was taken on **2026-10-04** at commit `ac1823d` on `main`. Where a line number
is given, the claim was read at that line. Per ADR-047's lesson, cite this ADR by section and treat
its line numbers as hints.

## Context

### The question, in one sentence

The RLS coverage gate exempts four tables from clan scope, and for two of them its own reason string
says "NO ADR DECIDES THIS". Are those two tables outside clan scope, or uncovered?

### Why the exemption list needs a written rule

The gate, `test_every_clan_owned_table_is_covered_by_exactly_one_of_the_four_postures`
(`backend/tests/integration/test_rls_activation.py:547`), reads every table in `public` from the
catalog and treats each table as clan-owned **unless** `_NOT_CLAN_OWNED_TABLES` (`:311`) names it.
So the hand-written list is what defines "clan-owned". `.claude/rules/testing.md` names that exact
failure: "A set is a setting too." An exemption with no rule behind it pins the list, not the
coverage.

### The two tables, read at source

| | `user_profiles` | `user_fcm_tokens` |
|---|---|---|
| Owner | an auth user: `id` is the Supabase user id | a user: `user_id` NOT NULL, FK to `user_profiles` (`app/models/user_fcm_token.py:22`) |
| Path to a clan | only `person_id`, **nullable**, `ON DELETE SET NULL` (`001_initial.py:560-565`, `app/models/user_profile.py:36-41`) | none |
| PII | `email` (NOT NULL, UNIQUE), `display_name`, `avatar_url`; also `platform_role` and `person_id` | `token`: whoever holds it can address pushes to that device |
| RLS | off | off |
| Request-role grant | full CRUD, from the blanket grant in `002_rls_documents_pilot.py:44-50` | full CRUD, from the default privileges in the same migration |

**How `user_profiles` is reached:**

- **The caller's own row, keyed on the JWT `sub`, on the request session.** This covers
  `get_current_user` and `ensure_user_profile` (`app/core/security.py:108-203`), which run on every
  authenticated route; `GET /auth/me`; login; and `get_linked_person_id`
  (`app/infrastructure/persistence/person_repository.py:99-103`).
- **Other users, filtered by clan, on the request session.** `list_users` joins it through
  `user_clan_roles` for the current clan (`app/infrastructure/persistence/clan_repository.py:61-91`).
  ADR-039 decides which of those fields each list returns.
- **Other users, keyed on `person_id`, on the system session.** The claims flow
  (`app/infrastructure/persistence/claim_repository.py:26-27`, `:60-64`).
- **Before any clan exists.** `POST /auth/register` (ADR-058) and login, with `app.clan_id` empty.
- **Every approved member of a clan, on the privileged scheduler connection**
  (`app/services/notification.py:123-136`).

**How `user_fcm_tokens` is reached:**

- On the request session, two writes:
  - the upsert `INSERT … ON CONFLICT (token) DO UPDATE SET user_id = :user_id`
    (`app/infrastructure/persistence/auth_repository.py:162-171`). It moves a token to whoever
    registers it last, by design (`004_fcm_tokens.py:39-40`);
  - `DELETE … WHERE user_id = :user_id AND token = :token` (`:173-177`).
- Every read happens on the privileged scheduler connection (`app/services/notification.py:123-136`).

**The production application database is not the Supabase database.**
`docs/ops/local-supabase.md:12-24` says the application tables live in Render-managed Postgres, and
the Supabase project owns only `auth.*` and Storage. So neither table is reachable through the
Supabase Data API today.

## Decision

### 1. Both tables are user-owned, not clan-owned

A **user-owned** record belongs to an account. The account exists before any clan (ADR-058: a user
may register with no clan) and may belong to several clans. A **clan-owned** record belongs to
exactly one clan, and that clan decides whether the record lives and who sees it. `CONTEXT.md`
defines both terms.

One scenario settles it. A user's profile links to a person in clan A, and the user is also an
approved member of clan B. Clan A deletes that person. `person_id` is set to NULL and the profile
survives, still serving clan B. A clan that does not decide whether a row lives does not own the
row. A push token follows the device and the user, never a clan.

### 2. The rule for naming a table not-clan-owned

> **A table may be named not-clan-owned only if no row can reach a clan except through a nullable
> link: no column whose name ends in `clan_id`, no foreign key to `clans`, and no chain of NOT NULL
> foreign keys ending at a table that has either.**

This is a condition for **exemption**, not a definition of "clan-owned", and the difference
matters. "Every row reaches exactly one clan through a NOT NULL path" was proposed first and is
wrong: it would push `audit_logs` out of clan scope, because `audit_logs.clan_id` is nullable by
decision (ADR-043 § 4). The gate keeps the strict default. A table is clan-owned unless this rule
lets it out.

Applied to the schema at `ac1823d`:

| Table | Verdict | Why |
|---|---|---|
| `alembic_version` | may be exempt | no link of any kind |
| `clans` | may be exempt | it is the tenant; ADR-008 keeps it outside layer 2 |
| `user_profiles` | may be exempt | its only path is the nullable `person_id` |
| `user_fcm_tokens` | may be exempt | its NOT NULL `user_id` ends at `user_profiles`, which has no clan column or FK to `clans` |
| `identity_claims` | in scope | `person_id` is NOT NULL (`001_initial.py:732-736`) and ends at `persons`, which carries `created_by_clan_id` |
| `audit_logs` | in scope | it has a clan column, nullable or not |

**Today's veto enforces only the first two clauses.** The assertion at
`test_rls_activation.py:531-537` refuses an exemption that has a clan column or a foreign key to
`clans`. It does not follow NOT NULL chains. A new table with a NOT NULL `person_id` and no clan
column could be added to the list, and the gate would stay green. The clause is enforced by follow-up
issue #169.

### 3. Their posture: outside layer 2, protected by the application layer alone

Both tables keep RLS disabled, the same posture as `clans`. This is a decision, not missing coverage.

- **Layer 2 in this repository means clan isolation.** ADR-002 isolates on clan, ADR-008 builds
  RLS as defence in depth for that isolation, and every shipped policy keys on `app.clan_id`. These
  rows have no clan to isolate on.
- **A user-keyed policy needs `app.user_id`, and ADR-047 refuses it** unless a change shows five
  preconditions. None of them is shown here. ADR-050 already weighed the closest shape, "self or
  same clan", for `user_clan_roles` (its Alternatives, row (d)) and rejected it. That objection
  transfers here unchanged: on `POST /auth/register` and `POST /auth/login` there is no
  authenticated identity when `user_profiles` is queried, so the GUC would mean two different
  things. The policy would also break the FCM upsert. Postgres raises an error when
  `ON CONFLICT DO UPDATE` meets an existing row that fails the `UPDATE` policy's `USING` check, and
  a token registered to another user is exactly that row.
- **Denying the request role cannot work for `user_profiles`.** ADR-042 gave `identity_claims` a
  deny-all tripwire because no request-role path touches that table. Here, every authenticated route
  reads `user_profiles` on `get_db` through `get_current_user`. For `user_fcm_tokens` it could work,
  but only by moving routine user writes onto the privileged session. That runs opposite to the
  purpose of layer 2. ADR-050 row (a) counts the cost of the same move for the auth routes.

### 4. The risk this posture accepts, stated plainly

`familyroots_app` can read every user's `email`, `platform_role`, and `person_id`, and every push
token. It can also write to both tables. Today, nothing beyond the application layer stops that.
Every request-path statement listed above keys on the caller's verified `sub` or on the current
clan. One query that loses its `WHERE id = :sub` would leak across clans, and no database layer
stands behind it.

### 5. Two events reopen this decision

1. **A change meets ADR-047's five preconditions for `app.user_id`.** A user-keyed policy then
   becomes possible and should be weighed again, together with the FCM upsert semantics.
2. **The application database moves into the Supabase project.** These two tables would then sit in
   a schema the Data API can expose, and their grants alone would protect them. The clan-keyed
   tables would fail closed, because nothing on that path sets `app.clan_id`. These two would not.
   `docs/ops/local-supabase.md` carries this warning beside the topology it depends on.

## Consequences

Easier:

- `_NOT_CLAN_OWNED_TABLES` cites a decision for every entry. A reader who asks why a table is exempt
  can check the answer against a rule instead of a reason string.
- The next table that proposes an exemption has a sentence to fail against.

Harder:

- The risk in § 4 is accepted rather than closed. Until one of the § 5 events happens, a user-data
  leak across clans has one line of defence, not two.
- Until issue #169 lands, the third clause of the rule in § 2 is prose. The gate does not enforce it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Treat both as clan-owned and put them in one of the four posture sets | Fails the scenario in § 1: clan A deleting the linked person leaves the profile alive. No posture set fits a row with no owning clan |
| A user-keyed RLS policy now | Needs `app.user_id`, which ADR-047 refuses without five preconditions. ADR-050 row (d) rejected the same "self or same clan" shape because the GUC would mean two things on login and register. It also breaks the FCM upsert's move-on-re-register rule. See § 3 |
| Deny the request role on both, like `identity_claims` (ADR-042) | Impossible for `user_profiles`, which `get_current_user` reads on every authenticated route. For `user_fcm_tokens` it moves routine writes onto the privileged session |
| Split: `user_profiles` outside layer 2, `user_fcm_tokens` denied | Same cost as the row above for the token table, and it buys little: every token read already runs on the privileged scheduler connection |
| Leave the reason strings as they were, with "NO ADR DECIDES THIS" | Leaves the exemption list as a setting, which is the failure `.claude/rules/testing.md` names |

## What this ADR deliberately does not decide

- **Column-level grants** that narrow what `familyroots_app` can read in either table. Not weighed
  here, and not needed to settle the posture.
- **`scripts/bootstrap_super_admin.py`.** It writes `user_profiles` through the Supabase Data API
  (`:36`, `:66`), but per § Context that table is not in the Supabase database. That defect is
  issue #168, separate from this decision.
- **ADR-048 and ADR-050.** Each states as a fact that `user_profiles` carries no policy
  (`048-invitation-accept-runs-on-the-system-session.md:144`,
  `050-user-clan-roles-clan-keyed-mutations.md:224`). Both stay as written. This ADR is the decision
  they did not make.

## Related

- [ADR-002: Single Schema Clan-Scoped Multitenancy](002-clan-scoped-multitenancy.md): why
  isolation is on clan.
- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md): keeps
  `clans` outside layer 2, the posture these two tables now share.
- [ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies](043-audit-notification-rls-posture.md):
  the nullable-clan-column case that shaped § 2's wording.
- [ADR-047: The RLS Seam Sets `app.clan_id` Only](047-rls-seam-sets-clan-id-only.md): the five
  preconditions behind § 3 and § 5.1.
- [ADR-058: Registration May Name No Clan](058-registration-may-name-no-clan.md): the clanless
  account that makes a profile exist before any clan.
