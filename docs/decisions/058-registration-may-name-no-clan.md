# ADR-058: Registration May Name No Clan, and the Invitation Token Stays Out of `POST /auth/register`

## Status

Accepted (2026-08-26), by seed **S-085**, which [ADR-057](057-the-invitation-link-is-the-primary-join-path.md)
opened from its own finding 2.

**This ADR ships code**: `clan_action` becomes optional on `RegisterRequest` only, a new
`AuthCommandHandler._provision_clanless_account`, and one integration module that walks the whole
invitation flow.

Every measurement below was taken on **2026-08-26** in the worktree
`.claude/worktrees/s-085-backend`, on branch `seed/s-085-register-with-no-clan`, whose base commit
is `bc73f7c` (the tip of `seed/s-081-join-by-clan-code`, not yet merged anywhere). Where a line
number is given, the claim was read at that line.

## Context

### The gap, in one sentence

An invited stranger holds a token, and needs an account before the token is of any use to them, and
could not create one.

Both halves were read at source and both are old:

| Half | Source | What it says |
|---|---|---|
| accept needs a signed-in caller | `backend/app/api/v1/invitations.py:95-99` declares the route with `current_user: dict[str, Any] = Depends(get_current_user)`; `:104-105` read `current_user["sub"]` and `current_user.get("email", "")` | the token does not authorize by itself in a browser |
| register needed a clan | `clan_action: Literal["join", "create"]` carried no default on `RegisterRequest`, and `_resolve_join_target` raises `auth.clan_id_required_for_join` when neither identifier is given | an invitee has no code to type and no clan to found |

The contract agrees with the first: `Auth | Yes` at `docs/contracts/rest-invitations-api.md:62`.

### What the pre-fix failure actually is, and it is not the code the seed named

Seed S-085 and ADR-057 finding 2 both point at the handler check and expected
`auth.clan_id_required_for_join`. **Measured 2026-08-26, that is not the error an honest invitee
request gets.** Posting the invitee's body — email, password, full name, and no clan field at all —
to `POST /auth/register` against the code before this ADR returned:

```
status=422
{"error":{"code":"validation_error","message":"error.validation_error","detail":{"fields":["body.clan_action"]}}}
```

A body that **omits** `clan_action` is refused by Pydantic and never reaches the handler, so the
handler's code cannot be the one it sees. `auth.clan_id_required_for_join` is the second, different
failure: it needs a caller who explicitly sends `clan_action=join` and no identifier. Both readings
are real; they belong to two different requests. This is recorded here because a later reader
following the seed would look for the wrong code.

### A user with no clan is a state this product already draws, and the spec already names it

The seed asked whether a clanless account is the same state as the existing blocked and pending
screens, or a fourth one. **It is the same state, the design spec names it, `web` implements it, and
`mobile` mislabels it.** Read at source 2026-08-26:

- **The spec names it, in the pending screen's own States list**, § 7.2a at
  `docs/superpowers/specs/2026-08-02-design-system-and-screens.md:925-927`: *"No membership at all
  (`is_approved` false, `has_pending_membership` false, `clan_id` null) → onboarding variant of this
  screen with the join/create segmented control from 7.1b."* So it is a **variant of § 7.2a**, not a
  fourth screen.
- **`web` computes it and routes it.** `web/src/application/auth/use-cases/auth-context.ts:95`:
  `needsOnboarding: !isPlatformOnlyUser && !hasApprovedClanMembership && !hasPendingMembership`,
  distinct from `isPendingApproval` on the line above. `web/src/components/auth/PendingApprovalScreen.tsx:11-15`
  records the divergence from the spec deliberately: the onboarding variant "is, in this codebase,
  already a separate route — `useAuth().needsOnboarding` sends the user to `/register?mode=oauth`".
- **`mobile` does not.** `mobile/lib/app/router/app_router.dart:74` has a single post-verify gate,
  `if (!auth.hasApprovedMembership)`, which sends the user to `Routes.pending`. The copy there,
  `mobile/lib/core/l10n/app_en.arb:207`, is *"Your join request is waiting for a clan admin to
  approve it."* — false for someone who has made no request. The correct predicate already exists
  and is wired to nothing: `UserProfile.needsOnboarding` at
  `mobile/lib/domain/auth/user_profile.dart:29-30`, referenced only from
  `mobile/test/features/auth/auth_repository_test.dart`.

