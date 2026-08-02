# Mobile Rebuild — Architecture Design

**Status:** approved 2026-08-02
**Sub-project:** D (mobile), brought forward ahead of B
**Supersedes:** the scaffold under `mobile/` created 2026-03-07

---

## 1. Context

### 1.1 What exists today

`mobile/` holds 51 Dart files produced by the original monorepo scaffold. It is a
UI mock-up, not an application:

- `lib/core/network/api_client.dart` and `lib/core/network/auth_interceptor.dart`
  are `// TODO: implement in Prompt 2` stubs. **The app makes no HTTP call to the
  backend at all.**
- `core/di/injection.dart` binds every repository to `lib/domain/mocks/`. Every
  screen renders fabricated data.
- Firebase, Sentry and Hive initialisation in `main.dart` are TODO comments.
- Two directories both called "domain" coexist: `lib/domain/` (ports + mocks) and
  `lib/features/<f>/domain/` (entities). `MemberModel.fromJson` lives in the
  supposedly-pure `lib/domain/entities/`.
- Five hardcoded `lh3.googleusercontent.com/aida-public/…` mock-up image URLs are
  shipped inside production screens.
- `test/widget/home_page_test.dart` asserted the string `"No upcoming events"`,
  which exists in no locale and in no widget. Mobile CI had never executed a
  single test until 2026-08-02, so nobody found out.

The scaffold is being deleted rather than refactored because there is almost no
logic to preserve: no transport, no real repositories, no domain rules.

**Kept from the old tree:** the `.arb` translation files (`vi`, `en`), the Arbor
Heritage design mandates recorded in `mobile/CLAUDE.md`, `l10n.yaml`, and
`assets/`. Everything else is deleted.

### 1.2 What the backend already guarantees

The backend is mature and its contracts are frozen and documented. Every
constraint below is load-bearing for this design (sources in `docs/contracts/`
and `docs/architecture/`):

| Contract | Rule |
|---|---|
| Envelope (ADR-010) | Every 2xx body is `{"data": …}`; cursor lists add `meta: {cursor, has_more, limit}`. `GET /health`, `GET /exports/clan` and `GET /internal/metrics` are the only exemptions. |
| Cursors (ADR-010) | **Opaque.** Never parsed, constructed or repaired by a client. A bad cursor returns `400 invalid_cursor`; the client drops it and refetches page one. |
| `HistoricalDate` (ADR-011) | Every genealogical date is `{date, precision, display, lunar}`. Render `date` when `precision == "exact"`, else `display`, falling back to `date`. |
| Headers | `Authorization: Bearer …`, `Accept-Language`, and on clan-scoped routes `X-Current-Clan-Id`. Eight distinct failure modes, tabulated in `frontend-integration-guide.md` §1.2. |
| Errors | `{"error": {code, message, detail}}`. `code` is stable, `message` is already localised server-side. Switch on `code`, display `message`. |
| Optimistic concurrency (ADR-017) | `PATCH` on persons, marriages and parent-child requires `expected_version`; a mismatch is `409 stale_write` with `detail.current_version`. |
| đời (ADR-027) | `generation` is computed by a single backend authority. `null` means "not connected to the founder". Clients must never derive it. |
| Founder (ADR-026) | `GET /tree` without a designated thủy tổ returns `404 clan_founder_not_found`. This is an onboarding state, not an error. |
| RBAC | Platform `super_admin`; clan `admin` > `editor` > `viewer`. Permission matrix in `docs/architecture/rbac.md`. |
| Locales | `vi` \| `en` \| `zh` \| `fr` are accepted on `Accept-Language`; default and fallback `vi`. |
| Presigned URLs | TTL 3600s. Never persisted to any local store. |

### 1.3 Constraints from the audience

FamilyRoots is used by whole clans across every age group, frequently on older
Android phones and weak rural networks. Three architectural consequences, not
polish items:

1. Fonts must be bundled, never fetched at runtime.
2. Every layout must survive a 200% text scale.
3. Data already viewed must remain viewable without a network.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | **Riverpod 3 (`flutter_riverpod` 3.4, `riverpod_generator` 4.0) for both state and dependency injection** | Rejected `get_it` + `injectable` alongside it: two DI containers in one app is pure debt, and Riverpod already is one — the old scaffold carried both. Rejected BLoC: this is an overwhelmingly server-state application (paginated lists, details, mutate-then-invalidate), and `AsyncNotifier` + `ref.invalidate` maps almost one-to-one onto the TanStack Query model the web client uses, giving one mental model across both clients for materially less code. |
| D2 | **Plain Dio + hand-written repositories; DTOs via `json_serializable`** | Rejected **Retrofit**. ADR-010 states outright that `profile`/`include`/`fields` sparse-fieldset semantics cannot be expressed by codegen; the generated client would have to be hand-wrapped anyway, adding a layer without removing work. Rejected OpenAPI→Dart client generation for the same reason plus poor generator quality. |
| D3 | **`freezed` for entities, DTOs and state unions** | Rejected `equatable`: freezed gives `==`, `copyWith`, sealed unions for state and for the error taxonomy in one annotation. |
| D4 | **Bundle Plus Jakarta Sans and Manrope as assets** | Rejected `google_fonts`: it downloads fonts over the network at runtime, so type reflows on weak connections and falls back to the system font offline — a direct violation of the Arbor Heritage mandate ("never fall back to the device system font"). This is a live defect in the current app. |
| D5 | **`sqflite` with a single JSON cache table** | Rejected `hive` (v2 unmaintained; `hive_ce` is a community fork), `drift` (relational querying we do not need — the requirement is "show me what I last saw", not offline queries), `isar` (stalled since v3). |
| D6 | **`flutter_secure_storage` as the Supabase session store** | Rejected the `supabase_flutter` default, which is SharedPreferences — plaintext tokens on disk. `frontend-integration-guide.md` §2 forbids it explicitly. Requires a custom `LocalStorage` implementation. |
| D7 | **One Flutter package** | Rejected melos / multi-package. Web is Next.js; there is no second Flutter surface. The phantom `packages/family_roots_core` that Mobile CI referenced for five months never existed — do not create it. |
| D8 | **Proactive single-flight refresh on 401, via the Supabase SDK's `refreshSession()`** | Rejected copying the web client's approach of delegating entirely to SDK auto-refresh. A browser tab is alive; a phone is backgrounded for days. `frontend-integration-guide.md` §2 recommends reactive single-flight specifically for mobile. |
| D9 | **Import-boundary rules enforced by a test that scans `lib/`** | Rejected `dart_code_metrics` (now commercial) and `import_lint` (thin maintenance). A plain test adds no dependency, runs in CI, and mirrors the backend's `lint-imports` ratchet (ADR-013). |
| D10 | **Authentication ships inside M0, not as a separate milestone** | Rejected a screenless spine like web sub-project A. Web could afford that because the web app already runs; here the tree is being replaced wholesale, so the spine must be proven against the real backend early rather than after four PRs of tests. |

---

## 3. Target structure

```
mobile/lib/
├── main.dart                       # bootstrap only
├── app/
│   ├── app.dart                    # ProviderScope + MaterialApp.router
│   ├── bootstrap.dart              # Sentry, Supabase, cache, l10n init
│   └── router/                     # go_router + auth/email/clan guards
├── core/                           # infrastructure; knows nothing about features
│   ├── network/
│   │   ├── api_client.dart         # Dio wrapper, unwraps the envelope
│   │   ├── envelope.dart           # Page<T>, unwrapData, unwrapPage
│   │   ├── api_exception.dart      # sealed error taxonomy + policyActionFor
│   │   ├── token_refresher.dart    # single-flight refresh
│   │   └── interceptors/           # auth · clan · locale · trace · logging
│   ├── storage/
│   │   ├── secure_session_store.dart   # flutter_secure_storage LocalStorage
│   │   └── cache_store.dart            # sqflite key/JSON/timestamp
│   ├── observability/              # sentry · logger · traceparent
│   ├── theme/                      # design tokens → ThemeData + ThemeExtension
│   └── l10n/                       # ARB + generated AppLocalizations
├── domain/                         # pure Dart — no flutter, dio, riverpod, supabase
│   ├── shared/                     # ClanId, LocaleCode, HistoricalDate, Page<T>
│   ├── person/ · kinship/ · event/ · document/ · clan/
│   └── capability/                 # (role, clan state) → what the user may do
├── features/<slice>/
│   ├── data/                       # DTOs + repository implementation
│   ├── application/                # Riverpod notifiers — use-case orchestration
│   ├── presentation/               # pages and widgets owned by this slice
│   └── <slice>.dart                # PUBLIC SURFACE — the only cross-slice import
└── shared/widgets/                 # primitives shared across slices
```

