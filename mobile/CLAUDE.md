# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
flutter pub get                                                # install deps
flutter run                                                    # run on default device
flutter run -d "iPhone 16"                                     # run on a specific simulator/device
flutter test                                                   # full test suite
flutter test test/path/to/foo_test.dart                        # single test file
flutter test --plain-name "describes the case"                 # single test by name
dart analyze .                                                 # lint
dart run build_runner build --delete-conflicting-outputs       # regen code (BLoC/Freezed/Retrofit/Injectable)
dart run build_runner watch --delete-conflicting-outputs       # watch mode
flutter gen-l10n                                               # regenerate AppLocalizations from .arb files
flutter build apk                                              # Android build
flutter build ios                                              # iOS build (macOS + Xcode required)
```

Run `dart run build_runner build …` whenever you change BLoC states, Freezed models, `@RestApi()` Retrofit clients, or `@injectable` registrations. Run `flutter gen-l10n` after editing `.arb` files (see L10n below).

Simulator/emulator helpers:

```bash
xcrun simctl list devices available           # iOS sims
xcrun simctl boot "iPhone 16"
flutter emulators                             # Android AVDs
flutter emulators --launch <id>
```

Env file: copy `.env.example` → `.env` before first run.

## Architecture

Clean Architecture + feature-first modules + BLoC state.

```
lib/
├── main.dart                    # entry; calls configureDependencies() then runApp(FamilyRootsApp)
├── app/                         # MaterialApp.router, theme, go_router
├── core/                        # DI, networking, error, constants, theme tokens
├── domain/                      # cross-feature entities, repository ports, and shared mocks
├── features/<feature>/          # auth, family_tree, members, documents, events, home, notifications
│   ├── data/                    # API clients (Dio/Retrofit), DTOs, repository impls
│   ├── domain/                  # feature-local entities, use-cases
│   └── presentation/            # BLoC/Cubit, pages, widgets
└── shared/                      # widgets, extensions, l10n
```

### Two layers of "domain" — read carefully

The codebase has **two coexisting locations** while the mock-to-API migration is in flight:

- `lib/domain/` (top-level) — cross-feature repository **interfaces** + shared **mock implementations** (`domain/mocks/`). This is what `core/di/injection.dart` currently wires up (see `MockMemberRepository.new`, `MockEventRepository.new`).
- `lib/features/<feature>/domain/` — feature-local entities and use-cases.

Real API implementations (Dio + Retrofit) land under `lib/features/<feature>/data/`. To flip a feature from mock to real API, change the registration in `core/di/injection.dart`:

```dart
// from
getIt.registerLazySingleton<MemberRepository>(MockMemberRepository.new);
// to
getIt.registerLazySingleton<MemberRepository>(() => ApiMemberRepository(dio));
```

UI code depends on the abstract port only — no widget changes required.

### State, DI, routing, networking

- **State**: `flutter_bloc` (Cubit for simple, BLoC for event-driven). Cubits are registered as **factory** in DI so each screen gets a fresh instance disposed on pop. Use `bloc_test` + `mocktail` for unit tests.
- **DI**: `get_it` (singleton container) plus `injectable` for code-generated bindings. Manual registrations live in `core/di/injection.dart`.
- **Routing**: `go_router` configured in `lib/app/router/app_router.dart` with guards in `route_guards.dart`. App root is `MaterialApp.router` in `lib/app/app.dart`.
- **Network**: `dio` + `retrofit` (typed REST). **Important — currently scaffolded only**: `lib/core/network/api_client.dart` and `lib/core/network/auth_interceptor.dart` are TODO placeholders ("Prompt 2"). When wiring them up, the Dio interceptor must attach the three backend-contract headers (see below) and handle Supabase token refresh on 401.
- **Storage**: `hive` / `hive_flutter` for local cache (init is TODO in `main.dart`).
- **Auth**: `supabase_flutter` (+ `google_sign_in`, `sign_in_with_apple`).
- **Push**: `firebase_core` + `firebase_messaging` (init is TODO in `main.dart`).
- **Errors / observability**: `sentry_flutter` (init is TODO in `main.dart`).

### Backend contract

When the Dio client is wired up, every clan-scoped request must send:

- `Authorization: Bearer <supabase-jwt>`
- `Accept-Language` (current locale)
- `X-Current-Clan-Id` (active clan from session/local storage)

Match query semantics with backend + web: cursor pagination (`next_cursor`, `has_more`), `profile=summary|detail|full`, `include`, sparse `fields` (and merge `include_by_id` keys into `fields`).

### Known scaffold state (Prompt 2 TODOs)

Don't waste time grepping for these — they are intentionally stubs and need real implementations:

- `lib/core/network/api_client.dart`, `lib/core/network/auth_interceptor.dart`
- Firebase / Sentry / Hive initialization in `lib/main.dart`
- Per-feature `data/` adapters are partial — the DI container is still on mocks.

## UI-first development workflow

All new features and screens follow this order:

1. **Design first** — designed, reviewed, and approved via the Stitch design system (project ID `15513208985178358792`).
2. **Review specs** — layout, spacing tokens, typography, colors, and the design system's Do's/Don'ts before writing code.
3. **Mock-data UI** — build in Flutter against `lib/domain/mocks/` to hit pixel-perfect fidelity without backend coupling.
4. **Wire to API** — only after the UI is approved, flip the DI registration to the real `Api…Repository`.

## Arbor Heritage design system — mandatory

Organic, premium editorial feel. Adhere strictly:

### No-line rule
- Do not use 1px solid borders for sections or separation. (Exception: high-contrast accessibility mode → `outline_variant` at 15% opacity.)
- Express boundaries with subtle background shifts (e.g. `surface-container-low` on top of `surface`).

### Typography (via `google_fonts`)
- **Plus Jakarta Sans** — headings, display, storytelling, milestones, person names, branch titles.
- **Manrope** — body text, labels, data display.
- Never fall back to the device system font unless explicitly specified.

### Organic asymmetry & elevation
- Soft, highly rounded corners: `9999px` for primary buttons, `2rem` for nodes. Never `sm` or `none`.
- No rigid drop shadows. Use ambient depth (e.g. 32px blur at 6% opacity) when elevation is needed.
- **Glass rule**: floating cards / nav bars use `surface` at 80% opacity with `20px` backdrop-blur.

### Color & layout
- Never use `#000000`. Primary text uses `on_surface` (`#1d1b16`).
- No rigid grids unless the data is tabular — let layouts breathe asymmetrically.