**So this ADR invents no state.** It makes the state the spec already specifies reachable through
the API. The mobile screen gap is named as owed below; it is a mobile seed, not this one.

The login response a clanless account gets is exactly the triple the spec's condition reads, and
this ADR pins it (Stage 4 of the walk): `clan_id: null`, `is_approved: false`,
`has_pending_membership: false`, `role: null`.

## Decision

### 1. `clan_action` is optional on `POST /auth/register`. Omitting it creates an account with no clan membership.

`RegisterRequest.clan_action` becomes `Literal["join", "create"] | None = None`
(`backend/app/schemas/auth.py`). When it is `None`, `AuthCommandHandler.register` skips clan
validation entirely, creates the identity, and calls the new `_provision_clanless_account`, which
writes one `user_profiles` row and commits through the Unit of Work.

**Nothing else about the route changes.** The response is the same non-enumerating
`{"data": {"message": ...}}`, the verification email is still sent, and no error code is added.

### 2. A body that names a clan without naming an action is refused, in Pydantic

`RegisterRequest` carries a `model_validator(mode="after")` that raises when `clan_action is None`
and any of `clan_code`, `clan_id`, `clan_name`, `clan_slug` is present. The caller gets the existing
422 `validation_error`.

**Two reasons this rule exists, and one reason it lives in the schema rather than the handler.**

Without it, a client that names a clan and forgets `clan_action` would silently receive a clanless
account instead of the membership it asked for. Which clan a membership lands on is the one boundary
this product cannot get wrong (root `CLAUDE.md`), and "no clan at all" is a wrong answer to "join
this clan" as surely as "the wrong clan" is.

It lives in the schema because a schema validator runs **before the route body**, so it cannot
consult the identity provider and therefore **cannot** answer differently for a registered and an
unregistered email. Putting the same rule in the handler would have meant a new error code on a
non-enumerating route, which is precisely how an enumeration oracle gets built — the defect the
regression tests in `test_register_non_enumeration.py` were added for. Measured: on both a
registered and an unregistered email, the refusal is byte-identical and `create_user` is never
called.

**The residual, stated plainly.** A client that drops `clan_action` **and** every clan field sends a
body indistinguishable from an invitee's, and gets a clanless account where it previously got a 422.
No shipped client can do this: `web/src/app/[locale]/(auth)/register/page.tsx:80` and `:90` put
`clan_action` in the request object unconditionally, and `mobile/lib` has no register caller at all
(counted by S-081 and recorded at `docs/contracts/rest-auth-api.md`). A blank code field is also
still a 422, because `""` fails `_SLUG_PATTERN`.

### 3. `POST /auth/onboard` keeps `clan_action` required

`AuthenticatedOnboardingRequest` is **unchanged**. ADR-057's owed item named both schemas; this is a
deliberate narrowing, and the reason is the response.

`POST /auth/onboard` answers with `RegisterResponse`, whose `clan_id: uuid.UUID` is **not** optional
(`backend/app/schemas/auth.py`). A clanless onboard could not answer in its own response shape.
Making `clan_id` optional there would be a breaking change to a response the web client binds
(`docs/contracts/rest-auth-api.md` records the shape), in exchange for a request nobody needs: the
route exists only to attach an already-authenticated user to a clan, so a clanless onboard is a
no-op. The invitee's path never touches it — they register, verify, sign in, and accept.

### 4. The invitation token is not passed to `POST /auth/register`

The seed's second shape was a token-carrying register call, granting the membership in the same
transaction and keeping "every account has a clan" true. **Rejected, on four independent grounds.**

1. **It would weaken the property that makes an invitation link safe to share.** Today accept sits
   behind `get_current_user`, and a Supabase account cannot sign in until its email is confirmed
   (`403 email_not_verified`, `docs/contracts/rest-auth-api.md`). So the email-match rule at
   `docs/contracts/rest-invitations-api.md:67` today means "the caller controls the invited inbox".
   Granting the membership during register would demote it to "the caller typed the invited address",
   which is a claim, not a proof. ADR-057 § 3 calls the email-match rule "the property that makes the
   link safe to share at all".
