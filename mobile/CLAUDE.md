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
The blockers are known: no device or emulator, no credentials, and no test accounts.

Authoritative sources, in order:

| Source | What it owns |
|---|---|
| [`docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`](../docs/superpowers/specs/2026-08-02-mobile-architecture-design.md) | the design and its rationale (decisions D1–D9) |
| [`docs/superpowers/plans/2026-08-02-mobile-m0-spine.md`](../docs/superpowers/plans/2026-08-02-mobile-m0-spine.md) | the 20 M0 tasks, with literal code and verified gotchas |

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
flutter test                                       # full suite (134 tests)
flutter test --exclude-tags golden                 # what CI runs (132)
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
- **`testWidgets` bodies run in a fake-async zone**, and anything needing a real
  event-loop turn never completes there. It **hangs** rather than failing, which
  looks like an infinite loop in your own code. Plain `test()` bodies are
  unaffected. Two instances have cost time here:
  - **sqflite's FFI I/O.** Opening a real database inside a widget test hangs.
    Use an in-memory `CacheStore` fake — `FakeCacheStore` in
    `test/support/main_container.dart`.
  - **A `dio` request, even through a canned adapter that does no I/O at all.**
    Measured 2026-08-26: `await`ing
    `SessionController.signIn()` directly in a `testWidgets` body hung for **25
    minutes** with no output, `flutter_tester` at 0% CPU, and the per-test
    timeout never fired, because the fake clock only advances when the tester
    pumps and an `await` never pumps. Wrap the call in
    `await tester.runAsync(…)` and pump after it; the same test then finished
    in **under a second** (2026-08-27). Two follow-on effects, both measured
    2026-08-27 and both real: a provider that fires its own request back inside
    the zone never reaches the adapter at all (`GET /me/clans` from
    `clanPickRequiredProvider` is never recorded), and a route that shows a
    `CircularProgressIndicator` while it waits makes `pumpAndSettle` **time
    out** instead of failing on your assertion — resolve that provider inside
    the same `runAsync` block. `test/app/membership_route_test.dart` is the
    worked example.
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
  15% opacity. **The theme enforces this, it does not merely describe it:**
  `dividerTheme` sets `color: Colors.transparent`, so a `Divider` a screen adds
  by accident paints nothing and occupies nothing. See note 6.
- **Typography** — **Plus Jakarta Sans** for headings, display, storytelling,
  person names, branch titles; **Manrope** for body, labels, data. Fonts are
  **bundled as assets and never fetched at runtime**.
- **Shape** — soft, highly rounded: `9999px` for primary buttons, `2rem` for
  nodes. Never `sm` or `none`.
- **Depth** — no rigid drop shadows; ambient depth (e.g. 32px blur at 6%
  opacity). Glass rule: floating cards and nav bars are `surface` at 80% opacity
  with 20px backdrop blur.
- **Color** — never `#000000`. Primary text is `on_surface` (`#1d1b16`).
  `primary` is the leaf green `#3E5C38` and the page ground is `#FBF8F1`. Both are
  [ADR-041](../docs/decisions/041-primary-green-heritage-family-single-background.md)'s
  values and they bind web too. See the four notes below.
- **Layout** — no rigid grids unless the data is tabular. Layouts must survive
  **200% text scale**; goldens run at scale 1.0 and 2.0.

### The palette is the spec's and ADR-041's, and six things about it are load-bearing

Landed on 2026-08-22 and extended three times the same day. Each note exists because the obvious
move is wrong.

**1. `surface` is `#FBF8F1`, not the `#FDFCF7` mobile used to hold.** ADR-041 decision 3
picked the spec's value over *both* incumbents on purpose, so that no client has to
re-open the question. Mobile's `#FDFCF7` was sourced by nothing: it appears in no spec
section and in no ADR. Web's `background` is now the same `#FBF8F1` under the same name,
so the two clients paint one page ground. Contrast is unharmed: `on_surface` `#1D1B16`
measures 16.22:1 on it, `primary` measures 7.09:1, and `error` measures 7.07:1, all
computed 2026-08-22 with the WCAG 2.1 relative-luminance formula. The `error` figure is
note 4's new value; the `#8C1D18` it replaced measured 8.59:1 on the same ground.

