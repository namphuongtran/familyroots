# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first: it compiles, but it has never run

The mobile app is a **rebuild**, not a working app with gaps. The previous
BLoC/`get_it`/Retrofit/Hive scaffold was **deleted wholesale** in `dde6116`
(183 files, 3,342 lines) and rebuilt on Riverpod 3 per
[ADR-034](../docs/decisions/034-mobile-riverpod-rebuild.md).

**M0 Tasks 1–19 have landed** (#136, #138, #147, #148, #149, #150). `lib/main.dart`
exists and CI builds `app-debug.apk`. **Task 20 has not happened**, and it is the
task that makes M0 done: running on a device against the real backend and walking
the acceptance list in the plan's Task 20 step 3.

So be precise about what is proven. Everything here is verified against **canned
transports and a fake-async widget tester**. `Supabase.initialize` and
`SentryFlutter.init` need platform channels and have therefore **never executed**.
Treat login, token refresh against real Supabase, and session survival across a
relaunch as *unverified* until that walk happens.
[`docs/work-register.md`](../docs/work-register.md) §2.2 lists the blockers — no
device or emulator, no credentials, no test accounts.

Authoritative sources, in order:

| Source | What it owns |
|---|---|
| [`docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`](../docs/superpowers/specs/2026-08-02-mobile-architecture-design.md) | the design and its rationale (decisions D1–D9) |
| [`docs/superpowers/plans/2026-08-02-mobile-m0-spine.md`](../docs/superpowers/plans/2026-08-02-mobile-m0-spine.md) | the 20 M0 tasks, with literal code and verified gotchas |
| [`docs/work-register.md`](../docs/work-register.md) §2.2 | which tasks have landed, and where to resume |

## R1: run `build_runner` or CI will fail — read this before editing anything

Riverpod, freezed and json_serializable all generate code, and **that generated
code is committed**. After touching any `@riverpod`, `@freezed` or
`@JsonSerializable` declaration you must run:

```bash
dart run build_runner build
```

CI re-runs it and fails on `git diff --exit-code`, naming the stale file. This is
the mitigation for spec risk R1: it turns "forgot to run build_runner" from a
mysterious local error into a named CI failure.

`--delete-conflicting-outputs` **no longer exists** — it was removed in
build_runner 2.15.x and now errors with "These options have been removed and were
ignored". Do not add it back.

## Commands

```bash
flutter pub get                                    # install deps
flutter test                                       # full suite (128 tests)
flutter test --exclude-tags golden                 # what CI runs (126)
flutter test test/core/network/api_client_test.dart   # single file
flutter test --plain-name "describes the case"     # single test by name
flutter test --update-goldens test/goldens/        # re-baseline goldens (macOS only)
flutter analyze                                    # lint
dart format lib test                               # format
dart run build_runner build                        # regen freezed/riverpod/json code
dart run build_runner watch                        # watch mode
flutter gen-l10n                                   # regenerate AppLocalizations from .arb
```

### Running the app

Every secret arrives by `--dart-define`; none is committed. There is no `.env`.

```bash
flutter run -d <device-id> \
  --dart-define=API_BASE_URL=http://<your-lan-ip>:8000/api/v1 \
  --dart-define=SUPABASE_URL=<url> \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<key> \
  --dart-define=SENTRY_DSN=<dsn>
```

`API_BASE_URL` defaults to `http://10.0.2.2:8000/api/v1` — the Android emulator's
alias for the host's localhost. A **physical device needs your machine's LAN
address**, and the backend must be started with `--host 0.0.0.0`, because the
default binds loopback only and a phone cannot reach it.

Toolchain is pinned: **Flutter 3.44.8 / Dart 3.12.2**, installed locally at
`~/development/flutter/bin` — the version `subosito/flutter-action@v2` resolves
for `channel: stable`. Prepend it to `PATH` before any of the above:

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
```

Mobile changes are **verified locally before push**, not by CI round-trip.

### Quality gate — run before claiming any task done

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && dart run build_runner build && git diff --exit-code \
  && flutter analyze && flutter test
```

`git diff --exit-code` after `build_runner` is not optional: **generated code is
committed**, never gitignored, and CI fails on a diff.

## Architecture

Riverpod 3 for both state and DI, feature-first slices, a pure-Dart domain.

```
lib/
├── main.dart                     # entry point: --dart-define config + overrides
├── app/
│   ├── app.dart                  # MaterialApp.router; bridges Riverpod → router
│   ├── bootstrap.dart            # Supabase + Sentry init, then runApp
│   └── router/
│       ├── app_router.dart       # AuthRouteState, guards, clanPickRequired
│       └── routes.dart           # paths, route keys, provider-bound wrappers
├── core/
│   ├── network/
│   │   ├── api_client.dart       # getOne/getPage/post — the Dio wrapper
│   │   ├── envelope.dart         # unwrapData, unwrapPage
│   │   ├── api_exception.dart    # sealed taxonomy + policyActionFor
│   │   ├── token_refresher.dart  # single-flight refresh
│   │   ├── dio_provider.dart     # the single Dio + its five interceptors
│   │   └── interceptors/         # auth, clan, locale, trace, refresh
│   ├── observability/            # traceparent.dart
│   ├── storage/                  # secure_session_store, prefs_store, cache_store
│   ├── theme/                    # tokens (ThemeExtension), app_theme
│   └── l10n/                     # app_vi.arb, app_en.arb, generated/
├── domain/                       # pure Dart — no flutter, dio, riverpod, supabase
│   ├── shared/                   # historical_date, page, ids
│   ├── auth/                     # user_profile
│   └── clan/                     # clan_membership, ClanRole
├── features/<slice>/             # auth, clan
│   ├── <slice>.dart              # the slice's public surface
│   ├── data/                     # DTOs, repositories
│   ├── application/              # Riverpod notifiers
│   └── presentation/             # screens, widgets
└── shared/widgets/               # error_view
```

M1–M4 add the remaining `domain/` aggregates (person, kinship, event, document,
capability) and their slices; the shape above does not change.

### State, DI, routing, networking

- **State + DI**: `flutter_riverpod` with `riverpod_generator` codegen. There is
  **no second DI container** — no `get_it`, no `injectable`. Two containers in
  one app was the old scaffold's debt (spec D1). `@riverpod` function = a cached
  read; `@riverpod class …Notifier` = paginated lists and mutations.
- **Routing**: `go_router`.
- **Network**: `dio`, reached **only** through `ApiClient`. Nothing above
  `core/network` may see a `DioException` or a `{"data": …}` wrapper.
- **Auth**: `supabase_flutter`. Session at rest goes to Keychain/Keystore via
  `SecureSessionStore`; the PKCE code verifier gets its own `SecurePkceStore`,
  because the default leaves it in SharedPreferences plaintext.
- **Local storage**: `sqflite` read cache (`CacheStore`) + `shared_preferences`
  for non-secrets (selected clan, locale). No Hive.
- **Observability**: `sentry_flutter`; W3C `traceparent` on every request
  (ADR-033) so a phone crash links to the exact backend log line.

### Dependency rules (spec §3.1)

| Layer | May import | Must not import |
|---|---|---|
| `domain/**` | `domain/**`, `dart:*` | `package:flutter/*`, dio, riverpod, supabase, json_annotation |
| `features/*/data` | `domain`, `core/network`, `core/storage` | flutter, any `presentation`, another slice |
| `features/*/application` | own `data`, `domain`, `core` | any `presentation`, another slice's internals |
| `features/*/presentation` | own `application`, `domain`, `shared/widgets`, `core/theme`, `core/l10n` | own or any `data` — no direct transport |
| `features/A` | `features/B` **only via `b.dart`** | `features/b/data/…`, `features/b/application/…` |
| `app/**` | slice public surfaces, `core` | any `data` |
| `core/**` | `core`, `domain` | any `features/**` |

All of it is enforced by `test/architecture/layer_boundaries_test.dart` (spec D9),
which parses the import directives of every file under `lib/` and fails on a
violation. It is a test, not a convention — you cannot merge past it.

### Non-negotiable rules

These are enforced by tests or by review. Breaking one is a bug, not a style choice.

- **`domain/**` must not declare `part '*.g.dart'`.** `freezed_annotation`
  re-exports all of `json_annotation`, so `@JsonSerializable` is already in
  scope inside the domain through an import it legitimately needs — the import
  ban alone does not close this hole. Map DTOs to domain types in
  `features/*/data` instead.
- **The envelope is unwrapped in exactly one place**: `core/network/envelope.dart`.
- **`policyActionFor(code)` is the only error-code → routing mapping.** Branch
  on `code`, never on `message`. `message` arrives already localised from
  `Accept-Language` — display it directly, never parse or re-translate it.
- **`HistoricalDate` owns its own render rule** (`date` when
  `precision == "exact"`, else `display`, falling back to `date`). No widget
  re-implements it.
- **Cursors are opaque.** Never parsed, constructed or repaired. On
  `400 invalid_cursor`, drop the cursor and refetch page one.
- **Presigned URLs are never persisted** to any local store (TTL 3600s).
- **đời (`generation`) is backend data** — never derived client-side. `null`
  renders honestly as "đời ?".
- **No user-facing string is hardcoded.** Everything through ARB.

### Backend contract

Every clan-scoped request carries:

- `Authorization: Bearer <supabase-jwt>` — `AuthInterceptor`
- `X-Current-Clan-Id` — `ClanInterceptor`, **only on clan-scoped routes**
- `Accept-Language` — `LocaleInterceptor`
- `traceparent` — `TraceInterceptor`

`isClanScoped(path)` in `clan_interceptor.dart` is the single source of truth for
which routes are exempt: `/auth/*`, `/me/clans*`, `/platform/*`, and
`/invitations/{token}/accept`. The clan header is sent even for single-clan users
so behaviour does not change the day someone joins a second clan.

Every 2xx body is `{"data": ...}`; cursor lists add
`"meta": {cursor, has_more, limit}`. Date fields are `HistoricalDate` objects
`{date, precision, display, lunar}`. `docs/contracts/*` is the authoritative
spec — read it before changing any request/response shape.

On 401: one shared refresh (concurrent 401s queue behind it), retry the original
request **exactly once**, never loop; a failed refresh signs out. A
caller-initiated cancellation is rethrown unchanged, never reported as an auth
or network failure.

## Package versions — do not float

**`flutter_riverpod` is 3.3.1, not 3.4.2, on purpose.** Every pin in
`pubspec.yaml` is exact, and the set is **an all-stable line that resolves** —
not each package's newest release. Do not "helpfully" upgrade one: the versions
are coupled through `analyzer`, and bumping any of them breaks resolution
outright rather than degrading.

Root cause: Flutter 3.44.8 hard-pins `meta: 1.18.0`. `analyzer` ≥13.1.0 requires
`meta ^1.18.3`. And `flutter_test` pins `test_api 0.7.11`, which caps `analyzer`
below 13.0.0 in any package that also depends on `test`.

| Wanted (spec §4.7) | Why it cannot resolve | Landed |
|---|---|---|
| `custom_lint` 0.8.1 | Needs `analyzer ^8`; `freezed` 3.2.5 needs `>=9 <11`; `riverpod_lint` 3.1.8 needs `^13`. Mutually impossible — and `riverpod_lint` 3.1.3 does not depend on it at all. | **removed entirely** |
| `riverpod_generator` 4.0.8 | `>=4.0.6` needs `analyzer ^13`, which `flutter_test`'s `test_api 0.7.11` forbids. | **4.0.3** |
| `riverpod_lint` 3.1.8 | Needs `analyzer ^13` — same wall. | **3.1.3** |
| `flutter_riverpod` 3.4.2 / `riverpod_annotation` 4.0.6 | Fine standalone, but `riverpod_lint` pins `riverpod` **exactly** (3.1.3 → 3.2.1). Keeping codegen + lint forces the matching runtime. | **3.3.1 / 4.0.2** |
| `build_runner` 2.16.0 | `>=2.15.2` needs `analyzer >=13.3.0`, which needs `meta ^1.18.3` — conflicts with the SDK's `meta 1.18.0`. | **2.15.1** |
| `json_serializable` 6.14.1 | Needs `analyzer >=10`; the analyzer-9 line that keeps `freezed` 3.2.5 stable caps it. | **6.13.0** |
| `intl` 0.20.3 | `flutter_localizations` from the SDK depends on `intl 0.20.2` exactly. | **0.20.2** |

`freezed` **3.2.5** is preserved exactly. The alternative analyzer-12 line also
resolves, but only with `freezed 3.2.6-dev.1` — a **prerelease**. This project
chose all-stable. If you ever prefer newer Riverpod over stable freezed, that is
the one-line swap.

Accepted consequence: analyzer 9 lags the SDK, so `build_runner` prints
`SDK language version 3.12.0 is newer than analyzer language version 3.11.0`.
It is a warning, codegen succeeds, and every gate is green. Revisit when `freezed`
ships a stable release on analyzer ≥12.

`flutter pub outdated` reporting ~31 newer packages is expected, not a problem to
fix.

## Localization (l10n)

`l10n.yaml` drives generation: ARB files in **`lib/core/l10n/`**, template
**`app_vi.arb`**, output class `AppLocalizations` into `lib/core/l10n/generated/`.

**`vi` is the default and the fallback locale**, not `en`. M0 ships `vi` and `en`,
but **no code may assume the locale set is exactly two**.

### Adding a string

1. Add the key + Vietnamese value to `lib/core/l10n/app_vi.arb` (the template).
2. Add the same key + English value to `lib/core/l10n/app_en.arb`.
3. Run `flutter gen-l10n`. Never hand-edit anything under `generated/`.
4. Use it:

```dart
final l10n = AppLocalizations.of(context);
Text(l10n.myKey);
```

Parameters and plurals:

```jsonc
"greeting": "Xin chào, {name}"
"itemCount": "{count, plural, =0{Không có mục nào} =1{1 mục} other{{count} mục}}"
```

## Testing

Tests are written **before** the implementation — the plan's tasks are ordered
that way, and a test that has never been seen failing has not been verified.

Six layers, each with its own method (spec §5):

| Layer | Method |
|---|---|
| domain | pure unit tests, no Flutter binding — date rendering, đời display, kinship, capability |
| network | envelope, pagination, every error code, single-flight refresh, retry-exactly-once |
| repository | DTO → domain mapping, from JSON **copied verbatim from `docs/contracts/`** |
| application | `ProviderContainer` with fake repositories |
| presentation | widget tests with `ProviderScope` overrides; goldens at text scale 1.0 and 2.0 |
| architecture | the import-boundary scan (D9) |

Four test-host traps, all of which have already cost time here:

- **`sqflite` has no implementation under `flutter test`** — it throws
  `Bad state: databaseFactory not initialized`. Any test touching it must call
  `sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` in `setUpAll`.
  `inMemoryDatabasePath` is *shared across opens in one process*, so delete it
  in `setUp` or tests leak state into each other.
- **`testWidgets` bodies run in a fake-async zone**, where sqflite's FFI I/O
  never completes — opening a real database inside a widget test **hangs** rather
  than failing, which looks like an infinite loop in your own code. Use an
  in-memory `CacheStore` fake there (see `test/app/wiring_test.dart`). Plain
  `test()` bodies are unaffected.
- **`flutter test` renders a weight-insensitive placeholder font** unless the real
  ones are registered. Any golden or layout assertion must call `loadAppFonts()`
  in `setUpAll`, or it passes vacuously against any font — including none.
- **Platform channels are unavailable**, so Keychain/Keystore behaviour cannot be
  tested here. `flutter_secure_storage` is faked with `mocktail` and the contract
  asserted instead; real device behaviour is M0 Task 20.

Use `test/support/sequence_adapter.dart` — **not `http_mock_adapter`** — whenever
a test needs a *sequence* of responses. http_mock_adapter 0.6.1 fixes the status
code at registration, `replyCallback` varies only the body, and duplicate
registrations do not queue (the matcher keeps the **last** match), so it cannot
express "401 then 200".

**Goldens are excluded from CI** (`flutter test --exclude-tags golden`). Golden
images are host-renderer sensitive and the baselines in `test/goldens/goldens/`
were rendered on macOS, so on CI's Linux runner they would fail for a reason that
says nothing about the code. Re-baseline locally with
`flutter test --update-goldens test/goldens/` and **look at the 2.0 image** before
accepting it. To bring them into CI, generate baselines in a Linux container.

## UI: Arbor Heritage design system — mandatory

Organic, premium editorial feel. Encoded as theme tokens in `core/theme/tokens.dart`
as a `ThemeExtension`, with `ThemeData` built *from* the tokens — so no widget
hardcodes a colour or a radius. Reach them with `context.tokens`.

- **No-line rule** — no 1px solid borders for sections or separation. Express
  boundaries with subtle background shifts (`surface-container-low` on
  `surface`). Exception: high-contrast accessibility mode → `outline_variant` at
  15% opacity.
- **Typography** — **Plus Jakarta Sans** for headings, display, storytelling,
  person names, branch titles; **Manrope** for body, labels, data. Fonts are
  **bundled as assets and never fetched at runtime**.
- **Shape** — soft, highly rounded: `9999px` for primary buttons, `2rem` for
  nodes. Never `sm` or `none`.
- **Depth** — no rigid drop shadows; ambient depth (e.g. 32px blur at 6%
  opacity). Glass rule: floating cards and nav bars are `surface` at 80% opacity
  with 20px backdrop blur.
- **Color** — never `#000000`. Primary text is `on_surface` (`#1d1b16`).
- **Layout** — no rigid grids unless the data is tabular. Layouts must survive
  **200% text scale**; goldens run at scale 1.0 and 2.0.

The design system itself — tokens, components, accessibility rules and the 15
screen groups — is specced in
[`docs/superpowers/specs/2026-08-02-design-system-and-screens.md`](../docs/superpowers/specs/2026-08-02-design-system-and-screens.md)
(sub-project B). Tracking drift between mockups and shipped screens is
deliberately **out of scope** for this milestone (spec §7).