2. **It cannot share one transaction anyway.** [ADR-048](048-invitation-accept-runs-on-the-system-session.md)
   § 1 put accept on the privileged `get_system_db`, because the invitation read has no clan GUC and
   the migration-027 predicate on `clan_invitations` evaluates to NULL, which is zero rows.
   `get_auth_command_handler` is on `get_db`. So a token-carrying register would need register itself
   moved to the privileged session, or a second session inside one handler — and ADR-048's rejected
   "hybrid" option is the same shape, refused there for three reasons that all still apply.
3. **It needs at least three new error codes on a non-enumerating route** —
   `invitation.not_found`, `invitation.email_mismatch`, `invitation.not_pending`. The second is an
   oracle by construction: it tells the caller whether the address they typed is the invited one.
4. **It couples two aggregates.** `app/application/auth/` would have to reach the invitation
   aggregate's accept logic, including the C3 accept-versus-revoke conditional UPDATE
   (`app/application/invitation/handlers.py`), or copy it. A second copy of a race guard is a second
   place to be wrong.

### 5. Accept before an account exists is rejected

The seed rejected this on its face and asked for the reason to be written down rather than left to be
re-proposed. **A leaked token would become sufficient to create an account.**
`docs/contracts/rest-invitations-api.md:74` states that the token "is the only thing that decides",
and ADR-048's own consequences say plainly that "a leaked or guessed token reads and writes across
clans". Today the worst a leaked token can do is grant a membership to somebody who already holds a
verified account on the invited address. Letting it mint the account removes the email-match rule's
only teeth, because the accepter would be choosing the address the rule compares against. It would
also make an unauthenticated route the creator of identities, which is the identity provider's job
and not this API's.

### 6. The clanless register path emits no domain event, and commits through the Unit of Work

`_provision_clanless_account` writes one `user_profiles` row and calls `uow.commit()`. Three reasons,
each read at source:

- **`ensure_profile` is audited nowhere else either.** `_assign_clan_membership` audits
  `clan.create` on the create path and `clan.join_request` on the join path. Both rows are about the
  clan. This account has none.
- **A NULL-clan audit row would be written and never read.** `audit_logs.clan_id` is nullable
  (`backend/app/models/audit_log.py:37-39`) and `track_audit_event` passes `None` through
  deliberately (`backend/app/application/shared/audit.py:52-57`), so the row is possible. But
  `audit_logs_sel` is `USING (clan_id = <app.clan_id GUC>)` (ADR-043) and the application-layer
  reader is clan-keyed too, so nothing but the super-admin log could ever see it. Adding a row
  guarded for a reader that cannot arrive is the `clan_settings` mistake in miniature
  ([ADR-054](054-clan-settings-table-is-dropped.md)).
- **The Unit of Work rule is not relaxed.** The commit still goes through the UoW.
  `FCMTokenHandler.register_token` (`backend/app/application/auth/handlers.py`) is the standing
  precedent for a UoW commit with no event, and its docstring gives the same reason: the commit
  discipline is what guarantees the write survives the request.

### 7. The name typed at registration is kept by this path, and that is load-bearing

`IdentityProvider.create_user` takes `email` and `password` only
(`backend/app/domain/auth/identity_provider.py:75`), so **nothing carries `full_name` to the
provider.** Invitation accept calls `ensure_profile` with the JWT's
`user_metadata.full_name`, which is empty for an account created this way, and `ensure_profile_row`
is `ON CONFLICT DO NOTHING` on the primary key
(`backend/app/infrastructure/persistence/_profile.py:33`). So if the clanless register path wrote no
profile row, the person's name would be silently replaced by the local part of their email address.
`test_the_name_typed_at_register_survives_accept` reads `user_profiles.display_name` after the whole
walk and requires the typed name.

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **A third `clan_action` value, e.g. `"none"`** | Explicit, and it would remove the residual in § 2 completely: a client that dropped the field would still 422. Rejected because it makes four clients learn a magic string to express "I am not asking for anything", and because the residual it removes is unreachable from any shipped client (§ 2). An absent field is the honest encoding of an absent request |
| **Token-carrying register** (`invitation_token` on `RegisterRequest`) | § 4. Four independent objections, of which the first is a real weakening of the invitation link's safety property |
| **Accept creates the account** | § 5. A leaked token would become sufficient to create an identity |
| **Make `clan_id` optional on `RegisterResponse` and let onboard go clanless too** | § 3. A breaking response change the web client binds, for a request with no caller |
| **Put the "clan named, no action" rule in the handler** | § 2. It would be a new error code on a non-enumerating route, decided after the identity provider had been consulted on some paths. The schema is the layer that provably cannot leak |
| **Emit an `auth.register` audit row with `clan_id = NULL`** | § 6. Possible, and unreadable by every clan-keyed reader in the tree |