### 3.1 Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| `domain/**` | `domain/**`, `dart:*` | `package:flutter/*`, dio, riverpod, supabase, json_annotation |
| `features/*/data` | `domain`, `core/network`, `core/storage` | flutter, any `presentation`, another slice |
| `features/*/application` | own `data`, `domain`, `core` | any `presentation`, another slice's internals |
| `features/*/presentation` | own `application`, `domain`, `shared/widgets`, `core/theme`, `core/l10n` | own or any `data` — no direct transport |
| `features/A` | `features/B` **only via `b.dart`** | `features/b/data/...`, `features/b/application/...` |
| `app/**` | slice public surfaces, `core` | any `data` |
| `core/**` | `core`, `domain` | any `features/**` |

Enforced by `test/architecture/layer_boundaries_test.dart` (D9), which parses the
import directives of every file under `lib/` and fails on violation.

### 3.2 Why this is still DDD/SOLID without the ceremony

The domain layer does not know transport exists (SRP, DIP). The DTO mapper is the
only place that knows the backend's wire shape, so a new backend field changes one
file (OCP). Each slice's `<slice>.dart` is a genuine segregated interface. What is
deliberately absent is a port interface plus a use-case class per CRUD operation:
an interface with exactly one implementation is ceremony, not inversion. This
matches the equivalent decision on web (sub-project A, D1).

---

## 4. The spine

### 4.1 Network stack

A single `Dio` instance with five interceptors, in this order:

| Interceptor | Responsibility |
|---|---|
| `AuthInterceptor` | `Authorization: Bearer <token>` from the current Supabase session |
| `ClanInterceptor` | `X-Current-Clan-Id` on clan-scoped routes only — skipped for `/auth/*`, `/me/clans`, `/me/clans/{id}/select`, `/invitations/{token}/accept`, `/platform/*` |
| `LocaleInterceptor` | `Accept-Language` from the app's selected locale |
| `TraceInterceptor` | W3C `traceparent` (ADR-033), so a mobile span joins the backend trace |
| `RefreshInterceptor` | on 401: one shared refresh, concurrent 401s queued behind it, retry the original request exactly once; on refresh failure, sign out |

The envelope is unwrapped in exactly one place. No widget, notifier or repository
ever sees `{"data": …}`:

```dart
Future<T>       getOne<T>(String path,  {..., required T Function(Object?) parse});
Future<Page<T>> getPage<T>(String path, {..., required T Function(Object?) parse});

class Page<T> {
  final List<T> items;
  final String? cursor;   // opaque; pass back verbatim or drop
  final bool hasMore;
  final int limit;
}
```

Cursors are never inspected. On `400 invalid_cursor` the paginated notifier clears
its cursor and refetches page one, per contract.

### 4.2 Error taxonomy

A sealed hierarchy in `core/network/api_exception.dart`:

```dart
sealed class AppException
  ApiException(code, message, detail, traceId)   // any {"error": …} body
  NetworkException(cause)                        // transport, DNS, offline
  TimeoutException()                             // deadline exceeded
  MalformedResponseException(body)               // envelope did not parse
```

A caller-initiated cancellation is rethrown unchanged and is never reported as a
network failure.

`policyActionFor(String code)` is the single function that turns a backend code
into a routing decision. UI branches on `code`, never on `message`:

| Code / status | Action |
|---|---|
| 401 | single-flight refresh, retry once; on failure sign out and route to login |
| 403 `email_not_verified` | resend-verification screen |
| 403 `account_deactivated` | blocked-account screen; sign out |
| 403 `clan_suspended` | clan-blocked screen, offer clan switch |
| 403 `no_approved_clan_membership` | pending-approval or onboarding |
| 400 `multiple_clans_no_selection` | clan picker |
| 400 `invalid_clan_id_format` | clear stored clan, re-resolve |
| 409 `stale_write` | reload the record, show "người khác vừa sửa", reapply the edit, resubmit with the new version — never blind-retry |
| 404 `clan_founder_not_found` | **onboarding state.** Admin sees a "designate thủy tổ" CTA; a non-admin sees "waiting on your clan admin". Never a generic not-found. |
| 429 `rate_limited` | honour `detail.retry_after` and the `Retry-After` header; never blind-retry login or refresh |
| 503 `auth_provider_unavailable`, `storage_unavailable` | transient-outage message with retry; never rendered as "wrong password" |

`message` arrives already localised, so it is displayed directly. A per-code
fallback table exists only for the offline case.

### 4.3 Session, clan context and routing

- The Supabase session is stored through a custom `LocalStorage` backed by
  `flutter_secure_storage` (D6) — iOS Keychain, Android Keystore.
- After login the client calls `GET /auth/me`, because the login response's
  `has_pending_membership` is always `false` (documented backend gap).
- Clan resolution follows `frontend-integration-guide.md` §1.2: `GET /me/clans`;
  one clan → select it; several → clan picker. The selection is persisted locally
  (it is not a secret, so ordinary preferences) and sent as a header on every
  clan-scoped request thereafter, including for single-clan users.
