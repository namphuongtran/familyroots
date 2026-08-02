# Mobile M0 — Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the five-month-old mock scaffold under `mobile/` and rebuild it as a real Flutter application whose spine — transport, envelope, error policy, session, clan context, routing, theme, l10n, cache, observability — is proven by signing in to the real backend from a real device and listing the user's clans from `GET /me/clans`.

**Architecture:** One Flutter package. Riverpod 3 is both state manager and DI container. Plain Dio with hand-written repositories; DTOs via `json_serializable`; entities and state unions via `freezed`. A pure-Dart `domain/` layer that imports no framework, machine-enforced by an import-boundary test. The response envelope is unwrapped in exactly one function, `policyActionFor(code)` is the only error-code→routing mapping, and `HistoricalDate` owns its own render rule.

**Tech Stack:** Flutter 3.44.8 / Dart 3.12.2, `flutter_riverpod` + `riverpod_generator`, `go_router`, `dio`, `freezed`, `json_serializable`, `supabase_flutter`, `flutter_secure_storage`, `sqflite`, `sentry_flutter`, `intl`, ARB localisation.

---

## Verification status

Everything below was executed against a throwaway project (`flutter create /tmp/m0probe`) on the machine's real toolchain — **Flutter 3.44.8 • Dart 3.12.2 • DevTools 2.57.0**, `~/development/flutter/bin/flutter`, the exact version CI resolves. The probe finished on: `dart format --set-exit-if-changed` clean, `dart run build_runner build` reproducible, `flutter analyze` → **"No issues found!"**, `flutter test` → **30 passing**.

### VERIFIED — ran it, saw the output

| # | Claim | Evidence |
|---|---|---|
| V1 | **Spec §4.7's version table does not resolve.** See "Package set correction" below — this is the single largest finding and it changes the pubspec. | `flutter pub get` version-solving failures, reproduced for each conflicting pin |
| V2 | The corrected all-stable set resolves and passes every gate | `pubspec.lock` + clean format/codegen/analyze/test run |
| V3 | freezed 3.2.5 class syntax is `@freezed abstract class X with _$X` plus a `const X._();` for behaviour; freezed 2's plain `class` no longer works | `historical_date.freezed.dart` generated; equality, `copyWith`, and the custom `rendered` getter all tested |
| V4 | Riverpod 3 + `riverpod_generator` codegen emits `$Notifier`, `$Family`, and takes a plain `Ref` (not the Riverpod-2 `MyClansRef`) | `clan_providers.g.dart`: `final class MyClansProvider`, `abstract class _$SelectedClan extends $Notifier<String?>`, `final class ClanByIdFamily extends $Family` |
| V5 | `ProviderContainer(overrides: [...])` — **do not** write `<Override>[...]`; `Override` is `sealed` in `riverpod/src/core/override.dart` and is **not exported** from the public barrel. Annotating it is a compile error. | `error • The name 'Override' isn't a type` → fixed by dropping the type argument; 4 application tests pass |
| V6 | Dio 5.11 interceptor signatures: `void onRequest(RequestOptions, RequestInterceptorHandler)` and `Future<void> onError(DioException, ErrorInterceptorHandler)`; retry via `handler.resolve(await retryDio.fetch<Object?>(options))` | compiles; 401→refresh→retry test asserts exactly 2 transport calls and `Bearer fresh` on the retry |
| V7 | Single-flight refresh: 3 concurrent callers → 1 underlying refresh; refresh returning null signs out and does **not** loop | tests `concurrent callers share one refresh`, `refresh failure signs out and does not loop` |
| V8 | **`http_mock_adapter` 0.6.1 cannot vary status code per call.** `reply(status, data)` fixes the status at registration; `replyCallback` varies only the body. Duplicate route registrations do not queue — the matcher loop keeps the **last** match. So a 401-then-200 sequence needs a tiny hand-rolled `HttpClientAdapter`. | source read of `handlers/request_handler.dart` + `mixins/recording.dart`; the naive version failed with a real 401, the `SequenceAdapter` version passes |
| V9 | `supabase_flutter` 2.16.0 `LocalStorage` is 5 methods: `initialize()`, `hasAccessToken()`, `accessToken()`, `removePersistedSession()`, `persistSession(String)` — **read from the package source, not guessed** | `supabase_flutter-2.16.0/lib/src/local_storage.dart` |
| V10 | `LocalStorage` alone is not enough — the **PKCE code verifier** goes through a separate `GotrueAsyncStorage` (`pkceAsyncStorage`), which otherwise still lands in SharedPreferences plaintext | `FlutterAuthClientOptions` fields: `localStorage`, `pkceAsyncStorage` |
| V11 | `flutter_secure_storage` 10.3.1: `AndroidOptions(encryptedSharedPreferences: true)` is **deprecated, ignored, and removed in v11**. The v10 default is already KeyStore-backed AES-GCM + RSA-OAEP — pass a bare `AndroidOptions()`. | analyzer `deprecated_member_use` + the deprecation text in `android_options.dart` |
| V12 | `Supabase.initialize`'s `anonKey` is deprecated in 2.16.0; use `publishableKey` | `supabase.dart:80-95` |
| V13 | go_router 17.3.0 `redirect` + `refreshListenable` work — **but clearing a guard condition does not pull the user forward.** `redirect` returning null for the current location leaves the router where it is; the clan picker must `context.go()` explicitly after selection. | test `multi-clan user is sent to the picker`: after `needsClanPick=false` the picker is still on screen until an explicit `router.go('/clans')` |
| V14 | The import-boundary scanner parses real Dart directives (ignoring line and block comments), resolves relative imports against `lib/`, and **actually fails** on a violation | three injected violations each caught with a precise message, tree clean again after removal |
| V15 | **`sqflite` does not work under `flutter test`** — `Bad state: databaseFactory not initialized`. Needs `sqflite_common_ffi` (dev dep, not in spec §4.7) with `sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` | failing run, then passing round-trip test |
| V16 | `build_runner` 2.15.1 **removed `--delete-conflicting-outputs`** — it warns `These options have been removed and were ignored`. Spec §5's CI command must drop it. | build_runner output |
| V17 | The generated-code freshness gate works: after `build_runner build`, `git diff --exit-code` is clean; corrupting a `.g.dart` and rebuilding is detected | simulated staleness detected, named the exact file |
| V18 | Only **variable** fonts exist upstream for Plus Jakarta Sans and Manrope (no `static/` instances — those 404). Declaring the same variable TTF twice with different `weight:` values works: the wght axis is applied. | regular 247.3px vs bold 250.5px for identical text |
| V19 | **Golden/widget tests render a placeholder font unless fonts are explicitly loaded.** Without `FontLoader` the same string measured 480.0×32.0 at both weights (weight-insensitive placeholder); with it, 247.3 vs 250.5. Goldens need a `loadAppFonts()` in `setUpAll`. | the two measurements above |
| V20 | `analysis_options.yaml` with `strict-casts`/`strict-inference`/`strict-raw-types` on top of `flutter_lints` 6.0.0 is achievable with zero issues, but forces explicit type arguments on collection literals **in test code** and `_`/`_` (not `__`) for unused closure params | `flutter analyze` → "No issues found!" only after those fixes |
| V21 | `flutter gen-l10n` with `template-arb-file: app_vi.arb` works; `synthetic-package:` is deprecated and must not be present in `l10n.yaml` | generated `app_localizations{,_en,_vi}.dart`; deprecation warning when the key was present |
| V22 | The repo's current `mobile/assets/` holds **only `.gitkeep` files — there are no fonts**, so "carry `assets/` forward" carries nothing. Fonts must be fetched. | `ls -la mobile/assets/{icons,images}` |
| V23 | The `packages/**` CI trigger the spec says to remove is **already gone**, and `mobile-ci.yml` already self-triggers. Only the new gates need adding. | current `.github/workflows/mobile-ci.yml` |
| V24 | The two Google Fonts variable TTFs and their OFL licence are fetchable (HTTP 200) | `curl -o /dev/null -w %{http_code}` on all three URLs |

### NOT VERIFIED — stated honestly

| # | Not verified | Why / what the implementer must do |
|---|---|---|
| N1 | **Any real call to the FamilyRoots backend.** Every network test uses a mock transport. No login, no `GET /auth/me`, no `GET /me/clans` was executed against a live server. | M0's definition of done is exactly this. Task 18 is the manual device run; it is the first moment the spine meets the real backend. Expect surprises there, not in the unit tests. |
| N2 | `flutter build apk --debug` | Requires the Android SDK/toolchain, which was not exercised. CI runs it; if it fails it will fail on Android config, not Dart. |
| N3 | On-device iOS Keychain / Android Keystore behaviour of `flutter_secure_storage` | Plugin channels are unavailable in `flutter test`. The `LocalStorage` contract conformance is verified; the platform round-trip is not. Task 18 covers it implicitly (a session that survives an app restart). |
| N4 | Sentry actually delivering an event, and the `traceparent` span joining a backend trace | `SentryFlutter.init` compiles against 9.26.0; no DSN was exercised. |
| N5 | Golden **images**. `loadAppFonts` is verified; no golden file was committed or compared. | First golden run must be `--update-goldens`, then reviewed by eye. Goldens are host-font-sensitive; CI and local must both run Linux or goldens must be tagged. |
| N6 | The exact Supabase email-link parameter format (spec R2) | Unknowable from this repo. **M0 does not need it** — spec §7 puts deep links out of scope, and the verification screen only needs `POST /auth/resend-verification`. Recorded as an open question below. |
| N7 | `firebase_messaging` 16.4.3 | M4 scope; deliberately not added to the pubspec in M0. |
| N8 | That `riverpod_lint`'s analyzer plugin actually reports Riverpod misuse | It is wired via `plugins: - riverpod_lint` and `flutter analyze` runs clean, but no deliberate Riverpod misuse was written to confirm the plugin fires. Note `riverpod_lint` 3.1.3 uses the native `analysis_server_plugin`, **not** `custom_lint`. |

### Package set correction — spec §4.7 does not resolve

This needs owner sign-off before Task 1. Six pins in spec §4.7 are unusable on Flutter 3.44.8, and one is a published-package defect.

Root cause: Flutter 3.44.8 hard-pins `meta: 1.18.0`. `analyzer` ≥13.1.0 requires `meta ^1.18.3`. And `flutter_test` pins `test_api 0.7.11`, which caps `analyzer` below 13.0.0 in any package that also depends on `test`.

| Spec pin | Problem (exact resolver output) | Corrected |
|---|---|---|
| `custom_lint` 0.8.1 | Needs `analyzer ^8.0.0`; `freezed` 3.2.5 needs `>=9.0.0 <11.0.0`; `riverpod_lint` 3.1.8 needs `^13.0.0`. Mutually impossible. **`riverpod_lint` 3.1.3 does not depend on `custom_lint` at all** — it uses `analysis_server_plugin ^0.3.0`. | **removed entirely** |
| `riverpod_generator` 4.0.8 | `riverpod_generator >=4.0.6 depends on analyzer ^13.0.0 and every version of flutter_test from sdk depends on test_api 0.7.11, riverpod_generator >=4.0.8 is incompatible with flutter_test from sdk.` pub's own suggestion: `flutter pub add dev:riverpod_generator:^4.0.4`. (4.0.6 is additionally self-contradictory: it declares `analyzer ^13` while pinning `riverpod_analyzer_utils 1.0.0-dev.10`, which declares `analyzer ^12`.) | **4.0.3** |
| `riverpod_lint` 3.1.8 | Needs `analyzer ^13.0.0` — same wall. | **3.1.3** |
| `flutter_riverpod` 3.4.2 / `riverpod_annotation` 4.0.6 | Fine standalone, but `riverpod_lint` pins `riverpod` **exactly** (3.1.8→3.4.2, 3.1.3→3.2.1). Keeping codegen + lint forces the matching runtime. | **3.3.1 / 4.0.2** |
| `build_runner` 2.16.0 | `build_runner >=2.15.2 depends on analyzer >=13.3.0 <15.0.0 which depends on meta ^1.18.3` — conflicts with the SDK's `meta 1.18.0`. | **2.15.1** |
| `json_serializable` 6.14.1 | Needs `analyzer >=10.0.0`; the analyzer-9 line that keeps `freezed` 3.2.5 stable caps it. | **6.13.0** |
| `intl` 0.20.3 | `every version of flutter_localizations from sdk depends on intl 0.20.2 and probe_res depends on intl 0.20.3, flutter_localizations from sdk is forbidden.` | **0.20.2** |
| — | `sqflite` is untestable without it (V15) | **add `sqflite_common_ffi` 2.4.2** (dev) |
| — | the boundary test imports it directly; `depend_on_referenced_packages` fires otherwise | **add `path` ^1.9.0** (dev) |
| — | clan selection is not a secret (spec §4.3 says "ordinary preferences") | **add `shared_preferences` ^2.5.3** |

`freezed` **3.2.5** — the spec's pin — is *preserved exactly*. The alternative (analyzer-12 line: `riverpod_generator` 4.0.4, `riverpod_lint` 3.1.4, `flutter_riverpod` 3.3.2) also resolves but only with `freezed 3.2.6-dev.1`, **a prerelease**. This plan chooses the all-stable line. If the owner prefers newer Riverpod over stable freezed, the analyzer-12 line is the one-line swap; everything else in this plan is unaffected.

One accepted consequence: analyzer 9.0.0 lags the SDK, so `build_runner` prints `SDK language version 3.12.0 is newer than analyzer language version 3.11.0`. It is a warning, codegen succeeds, and every gate is green — but Dart 3.12-only syntax may not parse in generated-code analysis. Revisit when `freezed` ships a stable release on analyzer ≥12.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Toolchain:** Flutter 3.44.8, Dart 3.12.2. `export PATH="$HOME/development/flutter/bin:$PATH"`. CI must pin `flutter-version: 3.44.8` — not bare `channel: stable`, which drifts.
- **Package versions:** exactly the corrected table in Task 1. Do not float, upgrade or substitute. Every pin is exact (no `^`) for the packages spec §4.7 names.
- **`domain/**` must not import** `package:flutter/*`, `dio`, `riverpod`, `flutter_riverpod`, `riverpod_annotation`, `supabase_flutter`, or `json_annotation`. Enforced by `test/architecture/layer_boundaries_test.dart` (spec D9).
- **No user-facing string is hardcoded.** Everything through ARB. M0 ships `vi` and `en`, **`vi` is default and fallback**. No code may assume the locale set is exactly two.
- **Generated code is committed.** `*.g.dart` and `*.freezed.dart` are checked into git, never gitignored. CI re-runs `build_runner` and fails on a diff.
- **The envelope is unwrapped in exactly one place** (`core/network/envelope.dart`). No widget, notifier or repository ever sees `{"data": …}`.
- **`policyActionFor(code)` is the single error-code → routing mapping.** UI branches on `code`, never on `message`. `message` arrives already localised — display it directly.
- **`HistoricalDate` owns its own render rule** (`date` when `precision == "exact"`, else `display`, falling back to `date`). No widget re-implements it.
- **Cursors are opaque** — never parsed, constructed or repaired. On `400 invalid_cursor`, drop the cursor and refetch page one.
- **Presigned URLs are never persisted** to any local store (TTL 3600s).
- **đời (`generation`) is backend data** — never derived. `null` renders honestly as "đời ?".
- **Arbor Heritage mandates** are encoded as theme tokens: no 1px borders, 9999px/2rem radii, never `#000000` (use `on_surface` `#1d1b16`), glass = surface at 80% opacity with 20px blur, ambient depth not rigid shadows, fonts bundled and never fetched at runtime.
- **Layouts must survive 200% text scale.** Goldens at scale 1.0 and 2.0.
- **Quality gate before claiming any task done:**
  ```bash
  cd mobile && dart format --set-exit-if-changed lib test \
    && dart run build_runner build && git diff --exit-code \
    && flutter analyze && flutter test
  ```
