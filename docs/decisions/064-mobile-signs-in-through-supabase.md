# ADR-064: Mobile Signs In and Out Through Supabase, So Every Request Carries the Session Sign-In Created

## Status

Accepted (2026-10-10). Resolves issue #204, "Mobile sign-in discards its tokens, so the first
authenticated request carries no bearer token". The maintainer took the decision in § 1 in triage
on 2026-10-10. The rest of this ADR records what building it decided.

**This ADR ships with its code**, in the same pull request. Readings were taken on **2026-10-10**
at `9fb59a4` on `main`, before the change. gotrue readings are of the 2.26.0 source, the version
`mobile/pubspec.lock` resolves. **Nothing here has run on a device or against hosted Supabase**:
mobile M0 has never run on one (`mobile/CLAUDE.md`, "Read this first"). The tests below prove the
chain with a real Supabase auth client over a faked HTTP transport, and no further.

## Context

### The defect

`SessionController.signIn` called `POST /auth/login`, discarded the `LoginResult` that held the
access and refresh tokens, and called `GET /auth/me`
(`mobile/lib/features/auth/application/session_controller.dart:27-28`). But every request read its
bearer token from the Supabase client: `accessTokenProvider` was
`() => Supabase.instance.client.auth.currentSession?.accessToken` (`mobile/lib/main.dart:47-49`),
and nothing ever gave that client a session. `AuthInterceptor` adds the header only when the token
is non-null (`core/network/interceptors/auth_interceptor.dart:10-13`), so it was silently left off.
`GET /auth/me` would answer 401 `missing_token` (`backend/app/core/security.py`), the refresh would
find no session, and `onSignOut` would fire.

### Why no test saw it

- `test/support/main_container.dart:58` stubbed the token provider to `() => null`.
- `:78-83` swapped `dioProvider` for a bare `Dio` with **no interceptors** whenever a test passed an
  adapter, and every sign-in test passed one.
- The canned `/auth/me` in `test/app/membership_route_test.dart:107-111` answered 200 whatever the
  headers were.

### One more defect on the same path, read at source and not run

`signOut` called `POST /auth/logout`, which needs a bearer token. With no session, that request 401s,
`RefreshInterceptor` refreshes, the refresh throws because there is no session, and it calls
`onSignOut`, which is `signOut` again. Each turn sends another `POST /auth/logout`. Until this ADR,
every sign-in ended in that state.

## Decision

### 1. Sign-in goes to Supabase directly, as on the web

`signIn` calls Supabase's password sign-in, then `GET /auth/me` as before. It does **not** keep
`POST /auth/login` and hand the returned tokens to the Supabase client with `setSession`:

- Both clients get one sign-in path. The web's is ADR-061 § 7.
- The session is created by the client that stores it (`SecureSessionStore`, spec D6) and
  refreshes it (`refreshSession()`, spec D8).
- ADR-061's last "Alternatives considered" row already rejected that hand-over for the web.

### 2. One `SupabaseAuth` serves sign-in, the bearer token, the refresh and sign-out

`features/auth/data/supabase_auth.dart` wraps a `GoTrueClient`. `main.dart` builds **one** on
`Supabase.instance.client.auth` and wires all four seams from it: `accessTokenProvider` reads
`auth.accessToken`, `tokenRefresherProvider` runs `auth.refresh`, and the new `supabaseAuthProvider`
hands it to `SessionController`. The token a request carries and the session sign-in made cannot
come from two places.

It imports `package:gotrue`, which `pubspec.yaml` now pins at 2.26.0, the version already
resolved. That keeps a Flutter plugin out of the data layer. The domain layer imports no Supabase
package, and the layer-boundaries test gains no exemption.

### 3. gotrue's exceptions stop at `SupabaseAuth`, and the copy is ours

`SupabaseAuth` is the one place gotrue's `AuthException` is caught, as `ApiClient` is for
`DioException`. A refusal becomes `SupabaseAuthException`, a new member of the sealed
`AppException` taxonomy carrying GoTrue's `code`, the status, and the address. No answer at all
becomes `NetworkException`.

The exception carries no message. GoTrue writes English whatever the locale, so `ErrorView` picks
the copy by code. `invalid_credentials` shows the new ARB key `errorInvalidCredentials`, whose words
are the backend's `auth.invalid_credentials` (`backend/app/i18n/vi.json:106`), so the person reads
what they read before. Any other code shows `errorUnexpected`.

### 4. `email_not_confirmed` reaches `/verify-email`, and the router checks it first

`policyActionFor` maps `email_not_confirmed` to `resendVerification`, beside the backend's
`email_not_verified`. The app shell sets `AuthRouteState.emailVerified` from that action, for a
`SupabaseAuthException` or an `ApiException` alike. Until now nothing in `mobile/lib` set it false.

Supabase refuses the sign-in itself, so this state has **no session**. The redirect therefore
checks `emailVerified` before `signedIn`; checked after, the route stayed unreachable. A signed-out
person may stay only on `/login`, so the sign-out button `MessagePage` always offers leaves
`/verify-email`. The address comes from the refusal, because there is no profile to read it from,
and `/verify-email` offers its resend to it.

### 5. A sign-in the backend refuses leaves no session

If `GET /auth/me` fails after Supabase said yes, for example with 403 `account_deactivated`,
`signIn` signs the Supabase session out before it reports the error. `supabase_flutter` persists
whatever session the client holds, so without this a half-signed-in session would stay in the
Keychain or Keystore. The revoke goes to GoTrue's `/logout` directly, so it works for a deactivated
account too, which `POST /auth/logout` refuses with 403 (`docs/architecture/auth-flow.md`).