**2. `ColorScheme.fromSeed` does not return the seed, so every token it owns is passed
explicitly.** This is the trap that made the primary change nearly cosmetic. `fromSeed`
re-derives its argument into a Material tonal palette. Measured 2026-08-22: the bronze
seed `#7A5C2E` produced `scheme.primary` `#7E570F`, and the new green seed `#3E5C38`
produced `#3E6837`. Both are colours that exist in no token file, on an app whose whole
rule is that colours live in `tokens.dart` only. `buildAppTheme` therefore passes
`primary`, `onPrimary`, `surface`, `onSurface`, `surfaceContainerLow` and `error` as named
overrides; the seed now only fills the tones no token names. Spec §2.8 already required
this: "`ColorScheme` is populated from the same values so Material widgets inherit
correctly". `test/core/theme/theme_test.dart` pins every one of the six, so removing an
override turns red.

**`surfaceContainerLow` was the override the first pass missed, and a later one added it.** Measured
2026-08-22 before the fix: `scheme.surfaceContainerLow` was `#F2F5EB`, a green-tinted tone
the leaf-green seed derived, while the token said `#F5F1E6`. No shipped screen showed the
difference, because `cardTheme.color` and both widgets that draw a card ground read the
token directly. Every M3 widget that *defaults* to `colorScheme.surfaceContainerLow`, such
as `Drawer`, would have painted the derived tone. **When a token gains a `ColorScheme`
counterpart, pass it and pin it in the same change.** Checking one token tells you nothing
about the next one.

**3. Mobile has no `heritage` family yet, and adding one before a screen needs it was
rejected.** ADR-041 decision 2 creates `heritage` `#A3182F`, `heritage-foreground`
`#FFFFFF`, `heritage-container` `#F6DFE0` and `heritage-container-foreground` `#4A0A14`,
and it argues the container pair should ship ahead of its first consumer. That argument
is web-shaped and does not transfer: web's rename *removes* red from `primary`, so
without the family a ceremonial red would have no token at all the day web's rename lands.
Mobile's `primary` was a bronze, so this change takes no red away from anything. Against
that, a Flutter token is not a CSS variable — each colour must be threaded through a
hand-written `copyWith` and `lerp`, no screen renders it, and mobile has no equivalent of
web's `contrast.test.ts` sweep, so a wrong value would be invisible to every gate. Four
values no gate can check and no screen can show are the dead-token defect.

**So the rule is written here instead of in the code.** When the first thủy tổ marker,
giỗ chip, or ancestral-emphasis surface is built, that change adds the four fields to
`ArborTokens` *with* the widget and the golden that renders them, at ADR-041's values
above. **Never reach for `error` for a ceremonial red.** Since the 2026-08-22 fix that warning is
stricter, not weaker: `error` is now `#A32218` and `heritage` is `#A3182F`, one digit
apart, so the wrong token no longer looks wrong on screen. Only the meaning separates
them, and reaching for the nearest token is exactly what put red in web's `primary` and
cost an ADR to undo. `web/src/app/globals.css:45-48` carries the same warning for the same
pair.

**4. `surfaceContainerLow` and `error` are spec § 2.1's values, and mobile's originals were
sourced by nothing.** A 2026-08-22 change moved `surfaceContainerLow` from `#F5F1E6` to `#F4EFE4`
and `error` from `#8C1D18` to `#A32218`, both read at source on 2026-08-22. Neither
original appeared in the spec or in any ADR: `grep` found each of them in exactly two
places, `tokens.dart` and `docs/superpowers/plans/2026-08-02-mobile-m0-spine.md`, which is
the record of what was built rather than an authority on what it should be. That is the
same argument ADR-041 decision 3 made for `surface`, so it resolved the same way.