- **Every commit message ends with:**
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
  ```

---

## File Structure

```
mobile/
├── pubspec.yaml
├── analysis_options.yaml
├── l10n.yaml
├── assets/fonts/{PlusJakartaSans,Manrope}.ttf, OFL.txt
├── lib/
│   ├── main.dart                                  # bootstrap only
│   ├── app/
│   │   ├── app.dart                               # ProviderScope + MaterialApp.router
│   │   ├── bootstrap.dart                         # Sentry, Supabase, cache, l10n init
│   │   └── router/{app_router.dart,auth_state.dart,routes.dart}
│   ├── core/
│   │   ├── network/
│   │   │   ├── api_client.dart                    # getOne/getPage/post; the Dio wrapper
│   │   │   ├── envelope.dart                      # unwrapData, unwrapPage
│   │   │   ├── api_exception.dart                 # sealed taxonomy + policyActionFor
│   │   │   ├── dio_provider.dart                  # the single Dio, wired
│   │   │   └── interceptors/{auth,clan,locale,trace,refresh}_interceptor.dart
│   │   ├── storage/{secure_session_store.dart,cache_store.dart,prefs_store.dart}
│   │   ├── observability/{sentry.dart,traceparent.dart}
│   │   ├── theme/{tokens.dart,app_theme.dart}
│   │   └── l10n/{app_vi.arb,app_en.arb,generated/}
│   ├── domain/
│   │   ├── shared/{historical_date.dart,page.dart,ids.dart,locale_code.dart}
│   │   ├── clan/{clan_membership.dart,clan_role.dart}
│   │   └── auth/{user_profile.dart}
│   ├── features/
│   │   ├── auth/{auth.dart,data/,application/,presentation/}
│   │   └── clan/{clan.dart,data/,application/,presentation/}
│   └── shared/widgets/
└── test/
    ├── architecture/layer_boundaries_test.dart
    ├── support/{sequence_adapter.dart,load_app_fonts.dart,fixtures.dart}
    ├── domain/ · core/ · features/ · goldens/
```

---

## Task 1: Delete the scaffold and stand up the new project

**Files:**
- Delete: everything under `mobile/` except the four carried-forward items
- Create: `mobile/pubspec.yaml`, `mobile/analysis_options.yaml`, `mobile/.gitignore`
- Preserve: `mobile/lib/shared/l10n/app_vi.arb`, `mobile/lib/shared/l10n/app_en.arb` (moved to `lib/core/l10n/`), `mobile/l10n.yaml` (rewritten), `mobile/assets/` (see note)

**Interfaces:**
- Produces: a `mobile/` package named `family_roots_mobile` that `flutter pub get` resolves and `flutter analyze` passes on an empty `lib/`.

> **Note on carried-forward assets (V22):** `mobile/assets/icons/` and `mobile/assets/images/` contain only `.gitkeep`. There is nothing to preserve but the directories. The 55-key ARB pair is the only substantive carry-forward.

- [ ] **Step 1: Rescue the ARB files before deleting anything**

```bash
cd mobile
mkdir -p /tmp/m0-carry
cp lib/shared/l10n/app_vi.arb lib/shared/l10n/app_en.arb /tmp/m0-carry/
ls /tmp/m0-carry   # expect: app_en.arb app_vi.arb
```

- [ ] **Step 2: Delete the tree**

```bash
cd mobile
git rm -r --quiet lib test android ios web macos linux windows \
  pubspec.yaml pubspec.lock analysis_options.yaml l10n.yaml \
  .metadata 2>/dev/null || true
git clean -nd .          # REVIEW the list first — never run git clean -fd blindly
```

Delete only what `git rm` reported. Do not remove `mobile/CLAUDE.md` (rewritten in Task 19) or `mobile/assets/`.

- [ ] **Step 3: Recreate the Flutter project in place**

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
cd mobile
flutter create --org com.familyroots --project-name family_roots_mobile \
  --platforms=android,ios .
```

- [ ] **Step 4: Write the pubspec with the corrected, verified versions**

`mobile/pubspec.yaml`:

```yaml
name: family_roots_mobile
description: FamilyRoots mobile app — Android and iOS.
publish_to: "none"
version: 0.1.0+1

environment:
  sdk: ">=3.12.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter

  flutter_riverpod: 3.3.1
  riverpod_annotation: 4.0.2
  go_router: 17.3.0
  dio: 5.11.0
  freezed_annotation: ^3.1.0
  json_annotation: ^4.11.0
  supabase_flutter: 2.16.0
  flutter_secure_storage: 10.3.1
  sqflite: 2.4.3
  shared_preferences: ^2.5.3
  sentry_flutter: 9.26.0
  intl: 0.20.2

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: 6.0.0
  build_runner: 2.15.1
  riverpod_generator: 4.0.3
  riverpod_lint: 3.1.3
  freezed: 3.2.5
  json_serializable: 6.13.0
  mocktail: 1.0.5
  http_mock_adapter: 0.6.1
  sqflite_common_ffi: 2.4.2
  path: ^1.9.0

flutter:
  generate: true
  uses-material-design: true

  assets:
    - assets/images/
    - assets/icons/
```

`json_annotation` must be `^4.11.0`, not `^4.9.0` — `json_serializable` warns `The version constraint "^4.9.0" on json_annotation allows versions before 4.11.0 which is not allowed.`

- [ ] **Step 5: Write `analysis_options.yaml`**

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  language:
    strict-casts: true
    strict-inference: true
    strict-raw-types: true
  errors:
    invalid_annotation_target: ignore
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"
    - "lib/core/l10n/generated/**"
  plugins:
    - riverpod_lint

linter:
  rules:
    - prefer_single_quotes
    - always_declare_return_types
    - unawaited_futures
```

- [ ] **Step 6: Ensure generated code is NOT gitignored**

Append to `mobile/.gitignore`, and confirm no `*.g.dart` / `*.freezed.dart` ignore rule exists anywhere:

```gitignore
.dart_tool/
build/
.flutter-plugins-generated
*.iml
```

```bash
grep -rn "g.dart\|freezed.dart" .gitignore ../.gitignore   # expect no matches
```

- [ ] **Step 7: Restore the ARB files and rewrite `l10n.yaml`**

```bash
mkdir -p lib/core/l10n
cp /tmp/m0-carry/app_vi.arb /tmp/m0-carry/app_en.arb lib/core/l10n/
rm -rf lib/shared/l10n
```

`mobile/l10n.yaml` — `vi` is the template because it is default and fallback. Do **not** add `synthetic-package:`; it is deprecated (V21).

```yaml
arb-dir: lib/core/l10n
template-arb-file: app_vi.arb
output-localization-file: app_localizations.dart
output-class: AppLocalizations
output-dir: lib/core/l10n/generated
nullable-getter: false
```

- [ ] **Step 8: Verify the toolchain resolves**

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
cd mobile && flutter pub get
```
Expected: `Got dependencies!` and **no** version-solving failure. If you see `version solving failed`, stop — do not "fix" it by loosening a pin. Re-read the Package set correction table.

- [ ] **Step 9: Confirm the resolved versions match**

```bash
grep -A1 -E "^  (flutter_riverpod|riverpod_generator|freezed|build_runner|analyzer|intl):" pubspec.lock | grep version
```
Expected: `flutter_riverpod 3.3.1`, `riverpod_generator 4.0.3`, `freezed 3.2.5`, `build_runner 2.15.1`, `analyzer 9.0.0`, `intl 0.20.2`.

- [ ] **Step 10: Commit**

```bash
git add -A mobile
git commit -m "$(cat <<'EOF'
feat(mobile): delete mock scaffold, scaffold Riverpod rebuild (ADR-034)

Carries forward only the vi/en ARB files and assets/, per ADR-034.
Package versions corrected from spec 4.7: custom_lint dropped
(riverpod_lint 3.1.3 uses analysis_server_plugin), riverpod tooling
capped at the analyzer-9 line by flutter_test's test_api pin, intl
pinned to 0.20.2 by flutter_localizations, build_runner to 2.15.1 by
the SDK's meta 1.18.0.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 2: The import-boundary ratchet (spec D9)

Built second, before any real code, so every later task lands inside a fence that already exists.

**Files:**
- Test: `mobile/test/architecture/layer_boundaries_test.dart`

**Interfaces:**
- Produces: `parseDirectives(String source) → List<String>`, `normalize(String directive, String fileLibRelPath) → String?`, `violationFor(String libRelPath, String target) → String?`. Later tasks do not call these; they only have to not trip them.

- [ ] **Step 1: Write the failing test**

Create `mobile/test/architecture/layer_boundaries_test.dart`. This is the whole file — it is verified working (V14), including the three negative controls.

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

/// Matches `import '...'` and `export '...'`, single or double quoted.
final _directive = RegExp(
  r"""^\s*(?:import|export)\s+(?:'([^']+)'|"([^"]+)")""",
  multiLine: true,
);

final _blockComment = RegExp(r'/\*.*?\*/', dotAll: true);
final _lineComment = RegExp(r'^\s*//.*$', multiLine: true);

List<String> parseDirectives(String source) {
  final stripped = source
      .replaceAll(_blockComment, '')
      .replaceAll(_lineComment, '');
  return _directive
      .allMatches(stripped)
      .map((m) => m.group(1) ?? m.group(2)!)
      .toList();
}

/// Resolves a relative import to a `lib/`-root-relative path so relative and
/// `package:` imports are checked by the same rules.
String? normalize(String directive, String fileLibRelPath) {
  if (directive.startsWith('dart:')) return null;
  if (directive.startsWith('package:family_roots_mobile/')) {
    return directive.substring('package:family_roots_mobile/'.length);
  }
  if (directive.startsWith('package:')) return directive;
  final dir = p.dirname(fileLibRelPath);
  return p.normalize(p.join(dir, directive));
}

const _domainForbiddenPackages = <String>[
  'package:flutter/',
  'package:dio/',
  'package:flutter_riverpod/',
  'package:riverpod/',
  'package:riverpod_annotation/',
  'package:supabase_flutter/',
  'package:supabase/',
  'package:json_annotation/',
];

/// Returns a human-readable violation, or null.
String? violationFor(String libRelPath, String target) {
  if (libRelPath.startsWith('domain/')) {
    for (final banned in _domainForbiddenPackages) {
      if (target.startsWith(banned)) {
        return '$libRelPath imports $target — domain must stay framework-agnostic';
      }
    }
    if (target.startsWith('core/') ||
        target.startsWith('features/') ||
        target.startsWith('app/') ||
        target.startsWith('shared/')) {
      return '$libRelPath imports $target — domain may import only domain/** and dart:*';
    }
  }

  if (libRelPath.startsWith('core/') && target.startsWith('features/')) {
    return '$libRelPath imports $target — core must not depend on features';
  }

  final presentation = RegExp(r'^features/([^/]+)/presentation/');
  if (presentation.hasMatch(libRelPath)) {
    if (RegExp(r'^features/[^/]+/data/').hasMatch(target)) {
      return '$libRelPath imports $target — presentation must not import data';
    }
  }

  final sliceOf = RegExp(r'^features/([^/]+)/');
  final from = sliceOf.firstMatch(libRelPath);
  final to = sliceOf.firstMatch(target);
  if (from != null && to != null && from.group(1) != to.group(1)) {
    final slice = to.group(1)!;
    if (target != 'features/$slice/$slice.dart') {
      return '$libRelPath imports $target — cross-slice imports must go '
          'through features/$slice/$slice.dart';
    }
  }

  if (libRelPath.startsWith('app/') &&
      RegExp(r'^features/[^/]+/data/').hasMatch(target)) {
    return '$libRelPath imports $target — app must not import data';
  }

  return null;
}

void main() {
  test('parseDirectives extracts imports and ignores comments', () {
    const src = '''
// import 'package:evil/evil.dart';
/* import 'package:also_evil/x.dart'; */
import 'dart:async';
import "package:dio/dio.dart";
import '../shared/page.dart';
export 'package:family_roots_mobile/domain/shared/page.dart';
''';
    expect(parseDirectives(src), <String>[
      'dart:async',
      'package:dio/dio.dart',
      '../shared/page.dart',
      'package:family_roots_mobile/domain/shared/page.dart',
    ]);
  });

  test('violationFor flags a domain file importing dio', () {
    expect(
      violationFor('domain/person/person.dart', 'package:dio/dio.dart'),
      isNotNull,
    );
    expect(
      violationFor(
        'domain/person/person.dart',
        'package:collection/collection.dart',
      ),
      isNull,
    );
  });

  test('violationFor flags relative domain->core escape', () {
    final target = normalize(
      '../../core/network/x.dart',
      'domain/person/person.dart',
    );
    expect(target, 'core/network/x.dart');
    expect(violationFor('domain/person/person.dart', target!), isNotNull);
  });

  test('violationFor flags cross-slice deep import', () {
    expect(
      violationFor(
        'features/clan/application/x.dart',
        'features/auth/data/auth_repository.dart',
      ),
      isNotNull,
    );
    expect(
      violationFor('features/clan/application/x.dart', 'features/auth/auth.dart'),
      isNull,
    );
  });

  test('violationFor flags presentation importing data', () {
    expect(
      violationFor(
        'features/clan/presentation/clan_page.dart',
        'features/clan/data/clan_repository.dart',
      ),
      isNotNull,
    );
  });

  test('lib/ has no layer-boundary violations', () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue, reason: 'run from the package root');

    final violations = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final libRel = p.relative(entity.path, from: 'lib');
      for (final d in parseDirectives(entity.readAsStringSync())) {
        final target = normalize(d, libRel);
        if (target == null) continue;
        final v = violationFor(libRel, target);
        if (v != null) violations.add(v);
      }
    }

    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
```

- [ ] **Step 2: Run it**

```bash
cd mobile && flutter test test/architecture/layer_boundaries_test.dart
```
Expected: `All tests passed!` (6 tests) on the fresh `lib/`.

- [ ] **Step 3: Prove it fails — negative control**

Do not skip this. A boundary test that cannot fail is worse than none.

```bash
mkdir -p lib/domain/shared
printf "import 'package:dio/dio.dart';\nclass Bad { Dio? d; }\n" > lib/domain/shared/_bad.dart
flutter test test/architecture/layer_boundaries_test.dart
```
Expected: **failure**, with `domain/shared/_bad.dart imports package:dio/dio.dart — domain must stay framework-agnostic`.

```bash
rm lib/domain/shared/_bad.dart
flutter test test/architecture/layer_boundaries_test.dart   # green again
```

- [ ] **Step 4: Commit**

```bash
git add mobile/test/architecture/layer_boundaries_test.dart
git commit -m "$(cat <<'EOF'
test(mobile): add import-boundary ratchet (ADR-034 D9)

Parses import/export directives of every file under lib/, resolves
relative imports, and fails on a layer violation. Mirrors the backend's
lint-imports ratchet (ADR-013) without adding a dependency.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 3: Domain shared kernel — `HistoricalDate`, `Page<T>`, ids

**Files:**
- Create: `mobile/lib/domain/shared/historical_date.dart`, `page.dart`, `ids.dart`
- Test: `mobile/test/domain/historical_date_test.dart`

**Interfaces:**
- Produces:
  - `enum DatePrecision { exact, month, year, circa, unknown }`
  - `HistoricalDate({String? date, DatePrecision precision, String? display, String? lunar})` with `String? get rendered`, `String get sortKey`, `factory HistoricalDate.fromWire(Map<String, Object?>)`
  - `Page<T>({List<T> items, String? cursor, bool hasMore, int limit})`, `Page.empty<T>()`
  - `extension type ClanId(String value)`, `extension type PersonId(String value)`

> **freezed 3 syntax (V3):** the class must be `abstract class` (or `sealed` for unions) and mix in `_$X`. freezed 2's plain `class X with _$X` is a compile error. A private `const X._();` constructor is required to add behaviour.

- [ ] **Step 1: Write the failing test**

`mobile/test/domain/historical_date_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/domain/shared/historical_date.dart';

