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
extension type const ClanId(String value) {
  @override
  String toString() => value;
}

extension type const PersonId(String value) {
  @override
  String toString() => value;
}

extension type const UserId(String value) {
  @override
  String toString() => value;
}
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