- `go_router` guards, driven by a `refreshListenable` on session state:
  unauthenticated → login; unverified → verification; no approved membership →
  pending/onboarding; no clan selected with several available → picker.

### 4.4 Domain rules the client must not reinvent

- **`HistoricalDate` is a model with behaviour**, not a struct. It owns the
  render rule (`date` when exact, else `display`, else `date`) and the sort key.
  No widget re-implements it.
- **đời is backend data.** Never derived, never inferred from tree depth. `null`
  renders honestly as "đời ?".
- **`depth` is not a nesting level.** `tree-read-model.md` warns that a node can
  nest deeper than `max_generations`. The renderer uses the `children` structure
  and `generation`; it ignores `depth`.
- **Polygyny**: children carry `mother_id` and `mother_spouse_order` and are
  grouped under each wife in that order. A node with `pedigree_collapse_ref: true`
  renders but never descends.

### 4.5 State and caching

Three provider kinds and no more:

| Kind | Used for |
|---|---|
| `@riverpod` function | a read with automatic caching — e.g. `personDetail(id)` |
| `@riverpod class …Notifier` | cursor-paginated lists and mutations |
| plain `Provider` | infrastructure — `dioProvider`, `sessionProvider`, `cacheProvider` |

One shared `PaginatedNotifier<T>` serves every cursor list. Mutations invalidate
with `ref.invalidate`, mirroring the web client's TanStack Query usage.

**Read cache (offline):** every successful network read writes its payload to
`CacheStore` with a timestamp. When the network fails, the notifier serves the
cached payload with an `isStale` flag and the UI shows a "dữ liệu ngày …" banner.
Writes always require the network — no write queue, no sync conflicts. Presigned
URLs are excluded from the cache by rule (§1.2).

### 4.6 Presentation, localisation, observability

- **Theme:** design tokens (colour, spacing, radius, elevation, typography)
  declared once as `ThemeExtension`s; `ThemeData` is built from them. No widget
  hardcodes a colour or calls a font helper inline. The Arbor Heritage mandates —
  no 1px borders, 9999px/2rem radii, never `#000000`, glass at 80% opacity with
  20px blur — are encoded as tokens, so violating them takes effort rather than
  inattention.
- **Text scaling is an architectural constraint.** Layouts must survive 200%.
  Golden tests cover the principal screens at scale 1.0 and 2.0.
- **l10n:** ARB + `flutter gen-l10n`. The app **ships `vi` and `en`** — the two
  locales for which translations exist — with `vi` as default and fallback.
  `zh` and `fr` are accepted by the backend and are added to `supportedLocales`
  when their ARB files are written; nothing in the architecture blocks them, and
  no code may assume the set is exactly two. No user-facing string is hardcoded.
  The active locale drives `Accept-Language`. The app stores the user's locale
  itself and does not trust the backend's `preferred_locale`, which always returns
  `"vi"` (documented backend gap).
- **Observability:** `sentry_flutter` plus `traceparent` per ADR-033, so a crash
  on a phone links to the exact backend log line. User-facing errors surface a
  short trace id, as on web.

### 4.7 Package set

| Package | Version | Role |
|---|---|---|
| `flutter_riverpod` | 3.4.2 | state + DI |
| `riverpod_annotation` / `riverpod_generator` | 4.0.6 / 4.0.8 | provider codegen |
| `riverpod_lint` + `custom_lint` | 3.1.8 / 0.8.1 | Riverpod-specific correctness lints |
| `go_router` | 17.3.0 | routing + guards |
| `dio` | 5.11.0 | HTTP |
| `freezed` | 3.2.5 | entities, DTOs, state unions |
| `json_serializable` | 6.14.1 | DTO (de)serialisation |
| `supabase_flutter` | 2.16.0 | auth session |
| `flutter_secure_storage` | 10.3.1 | session at rest |
| `sqflite` | 2.4.3 | read cache |
| `sentry_flutter` | 9.26.0 | crash + tracing |
| `firebase_messaging` | 16.4.3 | push (M4) |
| `intl` | 0.20.3 | date/number formatting |
| `flutter_lints` | 6.0.0 | lint baseline |
| `mocktail` / `http_mock_adapter` | 1.0.5 / 0.6.1 | test doubles |
| `build_runner` | 2.16.0 | codegen driver |

All verified against pub.dev on 2026-08-02 and all compatible with Dart 3.12
(Flutter 3.44.8 stable, the version `subosito/flutter-action@v2` resolves in CI
and the version installed locally).