void main() {
  test('renders date when precision is exact', () {
    const d = HistoricalDate(
      date: '1750-03-02',
      precision: DatePrecision.exact,
      display: 'khoảng 1750',
      lunar: null,
    );
    expect(d.rendered, '1750-03-02');
  });

  test('renders display when precision is not exact', () {
    const d = HistoricalDate(
      date: '1750-01-01',
      precision: DatePrecision.circa,
      display: 'khoảng 1750',
      lunar: null,
    );
    expect(d.rendered, 'khoảng 1750');
  });

  test('falls back to date when display is null', () {
    const d = HistoricalDate(
      date: '1750-01-01',
      precision: DatePrecision.year,
      display: null,
      lunar: null,
    );
    expect(d.rendered, '1750-01-01');
  });

  test('renders null when nothing is known', () {
    const d = HistoricalDate(
      date: null,
      precision: DatePrecision.unknown,
      display: null,
      lunar: null,
    );
    expect(d.rendered, isNull);
  });

  test('parses the wire shape from docs/contracts', () {
    final d = HistoricalDate.fromWire(<String, Object?>{
      'date': '1932-05-01',
      'precision': 'exact',
      'display': null,
      'lunar': '15/08 Nhâm Tý',
    });
    expect(d.precision, DatePrecision.exact);
    expect(d.lunar, '15/08 Nhâm Tý');
    expect(d.rendered, '1932-05-01');
  });

  test('an unknown precision string degrades to unknown, never throws', () {
    final d = HistoricalDate.fromWire(<String, Object?>{
      'date': null,
      'precision': 'something_new_from_the_backend',
      'display': 'thời Lê',
      'lunar': null,
    });
    expect(d.precision, DatePrecision.unknown);
    expect(d.rendered, 'thời Lê');
  });

  test('freezed gives value equality and copyWith', () {
    const a = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    const b = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(
      a.copyWith(precision: DatePrecision.year).precision,
      DatePrecision.year,
    );
  });

  test('sortKey puts unknown dates last', () {
    const known = HistoricalDate(
      date: '1900-01-01',
      precision: DatePrecision.exact,
      display: null,
      lunar: null,
    );
    const unknown = HistoricalDate(
      date: null,
      precision: DatePrecision.unknown,
      display: null,
      lunar: null,
    );
    final list = <HistoricalDate>[unknown, known]
      ..sort((a, b) => b.sortKey.compareTo(a.sortKey));
    expect(list.first, known);
  });
}
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd mobile && flutter test test/domain/historical_date_test.dart
```
Expected: FAIL — `Error: Couldn't resolve the package 'family_roots_mobile' ... historical_date.dart`.

- [ ] **Step 3: Write `page.dart` and `ids.dart`**

`mobile/lib/domain/shared/page.dart`:

```dart
/// One page of a cursor-paginated list.
class Page<T> {
  const Page({
    required this.items,
    required this.cursor,
    required this.hasMore,
    required this.limit,
  });

  final List<T> items;

  /// Opaque (ADR-010). Never parsed, constructed or repaired by the client —
  /// pass it back verbatim or drop it.
  final String? cursor;
  final bool hasMore;
  final int limit;

  static Page<T> empty<T>() =>
      Page<T>(items: <T>[], cursor: null, hasMore: false, limit: 0);
}
```

`mobile/lib/domain/shared/ids.dart`:

```dart
/// Zero-cost wrappers so a ClanId cannot be passed where a PersonId is meant.
///
/// Extension types may NOT declare `toString`, `==`, `hashCode`, `runtimeType`
/// or `noSuchMethod` — those conflict with the Object members and are a
/// compile error ("This extension member conflicts with Object member
/// 'toString'"). Use `.value` for interpolation.
extension type const ClanId(String value) {}

extension type const PersonId(String value) {}

extension type const UserId(String value) {}
```

- [ ] **Step 4: Write `historical_date.dart`**

```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'historical_date.freezed.dart';

enum DatePrecision {
  exact,
  month,
  year,
  circa,
  unknown;

  /// Never throws: an unrecognised backend value degrades to [unknown] so a
  /// new precision on the server cannot crash a shipped client.
  static DatePrecision fromWire(Object? raw) {
    for (final p in DatePrecision.values) {
      if (p.name == raw) return p;
    }
    return DatePrecision.unknown;
  }
}

/// ADR-011. A model with behaviour, not a struct: it owns the render rule and
/// the sort key so no widget re-implements them.
@freezed
abstract class HistoricalDate with _$HistoricalDate {
  const factory HistoricalDate({
    required String? date,
    required DatePrecision precision,
    required String? display,
    required String? lunar,
  }) = _HistoricalDate;

  const HistoricalDate._();

  factory HistoricalDate.fromWire(Map<String, Object?> json) => HistoricalDate(
    date: json['date'] as String?,
    precision: DatePrecision.fromWire(json['precision']),
    display: json['display'] as String?,
    lunar: json['lunar'] as String?,
  );

  /// Render `date` when precision is exact, else `display`, falling back to
  /// `date`. `display` and `lunar` are stored user-entered text and are
  /// returned verbatim in every locale — never translate them.
  String? get rendered {
    if (precision == DatePrecision.exact && date != null) return date;
    return display ?? date;
  }

  /// ISO date when known, else empty so unknowns sort last.
  String get sortKey => date ?? '';
}
```

- [ ] **Step 5: Generate and run**

```bash
cd mobile && dart run build_runner build && flutter test test/domain/historical_date_test.dart
```
Expected: `wrote 1 output` then `All tests passed!` (8 tests). `historical_date.freezed.dart` is a `part of` file with no imports, so it cannot trip the boundary test.

- [ ] **Step 6: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && dart run build_runner build && git diff --exit-code \
  && flutter analyze && flutter test
git add mobile/lib/domain mobile/test/domain
git commit -m "$(cat <<'EOF'
feat(mobile): add domain shared kernel (HistoricalDate, Page, ids)

HistoricalDate owns the ADR-011 render rule and sort key. Unknown
precision values from the backend degrade to `unknown` rather than
throwing. Page<T> carries the opaque cursor. Pure Dart throughout.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 4: Error taxonomy and `policyActionFor`

**Files:**
- Create: `mobile/lib/core/network/api_exception.dart`
- Test: `mobile/test/core/network/api_exception_test.dart`

**Interfaces:**
- Produces:
  - `sealed class AppException implements Exception`
  - `final class ApiException extends AppException` with `code`, `message`, `status`, `detail`, `traceId`, plus `int? get currentVersion`, `int? get retryAfter`
  - `final class NetworkException(Object? cause)`, `final class TimeoutException()`, `final class MalformedResponseException(Object? body)`
  - `enum PolicyAction`
  - `PolicyAction policyActionFor(String code, {int? status})`

- [ ] **Step 1: Write the failing test**

`mobile/test/core/network/api_exception_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';

void main() {
  group('policyActionFor covers the contract', () {
    test('401 family refreshes', () {
      expect(policyActionFor('missing_token'), PolicyAction.refreshThenRetry);
      expect(policyActionFor('invalid_token'), PolicyAction.refreshThenRetry);
      expect(policyActionFor('unauthorized'), PolicyAction.refreshThenRetry);
    });

    test('a dead refresh token signs out instead of refreshing again', () {
      expect(
        policyActionFor('auth.invalid_refresh_token'),
        PolicyAction.signOut,
      );
    });

    test('403 codes route, they never refresh or sign out', () {
      expect(
        policyActionFor('email_not_verified'),
        PolicyAction.resendVerification,
      );
      expect(
        policyActionFor('account_deactivated'),
        PolicyAction.blockedAccount,
      );
      expect(policyActionFor('clan_suspended'), PolicyAction.clanBlocked);
      expect(
        policyActionFor('no_approved_clan_membership'),
        PolicyAction.pendingOrOnboarding,
      );
      expect(
        policyActionFor('clan_membership_required'),
        PolicyAction.pendingOrOnboarding,
      );
    });

    test('clan-context codes', () {
      expect(
        policyActionFor('multiple_clans_no_selection'),
        PolicyAction.clanPicker,
      );
      expect(
        policyActionFor('invalid_clan_id_format'),
        PolicyAction.clearClanAndReResolve,
      );
    });

    test('stale_write reloads and reapplies, never blind-retries', () {
      expect(policyActionFor('stale_write'), PolicyAction.reloadAndReapply);
    });

    test('clan_founder_not_found is an onboarding state, not a 404', () {
      expect(
        policyActionFor('clan_founder_not_found'),
        PolicyAction.founderOnboarding,
      );
    });

    test('transient outages are not credential errors', () {
      expect(
        policyActionFor('auth_provider_unavailable'),
        PolicyAction.transientOutage,
      );
      expect(
        policyActionFor('storage_unavailable'),
        PolicyAction.transientOutage,
      );
      expect(
        policyActionFor('database_unavailable'),
        PolicyAction.transientOutage,
      );
    });

    test('rate limiting backs off', () {
      expect(policyActionFor('rate_limited'), PolicyAction.backOff);
    });

    test('a bad cursor drops the cursor and refetches page one', () {
      expect(policyActionFor('invalid_cursor'), PolicyAction.dropCursorRefetch);
    });

    test('an unknown code with a 401 status still refreshes', () {
      expect(
        policyActionFor('something_new', status: 401),
        PolicyAction.refreshThenRetry,
      );
    });

    test('an unknown code with a normal status does nothing special', () {
      expect(policyActionFor('person_not_found'), PolicyAction.none);
      expect(policyActionFor('person_not_found', status: 404),
          PolicyAction.none);
    });
  });

  group('ApiException detail accessors', () {
    test('exposes current_version for stale_write', () {
      const e = ApiException(
        code: 'stale_write',
        message: 'người khác vừa sửa',
        status: 409,
        detail: <String, Object?>{'current_version': 7},
      );
      expect(e.currentVersion, 7);
      expect(e.retryAfter, isNull);
    });

    test('exposes retry_after for rate_limited', () {
      const e = ApiException(
        code: 'rate_limited',
        message: 'quá nhiều yêu cầu',
        status: 429,
        detail: <String, Object?>{'retry_after': 30},
      );
      expect(e.retryAfter, 30);
    });
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/network/api_exception_test.dart
```
Expected: FAIL — cannot resolve `api_exception.dart`.

- [ ] **Step 3: Write the implementation**

`mobile/lib/core/network/api_exception.dart`:

```dart
/// The client-side error taxonomy. Every failure that reaches a notifier is
/// one of these four; nothing above `core/network` sees a `DioException`.
sealed class AppException implements Exception {
  const AppException();
}

/// Any response carrying an `{"error": {...}}` body.
final class ApiException extends AppException {
  const ApiException({
    required this.code,
    required this.message,
    required this.status,
    this.detail = const <String, Object?>{},
    this.traceId,
  });

  /// Stable machine code — branch on this.
  final String code;

  /// Already localised server-side from Accept-Language. Display directly;
  /// never parse it, never translate it client-side.
  final String message;
  final int status;
  final Map<String, Object?> detail;

  /// Short id surfaced to the user so a report links to a backend log line.
  final String? traceId;

  int? get currentVersion => detail['current_version'] as int?;
  int? get retryAfter => detail['retry_after'] as int?;

  @override
  String toString() => 'ApiException($status $code): $message';
}

/// Transport, DNS, offline.
final class NetworkException extends AppException {
  const NetworkException(this.cause);
  final Object? cause;
}

/// Deadline exceeded.
final class TimeoutException extends AppException {
  const TimeoutException();
}

/// The body did not match the canonical envelope.
final class MalformedResponseException extends AppException {
  const MalformedResponseException(this.body);
  final Object? body;
}

/// What the app should do about a backend error code.
enum PolicyAction {
  none,
  refreshThenRetry,
  signOut,
  resendVerification,
  blockedAccount,
  clanBlocked,
  pendingOrOnboarding,
  clanPicker,
  clearClanAndReResolve,
  reloadAndReapply,
  founderOnboarding,
  backOff,
  transientOutage,
  dropCursorRefetch,
}

/// The single mapping from a backend error code to a routing decision.
/// Every UI branch on an error goes through here. `status` only disambiguates
/// unknown codes; known codes are decided by `code` alone.
PolicyAction policyActionFor(String code, {int? status}) {
  switch (code) {
    case 'missing_token':
    case 'invalid_token':
    case 'unauthorized':
      return PolicyAction.refreshThenRetry;
    case 'auth.invalid_refresh_token':
      return PolicyAction.signOut;
    case 'email_not_verified':
      return PolicyAction.resendVerification;
    case 'account_deactivated':
      return PolicyAction.blockedAccount;
    case 'clan_suspended':
      return PolicyAction.clanBlocked;
    case 'no_approved_clan_membership':
    case 'clan_membership_required':
      return PolicyAction.pendingOrOnboarding;
    case 'multiple_clans_no_selection':
      return PolicyAction.clanPicker;
    case 'invalid_clan_id_format':
      return PolicyAction.clearClanAndReResolve;
    case 'stale_write':
      return PolicyAction.reloadAndReapply;
    case 'clan_founder_not_found':
      return PolicyAction.founderOnboarding;
    case 'rate_limited':
      return PolicyAction.backOff;
    case 'auth_provider_unavailable':
    case 'storage_unavailable':
    case 'database_unavailable':
      return PolicyAction.transientOutage;
    case 'invalid_cursor':
      return PolicyAction.dropCursorRefetch;
    default:
      if (status == 401) return PolicyAction.refreshThenRetry;
      return PolicyAction.none;
  }
}
```

- [ ] **Step 4: Run the test**

```bash
cd mobile && flutter test test/core/network/api_exception_test.dart
```
Expected: `All tests passed!` (13 tests).

- [ ] **Step 5: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/network/api_exception.dart mobile/test/core/network/api_exception_test.dart
git commit -m "$(cat <<'EOF'
feat(mobile): add sealed error taxonomy and policyActionFor

policyActionFor is the single backend-code -> routing decision, covering
every code in docs/contracts/error-codes.md that the client must act on.
UI branches on code, never on message.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 5: Envelope unwrapping — the one place `{"data": …}` is opened

**Files:**
- Create: `mobile/lib/core/network/envelope.dart`
- Test: `mobile/test/core/network/envelope_test.dart`

**Interfaces:**
- Consumes: `Page<T>` (Task 3), `MalformedResponseException` (Task 4)
- Produces: `typedef Parse<T> = T Function(Object? json);`, `T unwrapData<T>(Object? body, Parse<T> parse)`, `Page<T> unwrapPage<T>(Object? body, Parse<T> parse)`

- [ ] **Step 1: Write the failing test**

`mobile/test/core/network/envelope_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/envelope.dart';

void main() {
  group('unwrapData', () {
    test('pulls the data member', () {
      final v = unwrapData<String>(
        <String, Object?>{'data': 'hello'},
        (j) => j! as String,
      );
      expect(v, 'hello');
    });

    test('passes a map through to the parser', () {
      final v = unwrapData<int>(
        <String, Object?>{
          'data': <String, Object?>{'expires_in': 3600},
        },
        (j) => (j! as Map<String, Object?>)['expires_in']! as int,
      );
      expect(v, 3600);
    });

    test('throws MalformedResponseException when data is absent', () {
      expect(
        () => unwrapData<String>(
          <String, Object?>{'oops': 1},
          (j) => j! as String,
        ),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('throws MalformedResponseException on a non-map body', () {
      expect(
        () => unwrapData<String>('not json', (j) => j! as String),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('a null data member is legal and reaches the parser', () {
      final v = unwrapData<String?>(
        <String, Object?>{'data': null},
        (j) => j as String?,
      );
      expect(v, isNull);
    });
  });

  group('unwrapPage', () {
    test('reads cursor meta', () {
      final p = unwrapPage<int>(
        <String, Object?>{
          'data': <Object?>[1, 2],
          'meta': <String, Object?>{
            'cursor': 'b3BhcXVl',
            'has_more': true,
            'limit': 2,
          },
        },
        (j) => j! as int,
      );
      expect(p.items, <int>[1, 2]);
      expect(p.cursor, 'b3BhcXVl');
      expect(p.hasMore, isTrue);
      expect(p.limit, 2);
    });

    test('tolerates a meta-less array — GET /me/clans is a plain array', () {
      final p = unwrapPage<int>(
        <String, Object?>{
          'data': <Object?>[7, 8, 9],
        },
        (j) => j! as int,
      );
      expect(p.items, <int>[7, 8, 9]);
      expect(p.cursor, isNull);
      expect(p.hasMore, isFalse);
      expect(p.limit, 3);
    });

    test('an empty list is a valid page, not an error', () {
      final p = unwrapPage<int>(
        <String, Object?>{'data': <Object?>[]},
        (j) => j! as int,
      );
      expect(p.items, isEmpty);
      expect(p.hasMore, isFalse);
    });

    test('throws when data is not a list', () {
      expect(
        () => unwrapPage<int>(
          <String, Object?>{'data': <String, Object?>{}},
          (j) => j! as int,
        ),
        throwsA(isA<MalformedResponseException>()),
      );
    });

    test('the cursor is carried verbatim and never inspected', () {
      const weird = 'not-base64!!:{}';
      final p = unwrapPage<int>(
        <String, Object?>{
          'data': <Object?>[1],
          'meta': <String, Object?>{
            'cursor': weird,
            'has_more': true,
            'limit': 1,
          },
        },
        (j) => j! as int,
      );
      expect(p.cursor, weird);
    });
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/network/envelope_test.dart
```
Expected: FAIL — cannot resolve `envelope.dart`.