**The spec calls the role `danger`; Flutter calls it `error`, and mobile keeps `error`.**
`ColorScheme.error` is the field a Material widget reads, and one token spelled differently
from the field it feeds is a trap. ADR-041 decision 2 made the same call in the other
direction on web, keeping the repository's `-foreground` suffix over the spec's `on-`
prefix. The value is the spec's; only the spelling is this repository's.

**Contrast, computed 2026-08-22 with the WCAG 2.1 relative-luminance formula.** `error`
`#A32218` is a foreground in exactly one place, the message line of `ErrorView`
(`lib/shared/widgets/error_view.dart:41`), and the ground it renders on is
`surfaceContainerLow`, not `surface`. On the new `#F4EFE4` it measures **6.54:1**, and on
`surface` `#FBF8F1` it measures 7.07:1, which reproduces ADR-041's figure for
`destructive` on `background` exactly. Both clear the 4.5:1 body-text floor. White on
`#A32218` measures 7.50:1. The move costs contrast, from 7.95:1 on the same ground, and it
buys one red under one value across both clients.

**5. "No token reads it" and "no `ColorScheme` field takes it" are two different claims,
and `outlineVariant` is where they came apart.** A 2026-08-22 change moved `outlineVariant` from
`#CFC7B4` to spec § 2.1's `#B3A98F` on 2026-08-22, and passed it to `ColorScheme.fromSeed`.
Read at source that day: `mobile/lib/core/theme/tokens.dart:49` for the old value, and
`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:90` for the spec's. Like
note 4's two, `#CFC7B4` was sourced only by
`docs/superpowers/plans/2026-08-02-mobile-m0-spine.md:3151`, the record of what was built.

**The first claim is true and the second was false.** `grep -rn outlineVariant lib` still
returns five hits, all inside `tokens.dart`: the field, the factory, the declaration, the
`copyWith`, and the `lerp`. No widget reads the token. But `ColorScheme` **does** have an
`outlineVariant` field, `ColorScheme.fromSeed` **does** take it as a named argument, and
six Flutter 3.44.8 defaults classes read it: `_DividerDefaultsM3`
(`packages/flutter/lib/src/material/divider.dart:369`, backing both `Divider` and
`VerticalDivider`), `_OutlinedCardDefaultsM3` (`card.dart:394`), `_TabsPrimaryDefaultsM3`
and `_TabsSecondaryDefaultsM3` (`tabs.dart:2806` and `:2885`), `_ChipDefaultsM3`
(`chip.dart:2534`) and `_BannerDefaultsM3` (`banner.dart:516`). Measured 2026-08-22 before
the fix, `buildAppTheme().colorScheme.outlineVariant` was **`#C2C8BC`**, a green-tinted
tone the leaf-green seed derived, while the token said `#CFC7B4`. That is note 2's
`fromSeed` trap a **third** time, after `primary` and `surfaceContainerLow`. **Check the `ColorScheme` counterpart of every token, one at a time. The score so
far is three for three.**

**Deleting the field was the other live option, and this is why it lost.** Note 3 rejected
the `heritage` family as "values no gate can check and no screen can show". Both halves
fail here. A gate *can* check this one, because `ColorScheme` holds it, and
`test/core/theme/theme_test.dart` now pins both the token value and
`scheme.outlineVariant == t.outlineVariant`. And deleting the field would not have removed
the colour from the app: `ColorScheme.outlineVariant` would have stayed on the derived
`#C2C8BC` with nothing in the repository naming it. Note 3's rule is about **adding** a
token ahead of its consumer. This token already existed and already had a live framework
counterpart, so the symmetric question resolved the other way.

**The 15%-opacity condition is a rule about widgets, not about the value.** The no-line
rule above allows `outline_variant` only in high-contrast mode, at 15% opacity, and mobile
has no high-contrast mode. That is a reason no widget may draw a full-opacity line with it.
It is not a reason for the token to hold the wrong colour: a mode that renders it at 15%
needs a correct base value to take 15% of. Building that mode was explicitly out of scope for that
change, and is out of this note's.