---

## 5. Testing and CI

| Layer | Method |
|---|---|
| domain | pure unit tests, no Flutter binding — date rendering, đời display, kinship, capability |
| network | `http_mock_adapter` — envelope, pagination, every error code, single-flight refresh, retry-exactly-once |
| repository | DTO → domain mapping, built from JSON examples **copied verbatim from `docs/contracts/`** |
| application | `ProviderContainer` with fake repositories |
| presentation | widget tests with `ProviderScope` overrides; goldens at text scale 1.0 and 2.0 |
| architecture | the import-boundary scan (D9) |

`analysis_options.yaml` enables `strict-casts`, `strict-inference` and
`strict-raw-types` on top of `flutter_lints`, plus `custom_lint` with
`riverpod_lint`.

**Generated code is committed.** `*.g.dart` and `*.freezed.dart` are checked into
git rather than gitignored, so a fresh clone analyses, tests and opens in an IDE
without a build step first. CI then re-runs `build_runner` and fails if the result
differs from what is committed — which turns "forgot to run build_runner" from a
mysterious local error into a named CI failure, directly mitigating R1.

`.github/workflows/mobile-ci.yml` is rewritten:
`dart format --set-exit-if-changed` → `dart run build_runner build --delete-conflicting-outputs`
→ `git diff --exit-code` (the freshness check above) → `flutter analyze` →
`flutter test --coverage` → `flutter build apk --debug`.
The `packages/**` path trigger is removed (that directory has never existed) and
the workflow file is added to its own triggers so a change to Mobile CI is
validated by Mobile CI.

---

## 6. Milestones

Each milestone gets its own plan and its own PR sequence. Only M0 is planned now.

| | Scope | Done means |
|---|---|---|
| **M0** | Delete the old tree; new project; everything in §3–§5; **plus** login → `GET /auth/me` → clan resolution → an authenticated screen listing the user's clans from `GET /me/clans` | You can sign in to the real backend from a real device. The spine is proven end to end, not only by tests. |
| **M1** | Persons: cursor list, search, detail, create, edit, `409 stale_write` handling | Full member CRUD |
| **M2** | Tree: full tree, đời, polygyny grouping, focus view, founder-404 onboarding | The gia phả is viewable |
| **M3** | Events and documents, including presigned-URL handling | Giỗ chạp, photos, records |
| **M4** | FCM push and clan administration | Notifications, member approval, role assignment |

---

## 7. Out of scope

Offline-first with a write queue. Multi-package/melos. Retrofit. OpenAPI client
generation. Deep links. State restoration. Stitch design-drift tracking.
On-device integration tests in M0. Each is rejected for M0 specifically and may
be revisited later; adding any of them now lengthens M0 without proving anything
further about the spine.

---

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The owner has not written Flutter before, and Riverpod codegen means a `build_runner` step whose omission produces confusing errors | Documented prominently in the rewritten `mobile/CLAUDE.md`; CI fails when generated files are stale |
| R2 | **The email-verification and password-reset landing URLs are undetermined.** `frontend-integration-guide.md` flags this ⚠️ twice: whether the link carries `token_hash`+`type` or a PKCE `?code=` depends on Supabase project configuration and **is not knowable from this repository** | **Owner action inside M0:** check the Supabase dashboard's email templates and record the answer before the verification screen is written |
| R3 | Backend always returns `preferred_locale: "vi"` regardless of what was saved | The app owns locale storage and never reads that field (§4.6) |
| R4 | `persons.avatar_url` is a plain client-writable string that no backend code populates; what belongs in it is ⚠️ UNDEFINED | Needs a backend decision before M2/M3. Writing a presigned URL there would silently break after one hour |
| R5 | Deleting `mobile/` removes the only Flutter surface for a period | The deletion is one commit in git history and fully recoverable; the `.arb` files, design mandates and assets are carried forward explicitly |
| R6 | Riverpod 3 and `riverpod_generator` 4 are recent majors | Both verified against Dart 3.12 on pub.dev; `riverpod_lint` catches the common misuses at analysis time |

---

## 9. Documentation to update in the same PRs

- `mobile/CLAUDE.md` — rewritten wholesale for the new architecture, commands and codegen workflow
- `CLAUDE.md` (root) — services map, mobile commands, "Dart business entities live in mobile/lib/domain"
- `docs/decisions/034-mobile-riverpod-rebuild.md` — this decision, with the index updated
- `docs/work-register.md` — §2.3 replaced with the milestone list
- `docs/contracts/frontend-integration-guide.md` — the mobile references to `auth_interceptor.dart` as a scaffold