- [ ] **Step 3: Write the implementation**

`mobile/lib/core/network/envelope.dart`:

```dart
import '../../domain/shared/page.dart';
import 'api_exception.dart';

typedef Parse<T> = T Function(Object? json);

/// The ONLY place the canonical `{"data": ...}` envelope is opened (ADR-010).
/// No widget, notifier or repository ever sees the wrapper.
T unwrapData<T>(Object? body, Parse<T> parse) {
  if (body is! Map<String, Object?> || !body.containsKey('data')) {
    throw MalformedResponseException(body);
  }
  return parse(body['data']);
}

/// Cursor lists add `meta: {cursor, has_more, limit}`. Endpoints that return a
/// plain canonical array with no `meta` — `GET /me/clans` — are treated as a
/// single complete page.
Page<T> unwrapPage<T>(Object? body, Parse<T> parse) {
  if (body is! Map<String, Object?> || body['data'] is! List) {
    throw MalformedResponseException(body);
  }
  final items = (body['data']! as List<Object?>).map(parse).toList();
  final meta = body['meta'];
  if (meta is! Map<String, Object?>) {
    return Page<T>(
      items: items,
      cursor: null,
      hasMore: false,
      limit: items.length,
    );
  }
  return Page<T>(
    items: items,
    // Opaque: stored and replayed verbatim, never parsed.
    cursor: meta['cursor'] as String?,
    hasMore: meta['has_more'] as bool? ?? false,
    limit: meta['limit'] as int? ?? items.length,
  );
}
```

- [ ] **Step 4: Run the test**

```bash
cd mobile && flutter test test/core/network/envelope_test.dart
```
Expected: `All tests passed!` (10 tests).

- [ ] **Step 5: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/network/envelope.dart mobile/test/core/network/envelope_test.dart
git commit -m "$(cat <<'EOF'
feat(mobile): unwrap the canonical envelope in exactly one place

unwrapData/unwrapPage are the only functions that know about {"data": ...}.
Handles the meta-less array shape used by GET /me/clans, and carries the
opaque cursor verbatim.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 6: Header interceptors — auth, clan, locale, trace

**Files:**
- Create: `mobile/lib/core/network/interceptors/{auth,clan,locale,trace}_interceptor.dart`, `mobile/lib/core/observability/traceparent.dart`
- Test: `mobile/test/support/sequence_adapter.dart`, `mobile/test/core/network/interceptors_test.dart`

**Interfaces:**
- Produces:
  - `bool isClanScoped(String path)`
  - `AuthInterceptor(String? Function() accessToken)`, `ClanInterceptor(String? Function() currentClanId)`, `LocaleInterceptor(String Function() locale)`, `TraceInterceptor({String Function()? generator})`
  - `String newTraceparent({bool sampled = true})`
  - `class Canned(int statusCode, Object? body)` and `class SequenceAdapter implements HttpClientAdapter` with `List<RequestOptions> received`, `int callCount`

> **Why `SequenceAdapter` exists (V8):** `http_mock_adapter` 0.6.1 fixes the status code at registration (`reply(status, data)`), `replyCallback` varies only the body, and duplicate registrations do not queue — the matcher keeps the **last** match. It cannot express "401 then 200". Task 7 needs exactly that, so the adapter is built here and shared.

- [ ] **Step 1: Write the shared test double**

`mobile/test/support/sequence_adapter.dart`:

```dart
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

class Canned {
  const Canned(this.statusCode, this.body);
  final int statusCode;
  final Object? body;
}

/// Returns each canned response in order, repeating the last one thereafter,
/// and records every RequestOptions it saw.
class SequenceAdapter implements HttpClientAdapter {
  SequenceAdapter(this._responses);

  final List<Canned> _responses;
  final List<RequestOptions> received = <RequestOptions>[];

  int get callCount => received.length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    received.add(options);
    final index = received.length <= _responses.length
        ? received.length - 1
        : _responses.length - 1;
    final canned = _responses[index];
    return ResponseBody.fromString(
      jsonEncode(canned.body),
      canned.statusCode,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
```

- [ ] **Step 2: Write the failing test**

`mobile/test/core/network/interceptors_test.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/interceptors/auth_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/clan_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/locale_interceptor.dart';
import 'package:family_roots_mobile/core/network/interceptors/trace_interceptor.dart';
import 'package:family_roots_mobile/core/observability/traceparent.dart';

import '../../support/sequence_adapter.dart';

Dio _dio(SequenceAdapter a) =>
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a;

SequenceAdapter _ok() => SequenceAdapter(<Canned>[
  const Canned(200, <String, Object?>{'data': null}),
]);

void main() {
  group('isClanScoped', () {
    test('clan-scoped routes', () {
      expect(isClanScoped('/persons'), isTrue);
      expect(isClanScoped('/tree'), isTrue);
      expect(isClanScoped('/events'), isTrue);
      expect(isClanScoped('/documents'), isTrue);
      expect(isClanScoped('/relationships/marriages'), isTrue);
      expect(isClanScoped('/branches'), isTrue);
      expect(isClanScoped('/claims'), isTrue);
      expect(isClanScoped('/clans/me/founder'), isTrue);
    });

    test('exempt routes', () {
      expect(isClanScoped('/auth/login'), isFalse);
      expect(isClanScoped('/auth/me'), isFalse);
      expect(isClanScoped('/auth/refresh'), isFalse);
      expect(isClanScoped('/me/clans'), isFalse);
      expect(isClanScoped('/me/clans/abc-123/select'), isFalse);
      expect(isClanScoped('/platform/audit'), isFalse);
      expect(isClanScoped('/invitations/tok/accept'), isFalse);
    });

    test('an invitations route that is not /accept stays clan-scoped', () {
      expect(isClanScoped('/invitations'), isTrue);
    });
  });

  test('AuthInterceptor attaches the bearer token', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(AuthInterceptor(() => 'tok')))
        .get<Object?>('/persons');
    expect(a.received.single.headers['Authorization'], 'Bearer tok');
  });

  test('AuthInterceptor omits the header when signed out', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(AuthInterceptor(() => null)))
        .get<Object?>('/auth/login');
    expect(a.received.single.headers.containsKey('Authorization'), isFalse);
  });

  test('ClanInterceptor attaches only on clan-scoped routes', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final dio = _dio(a)..interceptors.add(ClanInterceptor(() => 'clan-1'));

    await dio.get<Object?>('/persons');
    expect(a.received[0].headers['X-Current-Clan-Id'], 'clan-1');

    await dio.get<Object?>('/me/clans');
    expect(a.received[1].headers.containsKey('X-Current-Clan-Id'), isFalse);
  });

  test('ClanInterceptor omits the header when no clan is selected', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(ClanInterceptor(() => null)))
        .get<Object?>('/persons');
    expect(
      a.received.single.headers.containsKey('X-Current-Clan-Id'),
      isFalse,
    );
  });

  test('LocaleInterceptor sends the app locale', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(LocaleInterceptor(() => 'vi')))
        .get<Object?>('/persons');
    expect(a.received.single.headers['Accept-Language'], 'vi');
  });

  test('TraceInterceptor sends a W3C traceparent', () async {
    final a = _ok();
    await (_dio(a)..interceptors.add(TraceInterceptor()))
        .get<Object?>('/persons');
    final tp = a.received.single.headers['traceparent']! as String;
    expect(
      RegExp(r'^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$').hasMatch(tp),
      isTrue,
      reason: tp,
    );
  });

  test('each request gets a distinct traceparent', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final dio = _dio(a)..interceptors.add(TraceInterceptor());
    await dio.get<Object?>('/persons');
    await dio.get<Object?>('/persons');
    expect(
      a.received[0].headers['traceparent'],
      isNot(a.received[1].headers['traceparent']),
    );
  });

  test('newTraceparent honours the sampled flag', () {
    expect(newTraceparent().endsWith('-01'), isTrue);
    expect(newTraceparent(sampled: false).endsWith('-00'), isTrue);
  });
}
```

- [ ] **Step 3: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/network/interceptors_test.dart
```
Expected: FAIL — the interceptor files do not exist.

- [ ] **Step 4: Write `traceparent.dart`**

`mobile/lib/core/observability/traceparent.dart`:

```dart
import 'dart:math';

final _rng = Random.secure();

String _hex(int bytes) {
  final buffer = StringBuffer();
  for (var i = 0; i < bytes; i++) {
    buffer.write(_rng.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}

/// A W3C trace-context `traceparent` (ADR-033), so a mobile span joins the
/// backend trace: `00-<32 hex trace-id>-<16 hex span-id>-<2 hex flags>`.
String newTraceparent({bool sampled = true}) =>
    '00-${_hex(16)}-${_hex(8)}-${sampled ? '01' : '00'}';
```

- [ ] **Step 5: Write the four interceptors**

`mobile/lib/core/network/interceptors/auth_interceptor.dart`:

```dart
import 'package:dio/dio.dart';

/// Attaches `Authorization: Bearer <token>` from the current Supabase session.
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._accessToken);
  final String? Function() _accessToken;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _accessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
```

`mobile/lib/core/network/interceptors/clan_interceptor.dart`:

```dart
import 'package:dio/dio.dart';

/// Routes that must NOT carry `X-Current-Clan-Id`: `/auth/*`, `/me/clans`,
/// `/me/clans/{id}/select`, `/invitations/{token}/accept`, `/platform/*`.
bool isClanScoped(String path) {
  const exempt = <String>['/auth/', '/me/clans', '/platform/'];
  for (final prefix in exempt) {
    if (path.startsWith(prefix)) return false;
  }
  if (path.startsWith('/invitations/') && path.endsWith('/accept')) {
    return false;
  }
  return true;
}

/// Sent on every clan-scoped request, including for single-clan users, so
/// behaviour stays deterministic if the user later joins a second clan.
class ClanInterceptor extends Interceptor {
  ClanInterceptor(this._currentClanId);
  final String? Function() _currentClanId;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final clanId = _currentClanId();
    if (clanId != null && isClanScoped(options.path)) {
      options.headers['X-Current-Clan-Id'] = clanId;
    }
    handler.next(options);
  }
}
```

`mobile/lib/core/network/interceptors/locale_interceptor.dart`:

```dart
import 'package:dio/dio.dart';

/// Drives all server-localised text. The app owns its locale and never reads
/// the backend's `preferred_locale`, which always returns "vi" (spec R3).
class LocaleInterceptor extends Interceptor {
  LocaleInterceptor(this._locale);
  final String Function() _locale;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['Accept-Language'] = _locale();
    handler.next(options);
  }
}
```

`mobile/lib/core/network/interceptors/trace_interceptor.dart`:

```dart
import 'package:dio/dio.dart';

import '../../observability/traceparent.dart';

/// W3C trace context (ADR-033): a crash on a phone links to the exact backend
/// log line.
class TraceInterceptor extends Interceptor {
  TraceInterceptor({String Function()? generator})
    : _generator = generator ?? newTraceparent;

  final String Function() _generator;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['traceparent'] = _generator();
    handler.next(options);
  }
}
```

- [ ] **Step 6: Run the tests**

```bash
cd mobile && flutter test test/core/network/interceptors_test.dart
```
Expected: `All tests passed!` (10 tests).

- [ ] **Step 7: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core mobile/test
git commit -m "$(cat <<'EOF'
feat(mobile): add auth, clan, locale and trace interceptors

X-Current-Clan-Id is attached only on clan-scoped routes; /auth/*,
/me/clans, /platform/* and invitation accept are exempt. traceparent
follows W3C trace context per ADR-033.

Adds test/support/sequence_adapter.dart: http_mock_adapter 0.6.1 fixes
the status code at registration and keeps the last matching handler, so
it cannot express a 401-then-200 sequence.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 7: Single-flight refresh and retry-exactly-once

**Files:**
- Create: `mobile/lib/core/network/token_refresher.dart`, `mobile/lib/core/network/interceptors/refresh_interceptor.dart`
- Test: `mobile/test/core/network/refresh_test.dart`

**Interfaces:**
- Consumes: `SequenceAdapter`, `Canned` (Task 6)
- Produces:
  - `class TokenRefresher(Future<String?> Function() refresh)` → `Future<String?> refresh()`, `int refreshCallCount`
  - `class RefreshInterceptor({required TokenRefresher refresher, required Dio retryDio, required void Function() onSignOut})`

> Spec D8: a browser tab is alive, a phone is backgrounded for days. This is the reactive single-flight strategy `frontend-integration-guide.md` §2 recommends for non-Supabase-SDK clients.

- [ ] **Step 1: Write the failing test**

`mobile/test/core/network/refresh_test.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/interceptors/refresh_interceptor.dart';
import 'package:family_roots_mobile/core/network/token_refresher.dart';

import '../../support/sequence_adapter.dart';

const _unauthorized = <String, Object?>{
  'error': <String, Object?>{
    'code': 'invalid_token',
    'message': 'Token không hợp lệ',
    'detail': <String, Object?>{},
  },
};

Dio _dio(SequenceAdapter a) =>
    Dio(BaseOptions(baseUrl: 'https://api.test'))..httpClientAdapter = a;