**One gap this left open, which is not `outlineVariant`'s defect.** `app_theme.dart`'s
`dividerTheme` was `DividerThemeData(thickness: 0, space: 0)`, commented as implementing the
no-line rule, and `theme_test.dart` pinned `thickness == 0` under the name "dividers have no
thickness". Thickness zero is not absence. Flutter documents it at
`packages/flutter/lib/src/material/divider.dart:86-87`: "A divider with a [thickness] of
0.0 is always drawn as a line with a height of exactly one device pixel." Measured
2026-08-22 by pumping a bare `Divider` under `buildAppTheme()`:
`Divider.createBorderSide(context)` returns `color #B3A98F, width 0.0,
style BorderStyle.solid` — the token, because the theme set no divider colour — and the
widget lays out at `Size(800.0, 0.0)` because `space` is 0. So the theme picked the colour
of a line it believed it had suppressed. Whether that hairline is visible at zero height
was **not** measured pixel by pixel at the time. Deciding what the theme should do instead
changes rendering and is its own decision, so it was reported rather than folded in.
**It was closed on 2026-08-22. Note 6 is that answer.**

**Contrast, computed 2026-08-22 with the WCAG 2.1 relative-luminance formula**, using an
implementation checked against note 4's published figures (`onSurface` on `surface` 16.22:1
and `error` on `surfaceContainerLow` 6.54:1 both reproduced exactly). `#B3A98F` measures
**2.20:1** on `surface` `#FBF8F1`; the `#CFC7B4` it replaces measured 1.59:1 and the derived
`#C2C8BC` measured 1.61:1. So the spec's value is the more visible of the three and none of
them reaches the 3:1 non-text floor of WCAG 1.4.11. That floor governs the boundary of a
control a user must find; a section separator is decorative and exempt, and the spec puts
this role behind high-contrast mode at 15% anyway, which is fainter still. The figure is
recorded so the next reader does not have to re-derive it, not as a compliance claim.

**6. The theme now suppresses the divider line, and the test reads pixels instead of a
field.** Note 5's open gap was settled on 2026-08-22. `dividerTheme` gained
`color: Colors.transparent`; `thickness: 0` and `space: 0` stayed.

**The hairline was measured, and it is painted.** The earlier pass established the colour and the
layout but said plainly that it had not looked at pixels. The later one did. Method: put a real
`Divider` in a `Column` inside a `ColoredBox` inside a `RepaintBoundary`, so nothing else
paints in that subtree, then `toImageSync(pixelRatio: 3.0)` and read every pixel back as
raw RGBA. Over the page ground `#FBF8F1`, two raster rows changed, to `#D7D1C0` and
`#D7D0C0`. Over a dark `#102030` control ground the same two rows came back `#61645F` and
`#626560`. Both grounds show about 50% coverage on each of two rows, which is one device
pixel of ink antialiased across the boundary it straddles — exactly what Flutter's
"exactly one device pixel" sentence promises. **The result does not depend on the raster
scale:** at `pixelRatio: 1.0` it was rows 3 and 4 of 9, at `3.0` rows 11 and 12 of 27.

**How visible is faint enough to ignore? The question does not arise, and that is the
point.** Each painted row measures **1.44:1** against `surface`, computed with the same
WCAG 2.1 implementation note 5 used and validated the same way (it reproduces 16.22:1,
6.54:1 and 2.20:1 exactly). That is faint. But visibility is not a property the code can
hold: it moves with the ground the divider sits on, with the display, and with the device
pixel ratio. The no-line rule forbids **drawing the line**, not **noticing** it. So the
test asserts that no pixel changed, never that no pixel is conspicuous.