This cleanup revokes **this device's session only** (scope `local`). The failure may be a passing
5xx or a timeout, and the person's other sessions, the web's included, did nothing wrong.

### 6. Sign-out goes to Supabase too, with scope `global`

`signOut` calls the SDK's `signOut(scope: SignOutScope.global)` and no longer calls
`POST /auth/logout`. `global` keeps what the backend did (`sign_out(..., "global")`) and matches
supabase-js's default, which the web calls. gotrue drops the local session before it sends the
revoke, so a failed revoke changes nothing a later request could carry, and `signOut` never throws.
It catches any error, not only gotrue's: gotrue also clears the PKCE verifier from secure storage
on the way, and a platform error there must not leave the app showing a session it no longer has.

A sign-out is no longer a backend request, so § Context's loop cannot start: `onSignOut` can no
longer cause the request that calls it.

### 7. The backend-login code is deleted

`AuthRepository.login`, `LoginResult`, `loginResultFromJson` and `AuthRepository.logout` are gone,
with the tests that pinned them. `auth_repository_test.dart`'s rate-limit case rode on `login`; it
now rides on `resendVerification`, which shares the `/auth/*` bucket.

## How it is tested

The reading is a request on the wire, never a setter (`.claude/rules/testing.md`):

- **The Supabase client is real.** `test/support/fake_gotrue.dart` builds a `GoTrueClient` whose
  `httpClient` is `package:http`'s `MockClient`. gotrue 2.26.0's constructor takes one, so the
  issue's fallback, a fake seam, was not needed.
- **The Dio is real.** `mainContainer(adapter:)` keeps all five interceptors and swaps only the
  transport, through `buildDio`, the body `dioProvider` now names.
- **Canned backend answers can demand the token.** `Canned(…, bearer:)` answers 401 as
  `get_current_user` does unless the request carries that token. The membership suite uses it.

`test/app/sign_in_session_test.dart` holds the readings the issue named, each seen to fail on
2026-10-10 against its plant:

| Reading | Plant | Failing reading |
|---|---|---|
| `GET /auth/me` carries `Bearer <the token the fake issued>` | no Supabase sign-in | `null` for `'Bearer gotrue-issued-access-token'` |
| after sign-out, a request carries no `Authorization` | no Supabase sign-out | `'Bearer gotrue-issued-access-token'` for `null` |
| after a refused `/auth/me`, a request carries none | no cleanup | the same |
| that cleanup's revoke is scope `local` | scope `global` | `'global'` for `'local'` |
| a wrong password shows `Email hoặc mật khẩu không đúng` | no `invalid_credentials` copy | no such text |
| `email_not_confirmed` renders `/verify-email`, and its resend asks for that address | no mapping; the check after `signedIn`; no address from the refusal | no `/verify-email`; no resend button |

With no sign-in and the membership suite's canned answers ungated, as before, that suite passed 4 of
4. Gated, it fails 4 of 4.

## Consequences

Easier:

- One sign-in path for both clients, and one auth object for every seam on mobile.
- `/verify-email` is reachable from a real sign-in for the first time.
- A test that signs in can no longer pass while the app sends no token.

Harder:

- No first-party client calls `POST /auth/login`, `POST /auth/logout` or `POST /auth/refresh`
  now. They stay, and their contract with them.
- The copy for a GoTrue refusal is ours, so a new GoTrue code reads `errorUnexpected` until someone
  gives it words. A 429 `over_request_rate_limit` does today.
- A person held on `/verify-email` with no session leaves it through a button labelled "Đăng xuất",
  because `MessagePage` offers only sign-out.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep `POST /auth/login` and hand its tokens to the client with `setSession` | Two sign-in paths, and the session is not created by the client that stores and refreshes it. ADR-061 rejected it for the web |
| A fake seam above gotrue instead of a real client over a fake transport | Allowed by the issue only if gotrue took no HTTP client. It takes one, and a fake seam would not run gotrue's own parsing of the refusal |
| Keep `POST /auth/logout`, sent before the Supabase sign-out while the token still exists | Two sign-out paths, and the no-session loop stays reachable whenever the token is gone |
| `SignOutScope.local`, gotrue-dart's default, for the sign-out a person asks for | Narrower than what the backend did and what the web does |
| `SignOutScope.global` for § 5's cleanup too | A passing 5xx on `/auth/me` during a phone sign-in would sign the person out of the web |
| Import `supabase_flutter` in the data layer | A Flutter plugin in a layer `mobile/CLAUDE.md` keeps free of Flutter. `gotrue` is the same code without it |

## What this ADR deliberately does not decide

- **Whether to delete `POST /auth/login`**, now that neither first-party client calls it.
- **Session restore on a cold start.** `SessionController.build` still returns null.
- **OAuth sign-in on mobile**, and **the resend action** itself.
- **The device walk.** Signing in against hosted Supabase stays unverified until M0 Task 20.

## Related

- [ADR-061](061-the-auth-session-is-server-state-and-access-is-routed-on-the-server.md) § 7: the web's
  Supabase-direct sign-in and the rejected hand-over.
- [ADR-034](034-mobile-riverpod-rebuild.md) and the mobile spec,
  `docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`, § 4.2 and § 4.3, amended here.
- `docs/contracts/frontend-integration-guide.md` § 1.1 and § 2, amended here.