void main() {
  group('TokenRefresher', () {
    test('concurrent callers share one in-flight refresh', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return 'new-token';
      });

      final results = await Future.wait<String?>(<Future<String?>>[
        refresher.refresh(),
        refresher.refresh(),
        refresher.refresh(),
      ]);

      expect(results, <String?>['new-token', 'new-token', 'new-token']);
      expect(calls, 1);
    });

    test('a later refresh starts a new flight', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        return 't$calls';
      });
      expect(await refresher.refresh(), 't1');
      expect(await refresher.refresh(), 't2');
      expect(calls, 2);
    });

    test('a throwing refresh does not wedge the refresher', () async {
      var calls = 0;
      final refresher = TokenRefresher(() async {
        calls++;
        if (calls == 1) throw StateError('boom');
        return 'ok';
      });
      await expectLater(refresher.refresh(), throwsStateError);
      expect(await refresher.refresh(), 'ok');
    });
  });

  group('RefreshInterceptor', () {
    test('401 refreshes once and retries exactly once', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(401, _unauthorized),
        const Canned(200, <String, Object?>{'data': <Object?>[]}),
      ]);
      final dio = _dio(a);

      var signedOut = false;
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () => signedOut = true,
        ),
      );

      final res = await dio.get<Object?>('/persons');
      expect(res.statusCode, 200);
      expect(a.callCount, 2);
      expect(a.received.last.headers['Authorization'], 'Bearer fresh');
      expect(refresher.refreshCallCount, 1);
      expect(signedOut, isFalse);
    });

    test('a failed refresh signs out and does not loop', () async {
      final a = SequenceAdapter(<Canned>[const Canned(401, _unauthorized)]);
      final dio = _dio(a);

      var signedOut = false;
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: TokenRefresher(() async => null),
          retryDio: dio,
          onSignOut: () => signedOut = true,
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(signedOut, isTrue);
      expect(a.callCount, 1);
    });

    test('a second 401 on the retry is not retried again', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(401, _unauthorized),
        const Canned(401, _unauthorized),
      ]);
      final dio = _dio(a);
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(a.callCount, 2);
      expect(refresher.refreshCallCount, 1);
    });

    test('a non-401 error passes straight through', () async {
      final a = SequenceAdapter(<Canned>[
        const Canned(403, <String, Object?>{
          'error': <String, Object?>{
            'code': 'insufficient_permissions',
            'message': 'Không đủ quyền',
            'detail': <String, Object?>{},
          },
        }),
      ]);
      final dio = _dio(a);
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      await expectLater(
        dio.get<Object?>('/persons'),
        throwsA(isA<DioException>()),
      );
      expect(refresher.refreshCallCount, 0);
      expect(a.callCount, 1);
    });

    test('a cancellation is rethrown unchanged and never refreshes', () async {
      final dio = _dio(
        SequenceAdapter(<Canned>[
          const Canned(200, <String, Object?>{'data': null}),
        ]),
      );
      final refresher = TokenRefresher(() async => 'fresh');
      dio.interceptors.add(
        RefreshInterceptor(
          refresher: refresher,
          retryDio: dio,
          onSignOut: () {},
        ),
      );

      final token = CancelToken()..cancel('user left the screen');
      await expectLater(
        dio.get<Object?>('/persons', cancelToken: token),
        throwsA(
          isA<DioException>().having(
            (e) => e.type,
            'type',
            DioExceptionType.cancel,
          ),
        ),
      );
      expect(refresher.refreshCallCount, 0);
    });
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/network/refresh_test.dart
```
Expected: FAIL — `token_refresher.dart` and `refresh_interceptor.dart` do not exist.

- [ ] **Step 3: Write `token_refresher.dart`**

```dart
/// Single-flight: concurrent callers await the same in-flight future, so a
/// burst of 401s produces exactly one refresh.
class TokenRefresher {
  TokenRefresher(this._refresh);

  final Future<String?> Function() _refresh;
  Future<String?>? _inFlight;

  /// Underlying refreshes actually performed. Test-facing.
  int refreshCallCount = 0;

  Future<String?> refresh() {
    final existing = _inFlight;
    if (existing != null) return existing;
    refreshCallCount++;
    // whenComplete also clears the slot on error, so a failed refresh does
    // not wedge every later attempt.
    final future = _refresh().whenComplete(() => _inFlight = null);
    _inFlight = future;
    return future;
  }
}
```

- [ ] **Step 4: Write `refresh_interceptor.dart`**

```dart
import 'package:dio/dio.dart';

import '../token_refresher.dart';

const _retriedFlag = 'familyroots.retried';

/// On 401: one shared refresh, concurrent 401s queued behind it, retry the
/// original request exactly once; on refresh failure, sign out.
class RefreshInterceptor extends Interceptor {
  RefreshInterceptor({
    required this.refresher,
    required this.retryDio,
    required this.onSignOut,
  });

  final TokenRefresher refresher;
  final Dio retryDio;
  final void Function() onSignOut;

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    // A caller-initiated cancellation is rethrown unchanged and is never
    // reported as a network or auth failure.
    if (err.type == DioExceptionType.cancel) {
      handler.next(err);
      return;
    }

    final options = err.requestOptions;
    if (err.response?.statusCode != 401 ||
        options.extra[_retriedFlag] == true) {
      handler.next(err);
      return;
    }

    final String? token;
    try {
      token = await refresher.refresh();
    } on Object {
      onSignOut();
      handler.next(err);
      return;
    }

    if (token == null) {
      onSignOut();
      handler.next(err);
      return;
    }

    options.extra[_retriedFlag] = true;
    options.headers['Authorization'] = 'Bearer $token';
    try {
      handler.resolve(await retryDio.fetch<Object?>(options));
    } on DioException catch (e) {
      handler.next(e);
    }
  }
}
```

- [ ] **Step 5: Run the tests**

```bash
cd mobile && flutter test test/core/network/refresh_test.dart
```
Expected: `All tests passed!` (8 tests).

- [ ] **Step 6: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/network mobile/test/core/network
git commit -m "$(cat <<'EOF'
feat(mobile): single-flight token refresh with retry-exactly-once

Concurrent 401s queue behind one refresh; the original request is retried
exactly once and never loops. Refresh failure signs out. Cancellations are
rethrown unchanged. Implements ADR-034 D8.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 8: Secure session storage and preferences

**Files:**
- Create: `mobile/lib/core/storage/secure_session_store.dart`, `mobile/lib/core/storage/prefs_store.dart`
- Test: `mobile/test/core/storage/secure_session_store_test.dart`

**Interfaces:**
- Produces:
  - `class SecureSessionStore extends LocalStorage` with `static const sessionKey`
  - `class SecurePkceStore extends GotrueAsyncStorage`
  - `class PrefsStore` — `static Future<PrefsStore> open()`, `String? readClanId()`, `Future<void> writeClanId(String)`, `Future<void> clearClanId()`, `String? readLocale()`, `Future<void> writeLocale(String)`

> **Two stores, not one (V10).** `LocalStorage` covers the session; the PKCE code verifier goes through a *separate* `GotrueAsyncStorage`. Leaving it default puts the verifier in SharedPreferences plaintext, which `frontend-integration-guide.md` §2 forbids. Clan selection and locale are *not* secrets — spec §4.3 puts them in ordinary preferences.
>
> **Verified (V11):** pass a bare `AndroidOptions()`. `encryptedSharedPreferences: true` is deprecated, ignored, and removed in v11; v10's default is already KeyStore-backed AES-GCM with RSA-OAEP key wrapping.

- [ ] **Step 1: Write the failing test**

Platform channels are unavailable under `flutter test`, so this injects a fake `FlutterSecureStorage` and asserts the `LocalStorage` contract. Real Keychain/Keystore behaviour is N3 and is covered by the device run in Task 18.

`mobile/test/core/storage/secure_session_store_test.dart`:

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/core/storage/secure_session_store.dart';

class _MockSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late _MockSecureStorage storage;
  late SecureSessionStore store;

  setUp(() {
    storage = _MockSecureStorage();
    store = SecureSessionStore(storage: storage);
  });

  test('is a supabase LocalStorage', () {
    expect(store, isA<LocalStorage>());
  });

  test('initialize does not touch the keystore', () async {
    await store.initialize();
    verifyZeroInteractions(storage);
  });

  test('persistSession writes under the namespaced key', () async {
    when(
      () => storage.write(key: any(named: 'key'), value: any(named: 'value')),
    ).thenAnswer((_) async {});

    await store.persistSession('{"access_token":"a"}');

    verify(
      () => storage.write(
        key: SecureSessionStore.sessionKey,
        value: '{"access_token":"a"}',
      ),
    ).called(1);
  });

  test('accessToken, hasAccessToken and removePersistedSession', () async {
    when(
      () => storage.read(key: SecureSessionStore.sessionKey),
    ).thenAnswer((_) async => '{"access_token":"a"}');
    when(
      () => storage.containsKey(key: SecureSessionStore.sessionKey),
    ).thenAnswer((_) async => true);
    when(() => storage.delete(key: any(named: 'key'))).thenAnswer((_) async {});

    expect(await store.accessToken(), '{"access_token":"a"}');
    expect(await store.hasAccessToken(), isTrue);

    await store.removePersistedSession();
    verify(() => storage.delete(key: SecureSessionStore.sessionKey)).called(1);
  });

  test('the PKCE verifier store is secure too', () async {
    final pkce = SecurePkceStore(storage: storage);
    expect(pkce, isA<GotrueAsyncStorage>());

    when(
      () => storage.write(key: any(named: 'key'), value: any(named: 'value')),
    ).thenAnswer((_) async {});

    await pkce.setItem(key: 'verifier', value: 'v1');
    verify(() => storage.write(key: 'verifier', value: 'v1')).called(1);
  });

  test('PrefsStore round-trips clan id and locale', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await PrefsStore.open();

    expect(prefs.readClanId(), isNull);
    await prefs.writeClanId('clan-1');
    expect(prefs.readClanId(), 'clan-1');
    await prefs.clearClanId();
    expect(prefs.readClanId(), isNull);

    expect(prefs.readLocale(), isNull);
    await prefs.writeLocale('vi');
    expect(prefs.readLocale(), 'vi');
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/storage/secure_session_store_test.dart
```
Expected: FAIL — cannot resolve `secure_session_store.dart`.

- [ ] **Step 3: Write `secure_session_store.dart`**

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const _defaultStorage = FlutterSecureStorage(
  // v10's default is already KeyStore-backed AES-GCM with RSA-OAEP key
  // wrapping. `encryptedSharedPreferences` is deprecated, ignored, and gone
  // in v11 — do not pass it.
  aOptions: AndroidOptions(),
  iOptions: IOSOptions(
    accessibility: KeychainAccessibility.first_unlock_this_device,
  ),
);

/// The Supabase session at rest: iOS Keychain / Android Keystore, never
/// SharedPreferences (frontend-integration-guide.md §2, ADR-034 D6).
class SecureSessionStore extends LocalStorage {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? _defaultStorage;

  static const sessionKey = 'familyroots.supabase.session';

  final FlutterSecureStorage _storage;

  @override
  Future<void> initialize() async {}

  @override
  Future<bool> hasAccessToken() => _storage.containsKey(key: sessionKey);

  @override
  Future<String?> accessToken() => _storage.read(key: sessionKey);

  @override
  Future<void> removePersistedSession() => _storage.delete(key: sessionKey);

  @override
  Future<void> persistSession(String persistSessionString) =>
      _storage.write(key: sessionKey, value: persistSessionString);
}

/// The PKCE code verifier needs securing too — the default implementation
/// writes it to SharedPreferences in plaintext.
class SecurePkceStore extends GotrueAsyncStorage {
  SecurePkceStore({FlutterSecureStorage? storage})
    : _storage = storage ?? _defaultStorage;

  final FlutterSecureStorage _storage;

  @override
  Future<String?> getItem({required String key}) => _storage.read(key: key);

  @override
  Future<void> removeItem({required String key}) => _storage.delete(key: key);

  @override
  Future<void> setItem({required String key, required String value}) =>
      _storage.write(key: key, value: value);
}
```

- [ ] **Step 4: Write `prefs_store.dart`**

```dart
import 'package:shared_preferences/shared_preferences.dart';

/// Non-secret client state: the selected clan and the user's chosen locale.
/// The app owns the locale and never reads the backend's `preferred_locale`,
/// which always returns "vi" (documented backend gap, spec R3).
class PrefsStore {
  PrefsStore(this._prefs);

  static const _clanKey = 'familyroots.selected_clan_id';
  static const _localeKey = 'familyroots.locale';

  final SharedPreferences _prefs;

  static Future<PrefsStore> open() async =>
      PrefsStore(await SharedPreferences.getInstance());

  String? readClanId() => _prefs.getString(_clanKey);
  Future<void> writeClanId(String clanId) => _prefs.setString(_clanKey, clanId);
  Future<void> clearClanId() => _prefs.remove(_clanKey);

  String? readLocale() => _prefs.getString(_localeKey);
  Future<void> writeLocale(String locale) =>
      _prefs.setString(_localeKey, locale);
}
```

- [ ] **Step 5: Run the tests**

```bash
cd mobile && flutter test test/core/storage/secure_session_store_test.dart
```
Expected: `All tests passed!` (6 tests).

- [ ] **Step 6: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/storage mobile/test/core/storage
git commit -m "$(cat <<'EOF'
feat(mobile): store the Supabase session in platform secure storage

Implements supabase_flutter's LocalStorage over flutter_secure_storage
(ADR-034 D6) and secures the PKCE code verifier through a matching
GotrueAsyncStorage, which the default leaves in SharedPreferences
plaintext. Clan selection and locale stay in ordinary preferences.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 9: sqflite read cache

**Files:**
- Create: `mobile/lib/core/storage/cache_store.dart`
- Test: `mobile/test/core/storage/cache_store_test.dart`

**Interfaces:**
- Produces:
  - `class CachedPayload(Object? body, DateTime storedAt)`
  - `abstract class CacheStore` — `put`, `get`, `remove`, `clear`
  - `class SqfliteCacheStore implements CacheStore` with `static const table`, `static const createTableSql`, `static Future<SqfliteCacheStore> open()`

> **Verified (V15):** `sqflite` throws `Bad state: databaseFactory not initialized` under `flutter test`. Every test touching it must call `sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` in `setUpAll`. `sqflite_common_ffi` is the dev dependency added in Task 1.

- [ ] **Step 1: Write the failing test**

`mobile/test/core/storage/cache_store_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:family_roots_mobile/core/storage/cache_store.dart';

