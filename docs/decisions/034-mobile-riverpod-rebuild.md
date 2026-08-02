# ADR-034: Rebuild the Flutter App on Riverpod, Deleting the Mock Scaffold

## Status
Accepted — 2026-08-02

## Context

`mobile/` has held a Flutter scaffold since 2026-03-07. Five months later it still
makes **no HTTP call to the backend**: `core/network/api_client.dart` and
`core/network/auth_interceptor.dart` are `// TODO: implement in Prompt 2` stubs, and
`core/di/injection.dart` binds every repository to `lib/domain/mocks/`. Firebase,
Sentry and Hive initialisation are likewise TODO comments in `main.dart`.

The structure had also drifted in ways that would fight a real implementation:

- Two directories named "domain" coexisted — `lib/domain/` (ports plus mocks) and
  `lib/features/<f>/domain/` (entities) — with `MemberModel.fromJson` living inside
  the supposedly framework-free one.
- Two dependency-injection systems ran side by side (`get_it` + `injectable`
  alongside `flutter_bloc` provider scoping).
- Five hardcoded `lh3.googleusercontent.com` mock-up image URLs shipped inside
  production screens.
- `google_fonts` fetched the mandated typefaces over the network at runtime,
  falling back to the system font offline — a direct violation of the Arbor
  Heritage mandate.
- Mobile CI had never executed a single test: every run since March died at a
  dependency step for `packages/family_roots_core`, a directory that has never
  existed in the repository. A widget test asserting a string present in no locale
  and no widget survived undetected for months as a result.

Meanwhile the backend became the opposite: ~70 endpoints across 15 routers with
frozen, documented contracts — the canonical envelope and opaque cursors (ADR-010),
`HistoricalDate` (ADR-011), optimistic concurrency (ADR-017), single-authority đời
(ADR-027), founder designation (ADR-026), and W3C trace context (ADR-033).

Rewriting the scaffold in place was considered and rejected: there is no transport
layer, no real repository, and no domain rule to preserve. What exists is screen
markup bound to fabricated data.

## Decision

Delete `mobile/` and rebuild it, carrying forward only the `.arb` translation
files, the Arbor Heritage design mandates, `l10n.yaml` and `assets/`.

The replacement is specified in
`docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`. The
load-bearing choices:

1. **Riverpod 3 is both the state manager and the DI container.** FamilyRoots
   mobile is an overwhelmingly server-state application; `AsyncNotifier` plus
   `ref.invalidate` maps almost one-to-one onto the TanStack Query model the web
   client already uses, giving one mental model across both clients. `get_it` and
   `injectable` are dropped — one container, not two.
2. **Plain Dio with hand-written repositories, DTOs via `json_serializable`.**
   Retrofit and OpenAPI client generation are both rejected on the grounds ADR-010
   already states: `profile`/`include`/`fields` sparse-fieldset semantics are not
   expressible by a generator, so the output would need hand-wrapping regardless.
3. **The backend contract lives in exactly one place per concern.** The envelope is
   unwrapped in one function; `policyActionFor(code)` is the single mapping from
   backend error code to routing decision; `HistoricalDate` is a domain model that
   owns its render rule. The scaffold's failure mode was every widget improvising.
4. **Layer boundaries are machine-enforced**, by a test that scans the import
   directives of every file under `lib/` — the mobile counterpart of the backend's
   `lint-imports` ratchet (ADR-013). `dart_code_metrics` is now commercial and no
   maintained equivalent exists, so a plain test is used instead of a dependency.
5. **The Supabase session is stored in `flutter_secure_storage`**, not the
   `supabase_flutter` default of SharedPreferences, which writes tokens to disk in
   plaintext. `docs/contracts/frontend-integration-guide.md` §2 forbids that.
6. **Fonts are bundled as assets.** `google_fonts` is dropped.
7. **Offline support is read-cache only** — responses are cached and re-served when
   the network fails; writes always require connectivity. A write queue is rejected
   for now: the backend already has optimistic concurrency, so offline writes would
   have to resolve genuine `409 stale_write` conflicts, which is a large problem to
   take on before the first screen ships.
8. **Authentication ships in the first milestone**, not after a screenless spine.
   Web sub-project A could defer screens because the web app already runs; here the
   tree is replaced wholesale, so the spine must be proven against the real backend
   early.

## Consequences

- The mobile dependency upgrade recorded as blocked in `docs/work-register.md` §1.1
  is resolved by obsolescence: `flutter_bloc ^8`, `get_it ^7`, `go_router ^14`,
  `hive ^2` and `retrofit >=4 <5` are not carried into the new project.
- A Flutter SDK (3.44.8 stable, matching CI) is now installed on the maintainer's
  machine, so mobile changes are verified locally instead of only by CI round-trips.
  This removed the constraint that made §1.1 blocked in the first place.
- Mobile CI is rewritten and gains a `dart format` gate, a coverage run and a
  generated-code freshness check. The `packages/**` path trigger is removed.
- Sub-project D is brought forward ahead of sub-project B (design system). B's
  output will land against a real architecture rather than against a mock scaffold.
- Two things the backend leaves undefined now block specific mobile screens rather
  than being abstract gaps: the Supabase email-link parameter format (blocks the
  verification screen; owner action in M0) and what belongs in `persons.avatar_url`
  (blocks avatar handling in M2/M3). Both are recorded as risks R2 and R4 in the
  spec.
- Everything deleted remains in git history and is recoverable.

## Alternatives considered

**Refactor the scaffold in place.** Rejected: there is nothing load-bearing to
preserve, and the two-"domain"/two-DI structure would have to be dismantled anyway.
The refactor would cost more than the rebuild and end somewhere worse.

**Keep BLoC.** Rejected. BLoC is a sound choice and the existing docs assume it, but
for an application that is mostly paginated reads it requires an event, a state, a
cubit and their tests per screen to reproduce what an `AsyncNotifier` gives in one
class — with no caching or invalidation model included. The consistency argument
with the web client's TanStack Query usage decided it.

**Full offline-first.** Rejected for now; see consequence 7 above.

**A shared `packages/family_roots_core` Dart package.** Rejected: web is Next.js, so
there is no second Flutter surface to share with. Notably, this is the very package
Mobile CI referenced for five months without it ever existing.
