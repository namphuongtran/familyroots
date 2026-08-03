# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first: the app does not run yet

The mobile app is a **rebuild in progress**, not a working app with gaps. The
previous BLoC/`get_it`/Retrofit/Hive scaffold was **deleted wholesale** in
`dde6116` (183 files, 3,342 lines) and is being rebuilt on Riverpod 3 per
[ADR-034](../docs/decisions/034-mobile-riverpod-rebuild.md).

There is **no `lib/main.dart`** until M0 Task 18. `flutter run` will not work.
Mobile CI's APK step is guarded on `hashFiles('mobile/lib/main.dart')` and
reactivates by itself when that file lands.

Authoritative sources, in order:

| Source | What it owns |
|---|---|
| [`docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`](../docs/superpowers/specs/2026-08-02-mobile-architecture-design.md) | the design and its rationale (decisions D1–D9) |
| [`docs/superpowers/plans/2026-08-02-mobile-m0-spine.md`](../docs/superpowers/plans/2026-08-02-mobile-m0-spine.md) | the 20 M0 tasks, with literal code and verified gotchas |
| [`docs/work-register.md`](../docs/work-register.md) §2.3 | which tasks have landed, and where to resume |

**M0 progress: Tasks 1–10 landed** (#136, #138, #147). Tasks 11–20 remain:
11–12 fonts/theme + l10n, 13–17 auth and clan slices, 18 router/Dio/bootstrap,
19 CI rewrite, 20 device run against the real backend + doc sync.

## Commands

```bash
flutter pub get                                    # install deps
flutter test                                       # full suite (80 tests)
flutter test test/core/network/api_client_test.dart   # single file
flutter test --plain-name "describes the case"     # single test by name
flutter analyze                                    # lint
dart format lib test                               # format
dart run build_runner build                        # regen freezed/riverpod/json code
dart run build_runner watch                        # watch mode
flutter gen-l10n                                   # regenerate AppLocalizations from .arb
```

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
├── main.dart                     # bootstrap only                      (Task 18)
├── app/
│   ├── app.dart                  # ProviderScope + MaterialApp.router  (Task 18)
│   ├── bootstrap.dart            # Sentry, Supabase, cache, l10n init  (Task 18)
│   └── router/                   # app_router, auth_state, routes      (Task 18)
├── core/
│   ├── network/
│   │   ├── api_client.dart       # getOne/getPage/post — the Dio wrapper
│   │   ├── envelope.dart         # unwrapData, unwrapPage
│   │   ├── api_exception.dart    # sealed taxonomy + policyActionFor
│   │   ├── token_refresher.dart  # single-flight refresh
│   │   ├── dio_provider.dart     # the single Dio, wired               (Task 18)
│   │   └── interceptors/         # auth, clan, locale, trace, refresh
│   ├── observability/            # traceparent.dart; sentry.dart       (Task 18)
│   ├── storage/                  # secure_session_store, prefs_store, cache_store
│   ├── theme/                    # tokens, app_theme                   (Task 11)
│   └── l10n/                     # app_vi.arb, app_en.arb, generated/
├── domain/                       # pure Dart — no flutter, dio, riverpod, supabase
│   └── shared/                   # historical_date, page, ids
├── features/<slice>/             # auth, clan                          (Tasks 13–17)
│   ├── <slice>.dart              # the slice's public surface
│   ├── data/                     # DTOs, repositories
│   ├── application/              # Riverpod notifiers
│   └── presentation/             # screens, widgets
└── shared/widgets/
```

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

### Non-negotiable rules

These are enforced by tests or by review. Breaking one is a bug, not a style choice.

- **`domain/**` stays framework-agnostic.** No `package:flutter/*`, `dio`,
  `riverpod`, `riverpod_annotation`, `supabase_flutter`, or `json_annotation`.
  It may import only `domain/**` and `dart:*`.
- **`domain/**` must not declare `part '*.g.dart'`.** `freezed_annotation`
  re-exports all of `json_annotation`, so `@JsonSerializable` is already in
  scope inside the domain through an import it legitimately needs — the import
  ban alone does not close this hole. Map DTOs to domain types in
  `features/*/data` instead.
- **`core/` must not import `features/`.** `presentation/` must not import
  `data/`. Cross-slice imports go through `features/<slice>/<slice>.dart` only.
- All of the above are enforced by
  `test/architecture/layer_boundaries_test.dart` (spec D9) — it walks every file
  in `lib/`.
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

Every pin in `pubspec.yaml` is exact for a reason. The set is **an all-stable
line that resolves**, not each package's newest release:

- `freezed 3.2.5` needs `analyzer >=9 <11`; Flutter hard-pins `meta 1.18.0`.
- Letting pub choose freely selects `freezed 3.2.6-dev.1`, a **prerelease**.
- `custom_lint` is **deliberately absent** — current `riverpod_lint` no longer
  routes through it.

`flutter pub outdated` reporting ~31 newer packages is expected, not a problem to
fix. Re-check only when Flutter stable ships a newer `meta`/`analyzer`.

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

`flutter test` for the suite; a path or `--plain-name` for one test. Tests are
written **before** the implementation — the plan's tasks are ordered that way,
and a test that has never been seen failing has not been verified.

Two test-host limits worth knowing before you fight them:

- **`sqflite` has no implementation under `flutter test`** — it throws
  `Bad state: databaseFactory not initialized`. Any test touching it must call
  `sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` in `setUpAll`.
  `inMemoryDatabasePath` is *shared across opens in one process*, so delete it
  in `setUp` or tests leak state into each other.
- **Platform channels are unavailable**, so Keychain/Keystore behaviour cannot
  be tested here. `flutter_secure_storage` is faked with `mocktail` and the
  contract is asserted instead; real device behaviour is M0 Task 20.

Use `test/support/sequence_adapter.dart` — **not `http_mock_adapter`** — whenever
a test needs a *sequence* of responses. http_mock_adapter 0.6.1 fixes the status
code at registration, `replyCallback` varies only the body, and duplicate
registrations do not queue (the matcher keeps the **last** match), so it cannot
express "401 then 200".

## UI: Arbor Heritage design system — mandatory

Organic, premium editorial feel. Encoded as theme tokens in `core/theme/`
(Task 11), not re-derived per widget.

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

Screens are designed and approved via the Stitch design system (project
`15513208985178358792`) before implementation — see
[`docs/sad/05c-mobile-components.md`](../docs/sad/05c-mobile-components.md).
