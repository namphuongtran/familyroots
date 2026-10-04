# ADR-061: The Web Auth Slice Holds the Session as Server State, Routes Access Once on the Server, and Guards by Capability

## Status

Accepted (2026-10-04). Resolves issue #165, "What is the auth slice, now that part of it shipped
outside features/?", on the map in issue #158. The maintainer chose every option below in a
grilling session on 2026-10-04.

**This ADR ships no runtime code.** The diff is this file, its index row, the web architecture
spec's § 4.1 and § 5.1, `web/CLAUDE.md`, and five glossary terms in `CONTEXT.md`. Documentation
only, so no gate applies. The code is in six build issues, #181 to #186, listed in § 8.

Every reading below was taken on **2026-10-04** at commit `6879ace` on `main`. Treat its line
numbers as hints and its quoted text as the claim.

2026-10-04: the email-link question this ADR left to #178 is decided by
[ADR-063](063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md). Its landing pages are
#200 and #201, both blocked by #183.

## Context

### The spec's auth slice, and what happened instead

The web architecture spec, `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`,
puts auth first among the slices (§ 5.1, row 1): "`current_clan_id` cookie, `auth.store` rewritten
around the context, capabilities, middleware on the cookie, 403 screens". Its § 4.1 says
"`auth.store` remains the client-side source of truth but writes the cookie whenever the clan
changes".

There is no `web/src/features/auth/`. Part of row 1 shipped in the spine without a decision record:

- the cookie and the request context, in `shared/http/request-context.ts`, `context.client.ts` and
  `context.server.ts`;
- the middleware's cookie check, at `web/src/middleware.ts:113-125`;
- the capability table, in `domain/capability/capability.ts`.

The rest is untouched legacy. `lib/hooks/useAuth.ts` drives the session through
`application/auth/`, `infrastructure/auth/`, and the zustand store `store/auth.store.ts`. The
blocked-state screens are in `components/auth/`.

### What reading it at source found

1. **The store is the runaway.** Measured 2026-08-26, `/vi/dashboard` re-ran `useAuth`'s mount
   effect 2613 times in seven seconds and sent 18174 `GET /auth/me` (`web/CLAUDE.md:836-847`). Two
   consumers mount on every dashboard page (`(dashboard)/layout.tsx:12`, `Header.tsx:18`). Each one
   hydrates on its own and writes fresh objects into the store.
2. **The store persists a fact the backend owns.** `auth.store.ts:57-67` writes `user`, role
   included, and `clanMemberships` to `localStorage['auth-store']`. The store's own header comment
   says it removed the clan id because "two persisted sources for one fact" is a defect. The role
   is the same kind of fact.
3. **The client and the server work out the active clan differently.** `resolveCurrentClanId` exists
   twice. The client copy (`application/auth/use-cases/auth-context.ts:120-140`) falls back to
   `profile.clan_id`. The server copy (`lib/server/auth-context.ts:173-186`) does not.
4. **Three layers route a signed-in user**: the middleware, the server's `requireServerRole`, and a
   client redirect effect in `(dashboard)/layout.tsx:18-37`.
5. **Route guards climb a role ladder.** `hasMinServerRole` (`lib/server/auth-context.ts:160-171`)
   ranks viewer < editor < admin. `domain/capability/capability.ts:126-132` rejects that ladder on
   purpose and states each role's capabilities instead.
6. **The web cannot learn that a user is super_admin.** `GET /auth/me` does not send `platform_role`
   (`backend/app/schemas/auth.py:105-115`), although the column exists
   (`backend/app/models/user_profile.py:31`). So the client's `isPlatformOnlyUser`
   (`auth-context.ts:87`) is always false, and the server guard calls `GET /platform/metrics` on
   every admin, backoffice and platform page load to find out (`lib/server/auth-context.ts:122-138`).
7. **Nothing in the browser refreshes a token.** Persons and invitations each built their own
   `use-*-request-context.ts`. Each reads the token once and passes no `refreshAuth`, waiting for "an
   auth slice to own" it (`features/persons/ui/use-persons-request-context.ts:19-30`).
8. **Persons imports more auth legacy than ADR-060 counted.** Besides the two `useCapabilities`
   imports, `members/page.tsx:5` and `members/[id]/page.tsx:5` import `lib/server/auth-context.ts`.
9. **`VerifyEmailScreen` cannot be reached from a real sign-in.** It handles `403
   email_not_verified`, which only `POST /auth/login` raises. The live sign-in calls Supabase's
   `signInWithPassword` directly (`web/CLAUDE.md:938-946`).
10. **A successful registration shows nothing.** `register` returns the whole envelope, so the page's
    `result.message` is `undefined` (`web/CLAUDE.md:826-835`).

## Decision

### 1. What `features/auth/` owns, and what stays outside it