**Why suppress rather than stop claiming to.** Both branches were live and the seed named
them. Deleting `dividerTheme` is the honest-sounding one and it loses on arithmetic:
`_DividerDefaultsM3` (`material/divider.dart:359-370`, read 2026-08-22) supplies
`thickness: 1.0`, `space: 16` and `colorScheme.outlineVariant`, so the first accidental
`Divider` would then paint a full-opacity `#B3A98F` line **1.0 logical pixels** thick plus
16 pixels of gap, instead of a 1.44:1 hairline. Honesty would have been bought by making
the forbidden thing larger. Beyond that, "enforced by review at the widget layer" is what
already failed here: the comment claimed the theme did the job from the day it was written
(`0785036`, 2026-08-03) and nothing checked it for the 19 days until someone looked. This repository prefers a mechanism to a convention everywhere else — see the
import-boundary test — and a global visual mandate belongs in the one global place.

**Where high-contrast mode turns the line back on.** In this same field, and nowhere else.
The rule's exception is `outline_variant` at 15% opacity, which is
`DividerThemeData(color: t.outlineVariant.withValues(alpha: 0.15), thickness: 1)` in place
of the transparent one. That is why note 5 refused to delete the `outlineVariant` token: a
mode that renders it at 15% needs a correct base value to take 15% of. Building the mode
stays out of scope.

**`Colors.transparent` is not a colour, so it does not want a token.** `tokens.dart` owns
every colour the app paints. Transparent is the absence of paint. A token for it would be
a value no screen renders, which is note 3's dead-token defect. The literal guard in
`theme_test.dart` is unaffected: it matches `Color(0x…)` spellings, and this is a named
framework constant.

**One other widget reads this field, and the change is deliberate for it too.**
`DividerTheme.of(context)` has exactly four call sites in Flutter 3.44.8, found 2026-08-22
with `grep -rn "DividerTheme.of(" packages/flutter/lib/src/material/`: `Divider` twice
(`divider.dart:167` and `:187`), `VerticalDivider` (`:315`), and `SearchAnchor`'s search
view (`search_anchor.dart:1063`). No screen in `lib/` uses any of the three. If a search
view lands and wants its divider, it passes `dividerColor` on the widget, which wins over
the theme at `search_anchor.dart:1076-1080`.

**The test is the part worth copying.** The old assertion was
`expect(theme.dividerTheme.thickness, 0)` under the name "dividers have no thickness"
(`theme_test.dart:129,131` at commit `27a446f`). It was true, it was green, and it would have
stayed green the day a screen added its first `Divider`. **No screen ever added one**, checked
2026-08-22 and re-checked the same day: `grep -rn "Divider" mobile/lib` returns
14 lines and every one is the `orDivider` localisation key, a comment, or the `dividerTheme`
declaration itself. So nothing was painted on any screen, and the sentence "the app painted a line
the whole time" that this note used to carry was wrong. It is corrected here rather than deleted,
because it was cited. The replacement, "the no-line rule: a real
Divider paints no pixel", renders both `Divider` and `VerticalDivider` over two grounds and
asserts the set of distinct pixels is exactly `{ground}`. It also asserts each divider
measures `Size(9, 0)` or `Size(0, 9)`, so an accidental one is inert in layout as well as
in paint. Both halves were watched failing: removing `color` produced
`Actual: Set:['#FFFBF8F1', '#FFD7D1C0', '#FFD7D0C0']`, and setting `space: 16` produced
`Actual: _DebugSize:<Size(9.0, 16.0)>`.

**The general rule is written once, and not here.** A test that pins a setting cannot fail for the
reason anyone cares about. `.claude/rules/testing.md`, section "A test pins an outcome, not a
setting", holds it, with this instance, the `web` token probe, and the `backend` RLS coverage guard
beside it. That file loads in every session. This note keeps the Flutter-specific evidence and does
not restate the rule.

The design system itself — tokens, components, accessibility rules and the 15
screen groups — is specced in
[`docs/superpowers/specs/2026-08-02-design-system-and-screens.md`](../docs/superpowers/specs/2026-08-02-design-system-and-screens.md)
(sub-project B). Tracking drift between mockups and shipped screens is
deliberately **out of scope** for this milestone (spec §7).