## Consequences

### What this buys

- **The invitation flow is reachable end to end by a new person for the first time.** ADR-057's
  Consequences said it could not be until this seed landed.
- **The state the spec already specified now has an API that can produce it.** § 7.2a's onboarding
  variant condition — `is_approved` false, `has_pending_membership` false, `clan_id` null — is what a
  clanless account's login returns, and it is asserted rather than assumed.
- **No new error code, and no new i18n entry.** The route's error surface is byte-identical for every
  body that carries a `clan_action`.

### What this costs, stated plainly

- **"Every account has a clan" is no longer true.** It was already not true in practice — invitation
  accept has always provisioned a profile for a caller with no membership
  (`app/application/invitation/handlers.py`, `ensure_profile` before the membership) — but this makes
  a clanless account something a client can ask for. Any later read that assumes a membership exists
  has to handle its absence. The reads on the auth path already do: `get_login_profile` and
  `get_profile` outer-join `user_clan_roles` and `_profile_view` returns `None` fields for a missing
  membership (`backend/app/infrastructure/persistence/auth_repository.py:24-38`).
- **`mobile` shows the wrong screen for this state**, and it did before this ADR too — the state was
  simply unreachable by registration. Owed below.
- **`web/src/generated/api-types.ts` is now stale** at `:1545` and `:3400`, both of which type
  `clan_action: 'join' | 'create'` as required. It is generated from the OpenAPI document and `web/`
  was fenced to another agent, so it is not regenerated here. Owed below.
- **The residual in § 2.** A client that drops `clan_action` and every clan field gets a clanless
  account where it used to get a 422.

### Owed, named rather than left to be found

1. **Regenerate `web/src/generated/api-types.ts`** so `clan_action` is optional on the register
   request. Belongs with seed S-082, which owns the web register form.
2. **`mobile` needs the onboarding branch.** `mobile/lib/app/router/app_router.dart:74` routes a
   zero-membership user to `/pending` and tells them their join request is being reviewed.
   `UserProfile.needsOnboarding` (`mobile/lib/domain/auth/user_profile.dart:29-30`) is the predicate,
   already written and already tested, and nothing reads it. A mobile seed, not this one.

## What this ADR deliberately does not decide

- **Email verification.** Unchanged. A clanless account is created unconfirmed and sends the same
  verification email; login still answers `403 email_not_verified` until it is confirmed. The
  integration walk models a confirmed account at the stubbed identity seam and says so.
- **`accept_path`**, which is seed S-086 and ADR-057's second owed item.
- **The invitation landing page** (S-084) or the web register form (S-082, S-083).
- **Clan discovery.** ADR-057 refused it against ADR-044, and nothing here reopens it. No route added
  or changed answers "which clans exist".
- **Whether `clan_id` stays on the join path.** S-081 decided that in
  `docs/contracts/rest-auth-api.md` and this ADR does not touch the window.
- **Any change to the invitation request or response contract.** There is none.

## Related

- Seed **S-085** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes.
- [ADR-057](057-the-invitation-link-is-the-primary-join-path.md) — found the gap, named this seed as
  owed, and made the invitation link the primary join path.
- [ADR-048](048-invitation-accept-runs-on-the-system-session.md) — why accept runs on the privileged
  session, and the reason a token-carrying register cannot share one transaction with it.
- [ADR-021](021-non-enumerating-auth-surfaces.md) — the non-enumeration rule this change must not
  bend, and the ordering property register already holds.
- [ADR-054](054-clan-settings-table-is-dropped.md) — the precedent for refusing a write guarded for a reader that
  cannot arrive.
- Spec § 7.1b (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:854-873`) and § 7.2a
  (`:904-930`) — the register screen's non-enumeration rule, and the onboarding variant this makes
  reachable.
- `docs/contracts/rest-auth-api.md` — "Registering with no clan", which extends S-081's "The join
  identifier".