| `features/auth/` (auth's slice-owned legacy, under ADR-060 § 1) | Stays outside |
|---|---|
| The session, sign-in, sign-out, register, onboard and clan selection. Replaces `lib/hooks/useAuth.ts`, `store/auth.store.ts`, `application/auth/`, `infrastructure/auth/` | **`shared/http/`**: the cookie, the request context, `context.client.ts` and `context.server.ts`. These are transport. Every slice and `middleware.ts` need them, and `shared` cannot import `features` |
| The screens: login, register, select-clan, and the blocked-state screens from `components/auth/` | **`domain/capability/`**: pure role → capabilities, unchanged |
| The capability hook, replacing `lib/hooks/useCapabilities.ts` | **`middleware.ts`**: Next.js requires it at `src/`. It keeps importing only `shared` |
| The server guard, replacing `lib/server/auth-context.ts` and `lib/utils/with-role.ts` | **A new pure access-state function in `domain/`** (§ 3) |
| | **`lib/supabase/` moves to `shared/supabase/`**: `shared/http` importing `lib/` points the dependency the wrong way |

`lib/hooks/useClanContext.ts` has no importers and is deleted.

**Finding 8 widens "persons is done".** Under ADR-060 § 2-3, auth re-points persons' two
`useCapabilities` imports **and** its two `getServerAuthContext` imports. Persons closes when the
persons legacy deletion (#172), #185 and #186 have all landed.

### 2. The session is server state, held in one query, not in a store

`auth.store.ts` is replaced, not moved. The session is one TanStack Query query over `GET /auth/me`
and `GET /me/clans`. Supabase's `onAuthStateChange` resets it. Access state is derived on every
read and never stored. Nothing writes the user, the role or the memberships to `localStorage`.

Any number of consumers share one cache entry, so the request count is fixed by design. That
removes finding 1. It also removes finding 2, and it puts the session in the same tool that already
holds server state in `persons` and `invitations`. zustand keeps only `ui.store.ts`.

**This reverses spec § 4.1's "`auth.store` remains the client-side source of truth".** § 4.1 now
points here.

### 3. Access state is one domain function, and the server routes on it once

One pure function in `src/domain/` takes a session or none, the approved memberships, whether a
pending membership exists, `platform_role`, and the clan the cookie names. It returns one of:
signed out, pending approval, needs onboarding, needs clan selection, platform, or ready in an
active clan. Both runtimes call it, which removes finding 3.

The layers split the work this way:

- **`middleware.ts`** checks only that a session and a clan cookie exist. It makes no backend call.
- **One server guard** in `features/auth/server/` makes every other routing decision, from that
  function. `(dashboard)/layout.tsx` becomes a server layout that calls it.
- **Client components only render.** The redirect effect in `(dashboard)/layout.tsx` is deleted.

### 4. Guards and hooks ask for a capability, never for a rung on a ladder

Each guarded page names the capability it exercises. `admin/users` and `backoffice/*` need
`viewPendingUsers`, and `admin/clan` needs `editClanSettings`. `hasMinRole` and `hasMinServerRole`
are deleted.

The client capability hook returns the domain `CapabilitySet`, all false without an active clan
or an approved membership. Its callers switch to the domain names. The four renamed booleans go.

**One behaviour change follows, and it is intended.** A super_admin without an admin membership in
the active clan no longer enters `admin/` or `backoffice/`. The backend's clan checks give
super_admin no bypass (`backend/app/core/permissions.py` has no `super_admin` branch), and
`docs/architecture/rbac.md:29-35` makes the role platform-level.

### 5. super_admin is read from `platform_role` on `/auth/me`

The backend adds `platform_role` to `GET /auth/me`, with `docs/contracts/rest-auth-api.md` in the
same pull request (#181). The `/platform/metrics` probe is deleted. A super_admin with no
membership routes to `platform/`, not to onboarding.

### 6. One browser request context, with one `refreshAuth`, lives in `shared/http`

`shared/http` exports one client request-context hook whose token follows Supabase's auth-state
changes, and one browser-wide `refreshAuth`: `createSingleFlight` (`shared/http/refresh.ts`) over
Supabase's `refreshSession()`. Persons and invitations use it, and their two
`use-*-request-context.ts` copies are deleted. It goes in `shared`, not `features/auth`, because it
is transport and every slice needs it.

### 7. An unconfirmed sign-in reaches `/verify-email` through Supabase's own error code

Sign-in stays Supabase-direct. When Supabase refuses a password sign-in with the error code
`email_not_confirmed`, the slice routes to `/{locale}/verify-email`. This makes the screen
reachable without a second login path. How email links land stays with #178.

### 8. The slice is six build issues, and "auth is done" has four checkable conditions

| Issue | What it does | Blocked by |
|---|---|---|
| #181 | `GET /auth/me` returns `platform_role` (backend) | none |
| #182 | Registration shows its success screen (§ 9) | none |
| #183 | `features/auth`: the session query, the actions, the screens, the access-state function. Deletes the client auth legacy | #182 |
| #184 | One request context and `refreshAuth` in `shared/http`. `lib/supabase` → `shared/supabase` | none |
| #185 | The capability hook returns `CapabilitySet` | #183 |
| #186 | One server guard, by access state and capability | #181, #183 |

Each pull request deletes what it replaces, so spec § 5.1's "No PR only adds" holds for each one.

**Auth is done when all four hold:**

1. **No slice-owned auth legacy is left.** `git ls-files` returns nothing for
   `lib/hooks/{useAuth,useClanContext,useCapabilities}.ts`, `store/auth.store.ts`,
   `application/auth/`, `infrastructure/auth/`, `components/auth/`, `lib/server/auth-context.ts`,
   `lib/utils/with-role.ts`, or `lib/supabase/`.
2. **`features/auth` imports no legacy.** The import baseline (#171) has no entry from
   `features/auth/`.
3. **Each outcome is pinned by a test that was seen to fail against its planted defect:**
   - a dashboard load sends at most 2 `GET /auth/me` (#183);
   - registration renders its success screen against the real envelope (#182, kept green by #183);
   - two concurrent 401s cause one refresh, and both requests retry (#184);
   - access state is one function, tested against a table that includes "approved in A, pending in
     B → ready in A" and "super_admin, no membership → platform" (#183, #186);
   - a viewer is turned away from `admin/users`, an admin gets in, and a super_admin with no clan
     reaches `platform/` (#186).
4. **Persons imports no auth legacy** (#185, #186).

### 9. The two known defects

- **The registration envelope defect ships on its own, first** (#182). It is live and visible to
  users, and the fix is two lines. Its test outlives the file. #183 rewrites the repository and must
  keep that test green, unedited.
- **The dashboard runaway gets no stopgap.** #183 removes it by design (§ 2). A patch to `useAuth`
  would be deleted by the next pull request. No real clan uses the app before M1 closes.

## Consequences

Easier:

- "Is auth done?" has a checkable answer: a file list, a baseline, and five named tests.
- Every later slice gets a request context that refreshes, instead of copying the persons gap.
- The client and server cannot disagree about where a user belongs, because one function decides.
- The authenticated e2e harness can cover `/vi/members` once #183 lands.

Harder:

- #183 and #184 both re-point Supabase importers, so whichever lands second rebases.
- #183 leaves two temporary adaptations that later issues remove: a client redirect in
  `(dashboard)/layout.tsx` (until #186), and `useCapabilities` reading the new session (until #185).
- Moving routing to a server layout means `(dashboard)/layout.tsx` fetches `/auth/me` and
  `/me/clans` on every navigation, deduplicated per request.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Move `auth.store.ts` into the slice as it is | Keeps the runaway's mechanism and the persisted copy of the role |
| Keep zustand without `persist`, hydrated once in a provider | Removes the runaway, but keeps a hand-built cache beside the TanStack Query one every slice already uses |
| Keep both the server and the client checks, both calling the domain function | Two layers redirecting on the same state is how finding 3 arose, and the client copy needs a loading spinner the server one does not |
| Keep the `/platform/metrics` probe | One extra request per page load, and a metrics outage turns into a redirect |
| Leave the browser `refreshAuth` for later | The spec's promise of "a trustworthy context" stays unmet, and five slices copy the gap |
| Fix the runaway in `useAuth` first | The fix is deleted by #183 |
| Sign in through the backend's `POST /auth/login` so `email_not_verified` is raised | A second login path, whose tokens would then have to be handed to the Supabase client |

## What this ADR deliberately does not decide

- **How email links land**, through Supabase's verify redirect or as a `token_hash` on a page of
  ours. That is #178. Its build issue lands in `features/auth/` after the slice.
- **When `lib/api/axios.ts` and `infrastructure/http/request-context.ts` go.** They are cross-cutting,
  and ADR-060 § 1 gives them to the last slice that imports them. #183 only trims the second one's
  reads.
- **Whether persons is otherwise a finished reference pattern.** ADR-060 left that open, and so does
  this ADR.

## Related

- [ADR-060: A Web Slice Deletes Its Own Legacy and Re-Points Every Importer](060-a-slice-deletes-its-own-legacy-and-re-points-its-importers.md):
  the deletion and "done" rules this slice follows.
- [Web architecture spec](../superpowers/specs/2026-08-02-web-architecture-observability-design.md):
  § 4.1 and § 5.1 row 1 now point here.
- `docs/architecture/rbac.md`: the permission matrix `domain/capability` encodes, and super_admin's
  platform scope.
- `CONTEXT.md`, "Belonging": **Session**, **Membership**, **Pending membership**, **Active clan**,
  **Suspended clan**.