## Localization (l10n)

`l10n.yaml` drives generation: ARB files in `lib/shared/l10n/`, template `app_en.arb`, output class `AppLocalizations`. `pubspec.yaml` has `flutter: generate: true`.

All user-facing text **must** use `AppLocalizations` — no hardcoded strings.

### Adding a string

1. Add the key + English value to `lib/shared/l10n/app_en.arb`.
2. Add the same key + Vietnamese value to `lib/shared/l10n/app_vi.arb`.
3. Run `flutter gen-l10n` (or it runs as part of `flutter pub get` / build). This regenerates `app_localizations.dart`, `app_localizations_en.dart`, and `app_localizations_vi.dart` — **do not edit those by hand**.
4. Use in widgets:

```dart
final l10n = AppLocalizations.of(context);
Text(l10n.myKey);
```

### Parameters & plurals

```jsonc
// In ARB:
"greeting": "Hello, {name}"
"itemCount": "{count, plural, =0{No items} =1{1 item} other{{count} items}}"
```

```dart
l10n.greeting('Minh');
l10n.itemCount(3);
```

Use `intl`'s `Intl.pluralLogic` for ad-hoc plural fallbacks.

## Testing

- `flutter test` for the suite, `--plain-name` or a path for single tests.
- BLoC/Cubit tests use `bloc_test` + `mocktail` — mock the repository port, drive the cubit, assert emitted states.
- Run `dart analyze .` and `flutter test` before submitting a PR; run codegen first if you changed annotated files, or analysis will mislead.