void main() {
  setUpAll(() {
    // sqflite has no implementation under `flutter test`; the FFI factory
    // provides a real SQLite without a device.
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late SqfliteCacheStore store;

  setUp(() async {
    final db = await databaseFactory.openDatabase(
      inMemoryDatabasePath,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (d, _) => d.execute(SqfliteCacheStore.createTableSql),
      ),
    );
    store = SqfliteCacheStore(db);
  });

  test('round-trips a payload with a timestamp', () async {
    await store.put('GET /me/clans', <String, Object?>{
      'data': <Object?>[
        <String, Object?>{'clan_id': 'c1'},
      ],
    });

    final got = await store.get('GET /me/clans');
    expect(got, isNotNull);
    expect(got!.body, <String, Object?>{
      'data': <Object?>[
        <String, Object?>{'clan_id': 'c1'},
      ],
    });
    expect(DateTime.now().difference(got.storedAt).inSeconds, lessThan(5));
  });

  test('a miss is null, not an error', () async {
    expect(await store.get('never written'), isNull);
  });

  test('put replaces an existing key rather than duplicating it', () async {
    await store.put('k', <String, Object?>{'v': 1});
    await store.put('k', <String, Object?>{'v': 2});
    expect((await store.get('k'))!.body, <String, Object?>{'v': 2});
  });

  test('remove drops one key', () async {
    await store.put('a', 1);
    await store.put('b', 2);
    await store.remove('a');
    expect(await store.get('a'), isNull);
    expect((await store.get('b'))!.body, 2);
  });

  test('clear empties the cache — used on sign-out', () async {
    await store.put('a', 1);
    await store.put('b', 2);
    await store.clear();
    expect(await store.get('a'), isNull);
    expect(await store.get('b'), isNull);
  });

  test('stores lists as well as maps', () async {
    await store.put('list', <Object?>[1, 'two', null]);
    expect((await store.get('list'))!.body, <Object?>[1, 'two', null]);
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/storage/cache_store_test.dart
```
Expected: FAIL — cannot resolve `cache_store.dart`.

- [ ] **Step 3: Write the implementation**

`mobile/lib/core/storage/cache_store.dart`:

```dart
import 'dart:convert';

import 'package:sqflite/sqflite.dart';

class CachedPayload {
  const CachedPayload(this.body, this.storedAt);

  /// The decoded payload — already unwrapped from the envelope.
  final Object? body;
  final DateTime storedAt;
}

/// Read cache only (ADR-034 consequence 7): every successful network read is
/// written here so it can be re-served when the network fails. Writes always
/// require connectivity — there is no write queue and no offline conflict
/// resolution.
///
/// Presigned URLs are excluded by rule: they expire after 3600s and must never
/// be persisted (frontend-integration-guide.md §8).
abstract class CacheStore {
  Future<void> put(String key, Object? body);
  Future<CachedPayload?> get(String key);
  Future<void> remove(String key);
  Future<void> clear();
}

class SqfliteCacheStore implements CacheStore {
  SqfliteCacheStore(this._db);

  static const table = 'response_cache';

  static const createTableSql =
      '''
CREATE TABLE IF NOT EXISTS $table (
  key TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  stored_at INTEGER NOT NULL
)''';

  final Database _db;

  static Future<SqfliteCacheStore> open() async {
    final path = '${await getDatabasesPath()}/familyroots_cache.db';
    final db = await openDatabase(
      path,
      version: 1,
      onCreate: (d, _) => d.execute(createTableSql),
    );
    return SqfliteCacheStore(db);
  }

  @override
  Future<void> put(String key, Object? body) async {
    await _db.insert(table, <String, Object?>{
      'key': key,
      'body': jsonEncode(body),
      'stored_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  @override
  Future<CachedPayload?> get(String key) async {
    final rows = await _db.query(
      table,
      where: 'key = ?',
      whereArgs: <Object?>[key],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final row = rows.first;
    return CachedPayload(
      jsonDecode(row['body']! as String),
      DateTime.fromMillisecondsSinceEpoch(row['stored_at']! as int),
    );
  }

  @override
  Future<void> remove(String key) =>
      _db.delete(table, where: 'key = ?', whereArgs: <Object?>[key]);

  @override
  Future<void> clear() => _db.delete(table);
}
```

- [ ] **Step 4: Run the tests**

```bash
cd mobile && flutter test test/core/storage/cache_store_test.dart
```
Expected: `All tests passed!` (6 tests).

- [ ] **Step 5: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/storage/cache_store.dart mobile/test/core/storage/cache_store_test.dart
git commit -m "$(cat <<'EOF'
feat(mobile): add the sqflite read cache

Single key/JSON/timestamp table (ADR-034 D5). Read cache only: writes
always require the network. Presigned URLs are excluded by rule.

Tests drive it through sqflite_common_ffi — sqflite has no implementation
under `flutter test`.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 10: `ApiClient` — the only class that touches Dio

**Files:**
- Create: `mobile/lib/core/network/api_client.dart`
- Test: `mobile/test/core/network/api_client_test.dart`

**Interfaces:**
- Consumes: `unwrapData`, `unwrapPage`, `Parse<T>` (Task 5); the taxonomy (Task 4)
- Produces:
  - `class ApiClient(Dio dio)` with
    `Future<T> getOne<T>(String path, {Map<String, Object?>? query, CancelToken? cancelToken, required Parse<T> parse})`,
    `Future<Page<T>> getPage<T>(String path, {String? cursor, int? limit, Map<String, Object?>? query, CancelToken? cancelToken, required Parse<T> parse})`,
    `Future<T> post<T>(String path, {Object? body, CancelToken? cancelToken, required Parse<T> parse})`
  - `AppException toAppException(DioException e)`

> **Verified gotcha (V25):** `DioExceptionType` in dio 5.11 has **nine** members — the usual eight plus `transformTimeout`. An exhaustive switch without it is a compile error: `The type 'DioExceptionType' is not exhaustively matched ... doesn't match 'DioExceptionType.transformTimeout'`.
>
> **Verified gotcha (V26):** under `strict-*` + `flutter_lints` 6, `if (cursor != null) 'cursor': cursor` inside a collection literal now trips `use_null_aware_elements`. Dart 3.12's null-aware element syntax `'cursor': ?cursor` is the clean form.

- [ ] **Step 1: Write the failing test**

`mobile/test/core/network/api_client_test.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/interceptors/trace_interceptor.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a, {bool trace = false}) {
  final dio = Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
    ..httpClientAdapter = a;
  if (trace) dio.interceptors.add(TraceInterceptor());
  return ApiClient(dio);
}

void main() {
  test('getOne unwraps the envelope', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'id': 'u1', 'email': 'a@b.c'},
      }),
    ]);
    final got = await _client(a).getOne<String>(
      '/auth/me',
      parse: (j) => (j! as Map<String, Object?>)['email']! as String,
    );
    expect(got, 'a@b.c');
  });

  test('getPage handles the meta-less array of GET /me/clans', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <Object?>[
          <String, Object?>{'clan_id': 'c1'},
          <String, Object?>{'clan_id': 'c2'},
        ],
      }),
    ]);
    final page = await _client(a).getPage<String>(
      '/me/clans',
      parse: (j) => (j! as Map<String, Object?>)['clan_id']! as String,
    );
    expect(page.items, <String>['c1', 'c2']);
    expect(page.cursor, isNull);
    expect(page.hasMore, isFalse);
  });

  test('getPage forwards an opaque cursor verbatim', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': <Object?>[]}),
    ]);
    await _client(a).getPage<int>(
      '/persons',
      cursor: 'weird!!:{}',
      limit: 25,
      parse: (j) => j! as int,
    );
    expect(a.received.single.uri.queryParameters['cursor'], 'weird!!:{}');
    expect(a.received.single.uri.queryParameters['limit'], '25');
  });

  test('an error envelope becomes ApiException with code and detail', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(409, <String, Object?>{
        'error': <String, Object?>{
          'code': 'stale_write',
          'message': 'Người khác vừa sửa',
          'detail': <String, Object?>{'current_version': 4},
        },
      }),
    ]);
    await expectLater(
      _client(a).getOne<Object?>('/persons/1', parse: (j) => j),
      throwsA(
        isA<ApiException>()
            .having((e) => e.code, 'code', 'stale_write')
            .having((e) => e.status, 'status', 409)
            .having((e) => e.currentVersion, 'currentVersion', 4),
      ),
    );
  });

  test('a 403 error envelope keeps its code for policyActionFor', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(403, <String, Object?>{
        'error': <String, Object?>{
          'code': 'email_not_verified',
          'message': 'Email chưa xác thực',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await _client(a).getOne<Object?>('/persons', parse: (j) => j);
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(
        policyActionFor(e.code, status: e.status),
        PolicyAction.resendVerification,
      );
    }
  });

  test('a non-envelope error body is MalformedResponseException', () async {
    final a = SequenceAdapter(<Canned>[const Canned(500, 'gateway exploded')]);
    await expectLater(
      _client(a).getOne<Object?>('/persons', parse: (j) => j),
      throwsA(isA<MalformedResponseException>()),
    );
  });

  test('a 2xx body without data is MalformedResponseException', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'unexpected': 1}),
    ]);
    await expectLater(
      _client(a).getOne<Object?>('/persons', parse: (j) => j),
      throwsA(isA<MalformedResponseException>()),
    );
  });

  test('the trace id is lifted from the traceparent header', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(500, <String, Object?>{
        'error': <String, Object?>{
          'code': 'internal_error',
          'message': 'Lỗi hệ thống',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await _client(
        a,
        trace: true,
      ).getOne<Object?>('/persons', parse: (j) => j);
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.traceId, isNotNull);
      expect(RegExp(r'^[0-9a-f]{32}$').hasMatch(e.traceId!), isTrue);
    }
  });

  test('a cancellation is rethrown as DioException, not wrapped', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': null}),
    ]);
    final token = CancelToken()..cancel('gone');
    await expectLater(
      _client(
        a,
      ).getOne<Object?>('/persons', cancelToken: token, parse: (j) => j),
      throwsA(
        isA<DioException>().having(
          (e) => e.type,
          'type',
          DioExceptionType.cancel,
        ),
      ),
    );
  });

  test('toAppException maps timeouts and connection errors', () {
    final req = RequestOptions(path: '/x');
    expect(
      toAppException(
        DioException(
          requestOptions: req,
          type: DioExceptionType.receiveTimeout,
        ),
      ),
      isA<TimeoutException>(),
    );
    expect(
      toAppException(
        DioException(
          requestOptions: req,
          type: DioExceptionType.connectionError,
        ),
      ),
      isA<NetworkException>(),
    );
  });

  test('post unwraps the envelope', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'access_token': 'tok'},
      }),
    ]);
    final got = await _client(a).post<String>(
      '/auth/login',
      body: <String, Object?>{'email': 'a@b.c', 'password': 'x'},
      parse: (j) => (j! as Map<String, Object?>)['access_token']! as String,
    );
    expect(got, 'tok');
    expect(a.received.single.method, 'POST');
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/network/api_client_test.dart
```
Expected: FAIL — cannot resolve `api_client.dart`.

- [ ] **Step 3: Write the implementation**

`mobile/lib/core/network/api_client.dart`:

```dart
import 'package:dio/dio.dart' as dio;

import '../../domain/shared/page.dart';
import 'api_exception.dart';
import 'envelope.dart';

/// The only class that talks to Dio. Everything above it sees domain types and
/// AppException — never DioException, never `{"data": ...}`.
class ApiClient {
  ApiClient(this._dio);

  final dio.Dio _dio;

  Future<T> getOne<T>(
    String path, {
    Map<String, Object?>? query,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.get<Object?>(
      path,
      queryParameters: query,
      cancelToken: cancelToken,
    );
    return unwrapData<T>(res.data, parse);
  });

  Future<Page<T>> getPage<T>(
    String path, {
    String? cursor,
    int? limit,
    Map<String, Object?>? query,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.get<Object?>(
      path,
      queryParameters: <String, Object?>{
        ...?query,
        // Opaque: replayed verbatim, never constructed or parsed.
        // `?x` is Dart 3.12's null-aware element — the entry is omitted when
        // the value is null. `if (x != null)` trips use_null_aware_elements.
        'cursor': ?cursor,
        'limit': ?limit,
      },
      cancelToken: cancelToken,
    );
    return unwrapPage<T>(res.data, parse);
  });

  Future<T> post<T>(
    String path, {
    Object? body,
    dio.CancelToken? cancelToken,
    required Parse<T> parse,
  }) => _guard(() async {
    final res = await _dio.post<Object?>(
      path,
      data: body,
      cancelToken: cancelToken,
    );
    return unwrapData<T>(res.data, parse);
  });

  Future<T> _guard<T>(Future<T> Function() run) async {
    try {
      return await run();
    } on dio.DioException catch (e) {
      // A caller-initiated cancellation is rethrown unchanged.
      if (e.type == dio.DioExceptionType.cancel) rethrow;
      throw toAppException(e);
    }
  }
}

/// Maps a DioException onto the sealed client taxonomy.
AppException toAppException(dio.DioException e) {
  switch (e.type) {
    case dio.DioExceptionType.connectionTimeout:
    case dio.DioExceptionType.sendTimeout:
    case dio.DioExceptionType.receiveTimeout:
    // dio 5.11 added transformTimeout; the switch must be exhaustive.
    case dio.DioExceptionType.transformTimeout:
      return const TimeoutException();
    case dio.DioExceptionType.connectionError:
    case dio.DioExceptionType.unknown:
    case dio.DioExceptionType.badCertificate:
      return NetworkException(e.error ?? e);
    case dio.DioExceptionType.cancel:
      return NetworkException(e);
    case dio.DioExceptionType.badResponse:
      final res = e.response;
      final body = res?.data;
      if (body is Map<String, Object?> &&
          body['error'] is Map<String, Object?>) {
        final err = body['error']! as Map<String, Object?>;
        final code = err['code'];
        final message = err['message'];
        if (code is String && message is String) {
          return ApiException(
            code: code,
            message: message,
            status: res?.statusCode ?? 0,
            detail:
                (err['detail'] as Map<String, Object?>?) ??
                const <String, Object?>{},
            traceId: _traceIdOf(res),
          );
        }
      }
      return MalformedResponseException(body);
  }
}

/// The 32-hex trace-id half of the request's traceparent, surfaced to the user
/// so a report links to the exact backend log line.
String? _traceIdOf(dio.Response<Object?>? res) {
  final tp = res?.requestOptions.headers['traceparent'];
  if (tp is! String) return null;
  final parts = tp.split('-');
  return parts.length >= 2 ? parts[1] : null;
}
```

- [ ] **Step 4: Run the tests**

```bash
cd mobile && flutter test test/core/network/api_client_test.dart
```
Expected: `All tests passed!` (11 tests).

- [ ] **Step 5: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/network/api_client.dart mobile/test/core/network/api_client_test.dart
git commit -m "$(cat <<'EOF'
feat(mobile): add ApiClient, the only class that touches Dio

getOne/getPage/post unwrap the envelope and translate DioException into
the sealed AppException taxonomy. Cursors are forwarded verbatim.
Cancellations are rethrown unchanged. The trace id is lifted from the
outgoing traceparent so errors can cite it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 11: Bundled fonts and Arbor Heritage theme tokens

**Files:**
- Create: `mobile/assets/fonts/PlusJakartaSans.ttf`, `Manrope.ttf`, `OFL.txt`; `mobile/lib/core/theme/tokens.dart`, `mobile/lib/core/theme/app_theme.dart`; `mobile/test/support/load_app_fonts.dart`
- Modify: `mobile/pubspec.yaml` (fonts section)
- Test: `mobile/test/core/theme/theme_test.dart`

**Interfaces:**
- Produces: `class ArborTokens extends ThemeExtension<ArborTokens>` with `ArborTokens.light()`; `extension ArborContext on BuildContext { ArborTokens get tokens }`; `ThemeData buildAppTheme()`; `Future<void> loadAppFonts()`

> **Verified (V18/V22/V24):** the repo ships **no fonts** — `assets/` holds only `.gitkeep`. Upstream has **only variable** fonts (`static/` 404s). Declaring the same variable TTF twice with different `weight:` values works; the wght axis is applied (regular 247.3px vs bold 250.5px for the same string).
>
> **Verified (V19):** `flutter test` renders a **placeholder** font unless you load the real ones. Without `loadAppFonts()` the same string measured 480.0×32.0 at *both* weights. Any golden or layout assertion must call it in `setUpAll`.

- [ ] **Step 1: Fetch the fonts and their licence**

```bash
cd mobile && mkdir -p assets/fonts
curl -sL -o assets/fonts/PlusJakartaSans.ttf \
  "https://github.com/google/fonts/raw/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf"
curl -sL -o assets/fonts/Manrope.ttf \
  "https://github.com/google/fonts/raw/main/ofl/manrope/Manrope%5Bwght%5D.ttf"
curl -sL -o assets/fonts/OFL.txt \
  "https://github.com/google/fonts/raw/main/ofl/plusjakartasans/OFL.txt"
file assets/fonts/*.ttf
```
Expected: both report `TrueType Font data`. Sizes are roughly 176 KB and 165 KB. If either is a few hundred bytes you fetched an HTML error page — stop and re-fetch.

- [ ] **Step 2: Declare them in `pubspec.yaml`**

Add under the existing `flutter:` key, after `assets:`:

```yaml
  fonts:
    - family: PlusJakartaSans
      fonts:
        - asset: assets/fonts/PlusJakartaSans.ttf
          weight: 400
        - asset: assets/fonts/PlusJakartaSans.ttf
          weight: 700
    - family: Manrope
      fonts:
        - asset: assets/fonts/Manrope.ttf
          weight: 400
        - asset: assets/fonts/Manrope.ttf
          weight: 700
```

Also add `- assets/fonts/` to the `assets:` list.

- [ ] **Step 3: Write the font loader for tests**

`mobile/test/support/load_app_fonts.dart`:

```dart
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Widget tests render a weight-insensitive placeholder font unless the real
/// ones are registered. Call this in setUpAll for any golden or layout test.
Future<void> loadAppFonts() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  const families = <String, String>{
    'PlusJakartaSans': 'assets/fonts/PlusJakartaSans.ttf',
    'Manrope': 'assets/fonts/Manrope.ttf',
  };
  for (final entry in families.entries) {
    final loader = FontLoader(entry.key)
      ..addFont(
        File(entry.value).readAsBytes().then(
          (b) => ByteData.view(Uint8List.fromList(b).buffer),
        ),
      );
    await loader.load();
  }
}
```

- [ ] **Step 4: Write the failing test**

`mobile/test/core/theme/theme_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/core/theme/tokens.dart';

import '../../support/load_app_fonts.dart';

void main() {
  setUpAll(loadAppFonts);

  testWidgets('tokens honour the Arbor Heritage mandates', (tester) async {
    late ArborTokens t;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Builder(
          builder: (context) {
            t = context.tokens;
            return const SizedBox();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Never #000000.
    expect(t.onSurface, isNot(const Color(0xFF000000)));
    expect(t.onSurface, const Color(0xFF1D1B16));
    // 9999px for primary buttons, 2rem for nodes. Never sm or none.
    expect(t.radiusPill, 9999);
    expect(t.radiusNode, 32);
    // Glass: surface at 80% opacity with 20px backdrop blur.
    expect(t.glassOpacity, 0.8);
    expect(t.glassBlur, 20);
    // Ambient depth, not rigid drop shadows.
    expect(t.ambientBlur, 32);
    expect(t.ambientOpacity, 0.06);
  });

  testWidgets('the no-line rule: dividers have no thickness', (tester) async {
    final theme = buildAppTheme();
    expect(theme.dividerTheme.thickness, 0);
    expect(theme.cardTheme.elevation, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('body text is Manrope, headings Plus Jakarta Sans',
      (tester) async {
    final theme = buildAppTheme();
    expect(theme.textTheme.headlineLarge?.fontFamily, 'PlusJakartaSans');
    expect(theme.textTheme.titleLarge?.fontFamily, 'PlusJakartaSans');
    // The family default covers body/labels.
    expect(theme.textTheme.bodyMedium?.fontFamily ?? 'Manrope', 'Manrope');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the bundled variable font applies its weight axis',
      (tester) async {
    Future<Size> measure(FontWeight w) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: Text(
              'Gia phả dòng họ',
              style: TextStyle(
                fontFamily: 'PlusJakartaSans',
                fontSize: 32,
                fontWeight: w,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getSize(find.byType(Text));
    }

    final regular = await measure(FontWeight.w400);
    final bold = await measure(FontWeight.w700);
    // The placeholder test font is weight-insensitive; the real one is not.
    expect(bold.width, isNot(regular.width));
  });
}
```

- [ ] **Step 5: Run to confirm it fails**

```bash
cd mobile && flutter test test/core/theme/theme_test.dart
```
Expected: FAIL — cannot resolve `tokens.dart`.

- [ ] **Step 6: Write `tokens.dart`**

```dart
import 'package:flutter/material.dart';

/// Arbor Heritage design tokens. Violating a mandate should take effort, so
/// every colour, radius, spacing and elevation lives here and nowhere else.
@immutable
class ArborTokens extends ThemeExtension<ArborTokens> {
  const ArborTokens({
    required this.surface,
    required this.surfaceContainerLow,
    required this.onSurface,
    required this.primary,
    required this.onPrimary,
    required this.error,
    required this.outlineVariant,
    required this.radiusPill,
    required this.radiusNode,
    required this.spaceXs,
    required this.spaceSm,
    required this.spaceMd,
    required this.spaceLg,
    required this.ambientBlur,
    required this.ambientOpacity,
    required this.glassOpacity,
    required this.glassBlur,
  });

  /// Primary text is `on_surface` #1d1b16 — never #000000.
  factory ArborTokens.light() => const ArborTokens(
    surface: Color(0xFFFDFCF7),
    surfaceContainerLow: Color(0xFFF5F1E6),
    onSurface: Color(0xFF1D1B16),
    primary: Color(0xFF7A5C2E),
    onPrimary: Color(0xFFFFFFFF),
    error: Color(0xFF8C1D18),
    outlineVariant: Color(0xFFCFC7B4),
    // 9999px for primary buttons, 2rem (32px) for nodes. Never sm or none.
    radiusPill: 9999,
    radiusNode: 32,
    spaceXs: 4,
    spaceSm: 8,
    spaceMd: 16,
    spaceLg: 24,
    // Ambient depth, not rigid drop shadows.
    ambientBlur: 32,
    ambientOpacity: 0.06,
    // Glass: surface at 80% opacity with 20px backdrop blur.
    glassOpacity: 0.8,
    glassBlur: 20,
  );

  final Color surface;
  final Color surfaceContainerLow;
  final Color onSurface;
  final Color primary;
  final Color onPrimary;
  final Color error;
  final Color outlineVariant;
  final double radiusPill;
  final double radiusNode;
  final double spaceXs;
  final double spaceSm;
  final double spaceMd;
  final double spaceLg;
  final double ambientBlur;
  final double ambientOpacity;
  final double glassOpacity;
  final double glassBlur;

  @override
  ArborTokens copyWith({Color? surface, Color? onSurface, Color? primary}) =>
      ArborTokens(
        surface: surface ?? this.surface,
        surfaceContainerLow: surfaceContainerLow,
        onSurface: onSurface ?? this.onSurface,
        primary: primary ?? this.primary,
        onPrimary: onPrimary,
        error: error,
        outlineVariant: outlineVariant,
        radiusPill: radiusPill,
        radiusNode: radiusNode,
        spaceXs: spaceXs,
        spaceSm: spaceSm,
        spaceMd: spaceMd,
        spaceLg: spaceLg,
        ambientBlur: ambientBlur,
        ambientOpacity: ambientOpacity,
        glassOpacity: glassOpacity,
        glassBlur: glassBlur,
      );

  @override
  ArborTokens lerp(ThemeExtension<ArborTokens>? other, double t) {
    if (other is! ArborTokens) return this;
    return ArborTokens(
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceContainerLow: Color.lerp(
        surfaceContainerLow,
        other.surfaceContainerLow,
        t,
      )!,
      onSurface: Color.lerp(onSurface, other.onSurface, t)!,
      primary: Color.lerp(primary, other.primary, t)!,
      onPrimary: Color.lerp(onPrimary, other.onPrimary, t)!,
      error: Color.lerp(error, other.error, t)!,
      outlineVariant: Color.lerp(outlineVariant, other.outlineVariant, t)!,
      radiusPill: radiusPill,
      radiusNode: radiusNode,
      spaceXs: spaceXs,
      spaceSm: spaceSm,
      spaceMd: spaceMd,
      spaceLg: spaceLg,
      ambientBlur: ambientBlur,
      ambientOpacity: ambientOpacity,
      glassOpacity: glassOpacity,
      glassBlur: glassBlur,
    );
  }
}

extension ArborContext on BuildContext {
  ArborTokens get tokens => Theme.of(this).extension<ArborTokens>()!;
}
```

- [ ] **Step 7: Write `app_theme.dart`**

```dart
import 'package:flutter/material.dart';

import 'tokens.dart';

/// ThemeData is built FROM the tokens — never the other way round.
ThemeData buildAppTheme() {
  final t = ArborTokens.light();
  final scheme = ColorScheme.fromSeed(
    seedColor: t.primary,
    surface: t.surface,
    onSurface: t.onSurface,
    error: t.error,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: t.surface,
    extensions: <ThemeExtension<dynamic>>[t],
    // Bundled, never fetched at runtime; never falls back to the system font.
    fontFamily: 'Manrope',
    textTheme: const TextTheme(
      displayLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
      displayMedium: TextStyle(fontFamily: 'PlusJakartaSans'),
      displaySmall: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineMedium: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineSmall: TextStyle(fontFamily: 'PlusJakartaSans'),
      titleLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
    ),
    // The no-line rule: boundaries come from background shifts, not borders.
    dividerTheme: const DividerThemeData(thickness: 0, space: 0),
    cardTheme: CardThemeData(
      elevation: 0,
      color: t.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(t.radiusNode),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(t.radiusPill),
        ),
        padding: EdgeInsets.symmetric(
          horizontal: t.spaceLg,
          vertical: t.spaceMd,
        ),
      ),
    ),
  );
}
```

- [ ] **Step 8: Run the tests**

```bash
cd mobile && flutter pub get && flutter test test/core/theme/theme_test.dart
```
Expected: `All tests passed!` (4 tests). If the weight-axis test fails with equal widths, `loadAppFonts()` did not run — check the `setUpAll`.

- [ ] **Step 9: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/assets/fonts mobile/pubspec.yaml mobile/lib/core/theme mobile/test
git commit -m "$(cat <<'EOF'
feat(mobile): bundle the mandated fonts and encode Arbor Heritage tokens

Plus Jakarta Sans and Manrope ship as assets (OFL included) rather than
being fetched at runtime by google_fonts, which fell back to the system
font offline — a direct mandate violation (ADR-034 D4). Only variable
fonts exist upstream; the wght axis is applied via duplicate weight
declarations.

Design tokens are a ThemeExtension and ThemeData is built from them, so
no widget hardcodes a colour or radius.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 12: Localisation — `vi` default, `en` alongside

**Files:**
- Modify: `mobile/lib/core/l10n/app_vi.arb`, `app_en.arb` (carried forward in Task 1)
- Create: `mobile/lib/core/l10n/generated/**` (generated, committed)
- Test: `mobile/test/core/l10n/l10n_test.dart`

**Interfaces:**
- Produces: `AppLocalizations` with `AppLocalizations.of(context)`, `AppLocalizations.localizationsDelegates`, `AppLocalizations.supportedLocales`, and the M0 keys below.

> The carried-forward ARB pair already has 55 keys from the old scaffold. Keep them — most are reusable — and **add** the M0 keys. `vi` is the template, so every key must exist in `app_vi.arb`; missing `en` values fall back to `vi`.
>
> Nothing may assume the locale set is exactly two: `zh` and `fr` are accepted by the backend and get added to `supportedLocales` automatically when their ARB files appear.

- [ ] **Step 1: Add the M0 keys to `app_vi.arb`**

Merge these into the existing object (do not delete the 55 carried-forward keys):

```jsonc
  "myClansTitle": "Dòng họ của tôi",
  "clanPickerTitle": "Chọn dòng họ",
  "clanCount": "{count, plural, =0{Chưa có dòng họ} =1{1 dòng họ} other{{count} dòng họ}}",
  "@clanCount": {
    "placeholders": { "count": { "type": "int" } }
  },
  "staleDataBanner": "Dữ liệu ngày {date}",
  "@staleDataBanner": {
    "placeholders": { "date": { "type": "String" } }
  },
  "signOutAction": "Đăng xuất",
  "retryAction": "Thử lại",
  "errorOffline": "Không có kết nối mạng",
  "errorTimeout": "Máy chủ phản hồi quá chậm",
  "errorUnexpected": "Đã xảy ra lỗi không mong muốn",
  "errorTraceId": "Mã lỗi: {traceId}",
  "@errorTraceId": {
    "placeholders": { "traceId": { "type": "String" } }
  },
  "pendingApprovalTitle": "Đang chờ duyệt",
  "pendingApprovalBody": "Yêu cầu tham gia của bạn đang chờ quản trị viên dòng họ duyệt.",
  "verifyEmailTitle": "Xác thực email",
  "verifyEmailBody": "Vui lòng mở email và bấm liên kết xác thực.",
  "resendVerificationAction": "Gửi lại email xác thực",
  "onboardingTitle": "Tham gia dòng họ",
  "accountBlockedTitle": "Tài khoản đã bị khoá",
  "clanSuspendedTitle": "Dòng họ đã bị tạm ngưng"
```

- [ ] **Step 2: Add the same keys to `app_en.arb`**

Placeholder metadata (`@key`) lives only in the template, so `en` carries values only:

```jsonc
  "myClansTitle": "My clans",
  "clanPickerTitle": "Choose a clan",
  "clanCount": "{count, plural, =0{No clans} =1{1 clan} other{{count} clans}}",
  "staleDataBanner": "Data from {date}",
  "signOutAction": "Sign out",
  "retryAction": "Retry",
  "errorOffline": "No network connection",
  "errorTimeout": "The server took too long to respond",
  "errorUnexpected": "Something went wrong",
  "errorTraceId": "Error id: {traceId}",
  "pendingApprovalTitle": "Awaiting approval",
  "pendingApprovalBody": "Your join request is waiting for a clan admin to approve it.",
  "verifyEmailTitle": "Verify your email",
  "verifyEmailBody": "Open your email and tap the verification link.",
  "resendVerificationAction": "Resend verification email",
  "onboardingTitle": "Join a clan",
  "accountBlockedTitle": "Account blocked",
  "clanSuspendedTitle": "Clan suspended"
```

- [ ] **Step 3: Generate**

```bash
cd mobile && flutter gen-l10n
ls lib/core/l10n/generated
```
Expected: `app_localizations.dart`, `app_localizations_en.dart`, `app_localizations_vi.dart`. If you see `The argument "synthetic-package" no longer has any effect`, remove that key from `l10n.yaml`.

- [ ] **Step 4: Write the test**

`mobile/test/core/l10n/l10n_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';

Widget _host(Locale locale, void Function(AppLocalizations) probe) =>
    MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) {
          probe(AppLocalizations.of(context));
          return const SizedBox();
        },
      ),
    );

void main() {
  testWidgets('vi and en are both supported, vi first', (tester) async {
    expect(
      AppLocalizations.supportedLocales.map((l) => l.languageCode),
      containsAll(<String>['vi', 'en']),
    );
    expect(AppLocalizations.supportedLocales.first.languageCode, 'vi');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Vietnamese strings', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('vi'), (x) => l = x));
    await tester.pumpAndSettle();

    expect(l.myClansTitle, 'Dòng họ của tôi');
    expect(l.clanCount(0), 'Chưa có dòng họ');
    expect(l.clanCount(1), '1 dòng họ');
    expect(l.clanCount(5), '5 dòng họ');
    expect(l.staleDataBanner('01/08/2026'), 'Dữ liệu ngày 01/08/2026');
  });

  testWidgets('English strings', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('en'), (x) => l = x));
    await tester.pumpAndSettle();

    expect(l.myClansTitle, 'My clans');
    expect(l.clanCount(0), 'No clans');
    expect(l.clanCount(2), '2 clans');
  });

  testWidgets('an unsupported locale falls back to vi', (tester) async {
    late AppLocalizations l;
    await tester.pumpWidget(_host(const Locale('zh'), (x) => l = x));
    await tester.pumpAndSettle();
    expect(l.myClansTitle, 'Dòng họ của tôi');
  });
}
```

> The fallback test depends on `MaterialApp` resolving an unsupported locale to the first supported one. Confirm the assertion matches observed behaviour when you run it; if Flutter resolves differently, assert what it actually does rather than forcing the expectation.

- [ ] **Step 5: Run**

```bash
cd mobile && flutter test test/core/l10n/l10n_test.dart
```
Expected: `All tests passed!` (4 tests).

- [ ] **Step 6: Full gate and commit**

Generated localisations are committed like all other generated code.

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && flutter analyze && flutter test
git add mobile/lib/core/l10n mobile/test/core/l10n mobile/l10n.yaml
git commit -m "$(cat <<'EOF'
feat(mobile): ship vi and en localisations with vi as default

app_vi.arb is the gen-l10n template because vi is both default and
fallback. Nothing assumes the locale set is exactly two — zh and fr join
supportedLocales as soon as their ARB files exist.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 13: Auth slice — domain, DTOs and repository

**Files:**
- Create: `mobile/lib/domain/auth/user_profile.dart`, `mobile/lib/domain/clan/clan_membership.dart`, `mobile/lib/features/auth/data/auth_dto.dart`, `mobile/lib/features/auth/data/auth_repository.dart`
- Test: `mobile/test/features/auth/auth_repository_test.dart`

**Interfaces:**
- Produces:
  - `enum ClanRole { admin, editor, viewer, unknown }` with `ClanRole.fromWire(Object?)`, `bool get canEdit`, `bool get canAdminister`
  - `ClanMembership({ClanId clanId, String clanName, String clanSlug, ClanRole role, DateTime? joinedAt})`
  - `UserProfile({UserId id, String email, String? fullName, ClanId? clanId, String? clanName, ClanRole? role, bool isApproved, bool hasPendingMembership, PersonId? personId})` with `bool get needsPendingScreen`, `bool get needsOnboarding`
  - `UserProfile userProfileFromJson(Object?)`, `LoginResult loginResultFromJson(Object?)`
  - `class LoginResult({String accessToken, String refreshToken, int expiresIn, UserProfile user})`
  - `class AuthRepository(ApiClient api)` — `login`, `me`, `resendVerification`, `logout`

> `preferred_locale` is deliberately **not** mapped: it always returns `"vi"` regardless of what was saved (spec R3). The app owns locale in `PrefsStore`.
>
> `role` is non-null only when the membership is approved — a pending member gets `role: null`, which is why `UserProfile.role` is nullable while `ClanMembership.role` is not.

- [ ] **Step 1: Write the failing test**

`mobile/test/features/auth/auth_repository_test.dart`:

```dart
// Fixtures copied verbatim from docs/contracts/rest-auth-api.md.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/domain/clan/clan_membership.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';

import '../../support/sequence_adapter.dart';

ApiClient _client(SequenceAdapter a) => ApiClient(
  Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))..httpClientAdapter = a,
);

const _login = <String, Object?>{
  'data': <String, Object?>{
    'access_token': 'eyJhbGciOi...',
    'refresh_token': 'v1.Mr7...',
    'expires_in': 3600,
    'user': <String, Object?>{
      'id': '99999999-9999-9999-9999-999999999999',
      'email': 'minh@example.com',
      'full_name': 'Nguyễn Văn Minh',
      'clan_id': '11111111-1111-1111-1111-111111111111',
      'clan_name': 'Họ Nguyễn Phúc',
      'role': 'admin',
      'is_approved': true,
      'has_pending_membership': false,
      'person_id': '33333333-3333-3333-3333-333333333333',
      'preferred_locale': 'vi',
    },
  },
};

void main() {
  test('POST /login maps tokens and the nested user', () async {
    final a = SequenceAdapter(<Canned>[const Canned(200, _login)]);
    final res = await AuthRepository(
      _client(a),
    ).login(email: 'minh@example.com', password: 'secret');

    expect(res.accessToken, 'eyJhbGciOi...');
    expect(res.refreshToken, 'v1.Mr7...');
    expect(res.expiresIn, 3600);
    expect(res.user.email, 'minh@example.com');
    expect(res.user.role, ClanRole.admin);
    expect(res.user.personId!.value, '33333333-3333-3333-3333-333333333333');
  });

  test('GET /auth/me carries the real has_pending_membership', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{
          'id': 'u1',
          'email': 'pending@example.com',
          'full_name': 'Chờ Duyệt',
          'clan_id': 'c1',
          'clan_name': 'Họ Lê',
          'role': null,
          'is_approved': false,
          'has_pending_membership': true,
          'person_id': null,
          'preferred_locale': 'vi',
        },
      }),
    ]);
    final me = await AuthRepository(_client(a)).me();

    expect(me.isApproved, isFalse);
    expect(me.hasPendingMembership, isTrue);
    expect(me.role, isNull, reason: 'role is null until approved');
    expect(me.needsPendingScreen, isTrue);
    expect(me.needsOnboarding, isFalse);
  });

  test('a user attached to no clan needs onboarding', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{
          'id': 'u2',
          'email': 'new@example.com',
          'full_name': null,
          'clan_id': null,
          'clan_name': null,
          'role': null,
          'is_approved': false,
          'has_pending_membership': false,
          'person_id': null,
          'preferred_locale': 'vi',
        },
      }),
    ]);
    final me = await AuthRepository(_client(a)).me();
    expect(me.needsOnboarding, isTrue);
    expect(me.needsPendingScreen, isFalse);
  });

  test('login with an unverified email surfaces email_not_verified', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(403, <String, Object?>{
        'error': <String, Object?>{
          'code': 'email_not_verified',
          'message': 'Email chưa được xác thực',
          'detail': <String, Object?>{},
        },
      }),
    ]);
    try {
      await AuthRepository(_client(a)).login(email: 'a@b.c', password: 'x');
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.code, 'email_not_verified');
      expect(e.status, 403);
      expect(
        policyActionFor(e.code, status: e.status),
        PolicyAction.resendVerification,
      );
    }
  });

  test('rate limiting surfaces retry_after', () async {
    final a = SequenceAdapter(<Canned>[
      const Canned(429, <String, Object?>{
        'error': <String, Object?>{
          'code': 'rate_limited',
          'message': 'Quá nhiều yêu cầu',
          'detail': <String, Object?>{'retry_after': 42},
        },
      }),
    ]);
    try {
      await AuthRepository(_client(a)).login(email: 'a@b.c', password: 'x');
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.retryAfter, 42);
      expect(policyActionFor(e.code), PolicyAction.backOff);
    }
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/features/auth/auth_repository_test.dart
```
Expected: FAIL — the auth files do not exist.

- [ ] **Step 3: Write `domain/clan/clan_membership.dart`**

```dart
import 'package:freezed_annotation/freezed_annotation.dart';

import '../shared/ids.dart';

part 'clan_membership.freezed.dart';

enum ClanRole {
  admin,
  editor,
  viewer,
  unknown;

  /// Never throws: an unrecognised role degrades to [unknown] so a new server
  /// role cannot crash a shipped client. `invalid_role_assignment` is the
  /// backend's own guard for corrupted values.
  static ClanRole fromWire(Object? raw) {
    for (final r in ClanRole.values) {
      if (r.name == raw) return r;
    }
    return ClanRole.unknown;
  }

  bool get canEdit => this == admin || this == editor;
  bool get canAdminister => this == admin;
}

@freezed
abstract class ClanMembership with _$ClanMembership {
  const factory ClanMembership({
    required ClanId clanId,
    required String clanName,
    required String clanSlug,
    required ClanRole role,
    required DateTime? joinedAt,
  }) = _ClanMembership;

  const ClanMembership._();
}
```

- [ ] **Step 4: Write `domain/auth/user_profile.dart`**

```dart
import 'package:freezed_annotation/freezed_annotation.dart';

import '../clan/clan_membership.dart';
import '../shared/ids.dart';

part 'user_profile.freezed.dart';

@freezed
abstract class UserProfile with _$UserProfile {
  const factory UserProfile({
    required UserId id,
    required String email,
    required String? fullName,
    required ClanId? clanId,
    required String? clanName,
    // Non-null only when the membership is approved.
    required ClanRole? role,
    required bool isApproved,
    required bool hasPendingMembership,
    required PersonId? personId,
  }) = _UserProfile;

  const UserProfile._();

  /// Routing rule from frontend-integration-guide.md §5.
  bool get needsPendingScreen => !isApproved && hasPendingMembership;

  /// Neither approved nor pending, attached to no clan → onboarding.
  bool get needsOnboarding =>
      !isApproved && !hasPendingMembership && clanId == null;
}
```

- [ ] **Step 5: Write `features/auth/data/auth_dto.dart`**

```dart
import '../../../domain/auth/user_profile.dart';
import '../../../domain/clan/clan_membership.dart';
import '../../../domain/shared/ids.dart';

/// The only place that knows the backend's wire shape for auth, so a new
/// backend field changes exactly one file.
///
/// `preferred_locale` is deliberately not mapped: it always returns "vi"
/// regardless of what was saved (spec R3). The app owns locale in PrefsStore.
UserProfile userProfileFromJson(Object? json) {
  final m = json! as Map<String, Object?>;
  final clanId = m['clan_id'];
  final personId = m['person_id'];
  return UserProfile(
    id: UserId(m['id']! as String),
    email: m['email']! as String,
    fullName: m['full_name'] as String?,
    clanId: clanId is String ? ClanId(clanId) : null,
    clanName: m['clan_name'] as String?,
    role: m['role'] == null ? null : ClanRole.fromWire(m['role']),
    isApproved: m['is_approved'] as bool? ?? false,
    hasPendingMembership: m['has_pending_membership'] as bool? ?? false,
    personId: personId is String ? PersonId(personId) : null,
  );
}

class LoginResult {
  const LoginResult({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final int expiresIn;

  /// `has_pending_membership` HERE IS ALWAYS FALSE — the login handler never
  /// computes it. Call GET /auth/me and route on that value instead.
  final UserProfile user;
}

LoginResult loginResultFromJson(Object? json) {
  final m = json! as Map<String, Object?>;
  return LoginResult(
    accessToken: m['access_token']! as String,
    refreshToken: m['refresh_token']! as String,
    expiresIn: m['expires_in'] as int? ?? 3600,
    user: userProfileFromJson(m['user']),
  );
}
```

- [ ] **Step 6: Write `features/auth/data/auth_repository.dart`**

```dart
import '../../../core/network/api_client.dart';
import '../../../domain/auth/user_profile.dart';
import 'auth_dto.dart';

class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  Future<LoginResult> login({
    required String email,
    required String password,
  }) => _api.post<LoginResult>(
    '/auth/login',
    body: <String, Object?>{'email': email, 'password': password},
    parse: loginResultFromJson,
  );

  /// Joined on approved memberships only, and with a real
  /// has_pending_membership — unlike the login response.
  Future<UserProfile> me() =>
      _api.getOne<UserProfile>('/auth/me', parse: userProfileFromJson);

  /// Always 200 with the same message (non-enumerating).
  Future<String> resendVerification(String email) => _api.post<String>(
    '/auth/resend-verification',
    body: <String, Object?>{'email': email},
    parse: (j) => (j! as Map<String, Object?>)['message']! as String,
  );

  /// Best-effort server-side revoke. The access token stays valid until it
  /// expires, so clear all client state regardless.
  Future<void> logout() => _api.post<Object?>('/auth/logout', parse: (j) => j);
}
```

- [ ] **Step 7: Generate and run**

```bash
cd mobile && dart run build_runner build \
  && flutter test test/features/auth/auth_repository_test.dart
```
Expected: `All tests passed!` (5 tests).

- [ ] **Step 8: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && dart run build_runner build && git diff --exit-code \
  && flutter analyze && flutter test
git add mobile/lib/domain mobile/lib/features/auth mobile/test/features/auth
git commit -m "$(cat <<'EOF'
feat(mobile): add the auth slice (UserProfile, DTOs, repository)

Fixtures are copied verbatim from docs/contracts/rest-auth-api.md.
preferred_locale is deliberately unmapped (always "vi", spec R3), and
role stays nullable because it is non-null only once approved. Unknown
roles degrade rather than throwing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Task 14: Session controller — login → `GET /auth/me`

**Files:**
- Create: `mobile/lib/features/auth/application/session_controller.dart`, `mobile/lib/features/auth/auth.dart`
- Test: `mobile/test/features/auth/session_controller_test.dart`

**Interfaces:**
- Consumes: `AuthRepository` (Task 13)
- Produces:
  - `final authRepositoryProvider = Provider<AuthRepository>(...)` (overridden at bootstrap)
  - `@Riverpod(keepAlive: true) class SessionController extends _$SessionController` → `Future<UserProfile?> build()`, `Future<void> signIn({required String email, required String password})`, `Future<void> signOut()`
  - generated `sessionControllerProvider`
  - `features/auth/auth.dart` — the slice's public surface, the only file other slices may import

> Signed-out is a **state**, not an error — hence `UserProfile?` rather than throwing. `keepAlive` because the session must outlive any one screen.

- [ ] **Step 1: Write the failing test**

`mobile/test/features/auth/session_controller_test.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/domain/auth/user_profile.dart';
import 'package:family_roots_mobile/features/auth/application/session_controller.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';

import '../../support/sequence_adapter.dart';

AuthRepository _repo(List<Canned> canned) => AuthRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = SequenceAdapter(canned),
  ),
);

const _loginOk = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'access_token': 'a',
    'refresh_token': 'r',
    'expires_in': 3600,
    'user': <String, Object?>{
      'id': 'u1',
      'email': 'a@b.c',
      'full_name': 'A',
      'clan_id': 'c1',
      'clan_name': 'Họ A',
      'role': 'admin',
      'is_approved': true,
      'has_pending_membership': false,
      'person_id': null,
      'preferred_locale': 'vi',
    },
  },
});

const _meApproved = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'a@b.c',
    'full_name': 'A',
    'clan_id': 'c1',
    'clan_name': 'Họ A',
    'role': 'admin',
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

void main() {
  test('starts signed out', () async {
    final c = ProviderContainer(
      overrides: [authRepositoryProvider.overrideWithValue(_repo(<Canned>[]))],
    );
    addTearDown(c.dispose);
    expect(await c.read(sessionControllerProvider.future), isNull);
  });

  test('signIn logs in then reads GET /auth/me', () async {
    final c = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          _repo(<Canned>[_loginOk, _meApproved]),
        ),
      ],
    );
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');

    final profile = c.read(sessionControllerProvider).requireValue;
    expect(profile, isA<UserProfile>());
    expect(profile!.email, 'a@b.c');
    expect(profile.isApproved, isTrue);
  });

  test('a failed login lands in AsyncError carrying the ApiException', () async {
    final c = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          _repo(<Canned>[
            const Canned(401, <String, Object?>{
              'error': <String, Object?>{
                'code': 'auth.invalid_credentials',
                'message': 'Sai email hoặc mật khẩu',
                'detail': <String, Object?>{},
              },
            }),
          ]),
        ),
      ],
    );
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'wrong');

    final state = c.read(sessionControllerProvider);
    expect(state.hasError, isTrue);
    expect(state.error, isA<ApiException>());
    expect((state.error! as ApiException).code, 'auth.invalid_credentials');
  });

  test('signOut clears the profile even if logout fails', () async {
    final c = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          _repo(<Canned>[
            _loginOk,
            _meApproved,
            const Canned(503, <String, Object?>{
              'error': <String, Object?>{
                'code': 'auth_provider_unavailable',
                'message': 'Tạm thời gián đoạn',
                'detail': <String, Object?>{},
              },
            }),
          ]),
        ),
      ],
    );
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');
    expect(c.read(sessionControllerProvider).requireValue, isNotNull);

    await c.read(sessionControllerProvider.notifier).signOut();
    expect(c.read(sessionControllerProvider).requireValue, isNull);
  });
}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd mobile && flutter test test/features/auth/session_controller_test.dart
```
Expected: FAIL — `session_controller.dart` does not exist.

- [ ] **Step 3: Write the controller**

`mobile/lib/features/auth/application/session_controller.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../domain/auth/user_profile.dart';
import '../data/auth_repository.dart';

part 'session_controller.g.dart';

/// Infrastructure binding — overridden in ProviderScope at bootstrap.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.
@Riverpod(keepAlive: true)
class SessionController extends _$SessionController {
  @override
  Future<UserProfile?> build() async => null;

  /// login → GET /auth/me, because the login response's
  /// has_pending_membership is always false (documented backend gap).
  Future<void> signIn({required String email, required String password}) async {
    state = const AsyncValue<UserProfile?>.loading();
    state = await AsyncValue.guard<UserProfile?>(() async {
      final repo = ref.read(authRepositoryProvider);
      await repo.login(email: email, password: password);
      return repo.me();
    });
  }

  Future<void> signOut() async {
    final repo = ref.read(authRepositoryProvider);
    try {
      await repo.logout();
    } on Object {
      // Logout is best-effort server-side; clear local state regardless.
    }
    state = const AsyncValue<UserProfile?>.data(null);
  }
}
```

- [ ] **Step 4: Write the slice public surface**

`mobile/lib/features/auth/auth.dart` — the ONLY file another slice may import:

```dart
/// Public surface of the auth slice. Other slices import this and nothing
/// deeper; the import-boundary test enforces it.
export 'application/session_controller.dart'
    show SessionController, sessionControllerProvider, authRepositoryProvider;
export 'data/auth_repository.dart' show AuthRepository;
```

- [ ] **Step 5: Generate and run**

```bash
cd mobile && dart run build_runner build \
  && flutter test test/features/auth/session_controller_test.dart
```
Expected: `All tests passed!` (4 tests).

- [ ] **Step 6: Full gate and commit**

```bash
cd mobile && dart format --set-exit-if-changed lib test \
  && dart run build_runner build && git diff --exit-code \
  && flutter analyze && flutter test
git add mobile/lib/features/auth mobile/test/features/auth
git commit -m "$(cat <<'EOF'
feat(mobile): add SessionController (login -> GET /auth/me)

Login alone is not enough: the login response's has_pending_membership is
always false, so the controller follows every login with GET /auth/me and
routes on that. Signed-out is modelled as data(null), not an error.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---
