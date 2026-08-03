# Work Register

**What this is:** the running list of what is in flight, what is queued, and what
we have knowingly left undone. Specs and plans hold the *how*; this file holds the
*state* — which of them are live, which are finished, and which decisions were made
outside any document.

**Keep it current.** Update this file in the same PR that changes the state of an
item. When an item is finished, move it to *Landed* with its merge commit, and delete
it once the git history and the ADRs tell the story on their own.

Last updated: 2026-08-03 (§3.1 METRICS_TOKEN and §3.5 test-DB name closed).

For the coarse view — which streams exist, which have plans, and what is next — see
[roadmap.md](roadmap.md). This file is the fine-grained state underneath it.

---

## 1. In flight

### 1.1 Dependency upgrade sweep — closed

Backend, web and mobile are all done (see §4).

- **Mobile:** closed — obsoleted by the rebuild (§2.2, ADR-034). The new project pins an
  explicit, resolvable package set; the pins and *why each one cannot move* are in
  `mobile/CLAUDE.md`. `flutter_bloc ^8`,
  `get_it ^7`, `go_router ^14`, `retrofit >=4 <5` and `hive ^2` are not carried into
  the new project, so there is nothing left to upgrade. The blocker itself is also
  gone: Flutter 3.44.8 stable (Dart 3.12.2) — the version
  `subosito/flutter-action@v2` resolves in CI — was installed locally on 2026-08-02,
  so mobile changes are now verified before they are pushed rather than by CI
  round-trip. First local run of the existing suite: `flutter analyze` clean,
  28/28 tests passing.

Three upgrades were attempted and deliberately not taken, each blocked upstream
rather than by our code:

| Package | Wanted | Landed | Why |
|---|---|---|---|
| `typescript` | 7.0.2 | 6.0.3 | typescript-eslint hard-errors on TS 7 (`typescript-eslint#10940`, targets ≥7.1), and eslint-config-next loads it, so the whole lint step dies. TS 7 itself type-checks and builds fine. |
| `eslint` | 10.8.0 | 9.39.5 | `eslint-plugin-react`'s latest release (7.37.5) declares `eslint: ^3 \|\| … \|\| ^9.7` and throws inside `usedPropTypes` on v10. `eslint-config-next` depends on it. |
| `firebase-admin` `Message.fid` | — | kept `token` | `fid` is a Firebase Installation ID, `token` a device registration token — distinct, mutually exclusive wire fields. Switching needs the Flutter client to send installation IDs first. The deprecation warning is filtered by exact message. |

Re-check all three when the upstream packages move.

**Consequence for sub-project A (§1.3):** resolved. The spine plan was re-verified on
2026-08-02 against the upgraded tree; its Global Constraints now state the zod-4
`z.input`/`z.output` rule for the slice PRs that will write boundary schemas.

---

### 1.2 Owner actions outstanding — these block shipped code

Neither can be done from the repository. Both are recorded here because the code that
needs them is already on `main`.

**A. Create the public avatars bucket in Supabase, per environment.** ADR-036 / #132 is
merged, so `PATCH /documents/{id}/set-avatar` currently returns
**`503 storage_bucket_not_configured`** in every environment and writes nothing.

| Setting | Value |
|---|---|
| Name | `family-roots-avatars` (matches `SUPABASE_AVATAR_BUCKET`; **must not** be `family-roots-files`) |
| Public bucket | on, public read — the adapter calls `get_bucket()` and refuses to copy if `public` is false |
| Allowed MIME | `image/jpeg, image/png, image/webp, image/heic` |
| Size limit | ≥ `MAX_UPLOAD_SIZE_MB` (50 MB) |
| Write access | service-role key only; no anonymous write policy |

No CORS rule is needed — clients render via `<img src>`. Remember the accepted
consequence: **publishing is one-way.** Soft-delete and the retention purge remove only
the private blob, so the public object and `avatar_url` survive and anyone holding the
URL keeps access. Deleting a photo in the app does not remove it from the internet.

**B. Report the Supabase email-template link format.** Blocks the real email-verification
flow. Not knowable from this repo — it depends on project configuration.

1. Authentication → Emails (or *Email Templates*) → open **Confirm signup**, and report
   whether the link uses `{{ .ConfirmationURL }}` or `{{ .TokenHash }}`.
2. Authentication → URL Configuration → report **Site URL** and the **Redirect URLs** list.

Do not send a real verification email or a live token — only the template shape is needed.

This does **not** block mobile M0: deep links are out of scope per the mobile spec §7, and
the verification screen there needs only `POST /auth/resend-verification`.

---

### 1.3 Sub-project A — web architecture spine + observability

- **Spec:** `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`
- **Plan:** `docs/superpowers/plans/2026-08-02-web-spine.md` — 13 tasks (0–12)
- **Status: all 13 tasks landed on `main` (#144).** PR 0 of sub-project A is closed by
  Task 12; feature slice PRs (persons, relationships, tree, events, documents, auth,
  admin, platform, backoffice) build on top of it next.

| Task | What | PR / branch |
|---|---|---|
| 0 | Node 22 floor | #122 |
| 1 | Vitest harness + `HistoricalDate` | #127 |
| 2–4 | OpenAPI types, envelope + error taxonomy, request context | #129 |
| 5–7 | traceparent, single-flight refresh, `apiFetch` | #134 |
| 8–10 | Sentry + Web Vitals, component harness, dependency-cruiser | #139 |
| 11 | Playwright harness and CI wiring (incl. `api-types-fresh` triggers) | #144 |
| 12 | Documentation sync (this entry, `web/CLAUDE.md`, `docs/sad/`) | #144 |

Full gate green on that branch: `pnpm type-check && pnpm lint && pnpm depcruise &&
pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build` — 55 unit tests,
3 component tests, 6 e2e tests (3 specs × 2 projects; 2 of the 6 are the deliberate
`test.fail()` pinning R-lang, §3.1), `depcruise` clean at 0 errors / 3 warnings (orphan
modules, within the plan's carve-out).

Task 11's own gate found the drift it was built to catch: `api-types-fresh` failed on
first run because `src/generated/api-types.ts` predated ADR-036, ADR-037 and ADR-039 —
the whole `/change-requests` surface was missing. Regenerated in #144.

The plan's own record of what was verified by execution — including the defects it found
and fixed along the way — is in the plan file's "Verification status — second pass" and
"Defects found and fixed" sections, not duplicated here.

## 2. Queued

### 2.1 Sub-project B — design system and UX for all ages

- **Spec:** `docs/superpowers/specs/2026-08-02-design-system-and-screens.md`
- **Artifact:** https://claude.ai/code/artifact/2b97d988-12af-4614-8148-294869ffb532
- **Status:** tokens, components, accessibility rules and 15 screen groups specced
  (#130, #137). No implementation started — B implements against the mobile and web
  architectures rather than the other way round.
- **Blocking finding (#146, spec §2.8.1):** the `@theme` block already in
  `web/src/app/globals.css` mostly does not work. All thirteen semantic colour tokens are
  declared `hsl(var(--x))` over hex values, so every one is invalid and dropped; there is
  no `.dark` block at all; the Vietnamese-subsetted Inter is loaded and then never
  referenced, `Playfair Display` is referenced and never loaded, and neither is the
  mandated typeface; and four colour pairs fail WCAG AA, including `destructive` in both
  directions. Measured in a browser, not read. Nothing can be implemented against these
  tokens until they resolve — fix order is in §2.8.1.

Deferred and blocked backend-side: onboarding tour, PDF book, import, a devices list,
and change requests beyond `person`-update.

Design rules recorded there that constrain future backend work, worth knowing before
someone builds the thing that contradicts them:
- **No privacy control ships until enforcement does.** `clan_settings.allow_public_tree`
  and `privacy_level` exist and enforce nothing; a toggle that restricts nothing is the
  most dangerous control in the product.
- **When a server field and a timestamp disagree, the timestamp wins** — invitations keep
  `status: "pending"` past `expires_at` with no sweep.
- No copy promises a notification, because no notification exists for any queue event.

### 2.2 Sub-project D — mobile rebuild

- **Spec:** `docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`
- **Decision:** [ADR-034](decisions/034-mobile-riverpod-rebuild.md)
- **Plan:** `docs/superpowers/plans/2026-08-02-mobile-m0-spine.md` — 20 tasks

**M0 Tasks 1–19 have landed** (#136, #138, #147, #148, #149, #150): the old scaffold is
gone, the app assembles, and CI builds `app-debug.apk`. 128 tests, `flutter analyze`
clean, `build_runner` and `gen-l10n` producing no diff.

| | Scope | Done means | State |
|---|---|---|---|
| **M0** | Delete the old tree; new project; everything in spec §3–§5; **plus** login → `GET /auth/me` → clan resolution → an authenticated screen listing the user's clans | You can sign in to the real backend from a real device. The spine is proven end to end, not only by tests. | **Tasks 1–19 landed; Task 20 outstanding — see below** |
| **M1** | Persons: cursor list, search, detail, create, edit, `409 stale_write` handling | Full member CRUD | not planned |
| **M2** | Tree: full tree, đời, polygyny grouping, focus view, founder-404 onboarding | The gia phả is viewable | not planned |
| **M3** | Events and documents, including presigned-URL handling | Giỗ chạp, photos, records | not planned |
| **M4** | FCM push and clan administration | Notifications, member approval, role assignment | not planned |

Each milestone gets its own plan and PR sequence. **Plan M1 only after Task 20** — M0's
own definition of done is "proven on a device", and planning M1 against an unproven spine
is how you inherit its mistakes.

#### M0 is not done: Task 20 is blocked, and the blockers are owner-side

Everything above is verified against **canned transports and a fake-async widget tester**.
`Supabase.initialize` and `SentryFlutter.init` need platform channels and have therefore
**never executed**. Login against real Supabase, token refresh, and session survival
across a relaunch are **unverified**.

Three blockers, none solvable from the repository:

1. **No device or emulator.** The dev machine has no Android SDK and an incomplete Xcode;
   `flutter devices` and `flutter emulators` both find nothing. Needs Android Studio + an
   AVD, a full Xcode + simulator, or a physical phone.
2. **No Supabase credentials.** Only `.env.example` files are committed, correctly. The
   run needs real `--dart-define=SUPABASE_URL=… SUPABASE_PUBLISHABLE_KEY=…`.
3. **No test accounts.** The acceptance walk needs a verified user with an approved
   membership, a second multi-clan account, and an unverified one.

The acceptance checklist to walk is the plan's Task 20 step 3. Start the backend with
`--host 0.0.0.0` (the default binds loopback and a phone cannot reach it) and pass the
machine's LAN address as `API_BASE_URL`.

#### Traps found by execution — do not re-introduce these

- **The l10n fallback** (#148): `gen-l10n` emits `supportedLocales` alphabetically, and
  `MaterialApp` resolves an unsupported locale to `supportedLocales.first` — so making
  `app_vi.arb` the *template* does not make `vi` the *fallback*.
  `preferred-supported-locales` in `l10n.yaml` orders the list. Any new locale must be
  added there too, or it silently changes which language a `zh`/`fr` user sees.
- **The Riverpod deadlock** (plan V27, held in #149): auto-selecting a clan must stay a
  notifier *method* (`SelectedClan.resolve()`). Writing to `selectedClanProvider` from a
  provider that also watches it deadlocks the container — it hangs ~30s then fails with
  "disposed during loading state, yet no value could be emitted".
  `clanResolutionProvider` stays pure and read-only.
- **No network call before sign-in** (#150): the app shell must watch
  `clanPickRequiredProvider`, not `clanResolutionProvider`. Watching the latter fired
  `GET /me/clans` at launch — unauthenticated, so it 401s, and the refresh interceptor
  then finds no session and signs the user out. Opening the app could sign you out.
  Pinned by a test asserting zero HTTP calls on the login screen.
- **Escaping the clan picker needs both halves, in order** (#150): go_router 17 re-runs
  `redirect` for the *current* location, so navigating while the guard still holds bounces
  straight back, and clearing the guard alone leaves the user in place. `onSelect` must
  clear `needsClanPick` and *then* `context.go`.
- **`testWidgets` bodies run in a fake-async zone** (#150), where sqflite's FFI I/O never
  completes: opening a real database inside a widget test **hangs** rather than failing.
  Use an in-memory `CacheStore` fake there. Plain `test()` bodies are unaffected.
- **Riverpod 3.2.1 has no `AsyncValue.valueOrNull`** — the nullable accessor is `value`.

#### Known CI gaps, both owned by a future task

- **Goldens are excluded from CI** (`flutter test --exclude-tags golden`). Golden images
  are host-renderer sensitive and the baselines were rendered on macOS, so on the Linux
  runner they would fail for a reason unrelated to the code. They run locally. Restoring
  them needs baselines generated in a Linux container.
- **`flutter build apk --debug` is only ever exercised in CI**, because the dev machine
  has no Android SDK. It passes there.


## 3. Open gaps — knowingly unfixed

### 3.1 R-lang — every page declares the wrong language

`src/app/layout.tsx` hardcodes `<html lang="en">`, and `src/app/[locale]/layout.tsx`
renders a `<div>`, so the selected locale never reaches the `lang` attribute. Screen
readers apply English pronunciation rules to Vietnamese content across the whole
product. Confirmed by request: `/vi/login` serves `<html lang="en">`.

The fix is structural — `<html>`/`<body>` must move into a locale-aware layout while
`src/app/page.tsx` and `src/app/api/*` still sit outside the `[locale]` segment.
**Owner: sub-project A, PR 1 (auth)**, which already rewrites the locale, cookie and
middleware machinery. A `test.fail()` in `web/e2e/smoke.spec.ts` (added by spine
Task 11) keeps CI green while the bug exists and turns red the moment it is fixed.

### 3.2 `pnpm format:check` fails on 112 web files

Pre-existing prettier drift in files no recent branch has touched
(`src/middleware.ts`, `src/store/auth.store.ts`, `tsconfig.json`, …). It is not part
of the documented web gate (`pnpm type-check && pnpm lint`), so CI stays green.
Running `pnpm format` would fix it in one sweep at the cost of a 112-file diff —
worth folding into sub-project A rather than doing standalone.

### 3.3 Branch hygiene has no automation

The remote was swept to a single `main` on 2026-08-02, but nothing stops it refilling:
**delete-branch-on-merge is not enabled** on the repository. Every future PR leaves its
branch behind. Turning it on in Settings → General is a one-click owner action and
removes this class of debt permanently.

### 3.4 Pre-existing platform debt

Carried from `CLAUDE.md` — none of these are scheduled:

- Pulumi resources are stubs; deployment drift is possible.
- The in-process event dispatcher has no durable delivery guarantee. Do not treat
  in-process events as integration events without explicit mitigation.
- Prompt-2 TODO scaffolds remain across mobile, infra, and helper scripts.
- The web test harness (§1.3) now has all four kinds (unit, component, e2e, dependency
  boundaries) but only covers the spine — no feature slice has tests yet. Each slice PR
  is expected to add its own.

---

## 4. Landed recently

| Work | Where | Merge |
|---|---|---|
| Backend dependency sweep + httpx2 (71 packages, 5 majors) | `backend/pyproject.toml` | `d2d2de1` |
| Web dependency sweep: Tailwind 4, zod 4, TS 6 | `web/package.json` | `a457e29`, `5f4cb7f`, `5dc340a`, `e3ce8d8` |
| W3C trace context + Prometheus metrics (ADR-033) | `docs/superpowers/plans/2026-08-02-backend-trace-context-metrics.md` | `dc6f499`, CI green |
| Software Architecture Document (arc42 + C4) | `docs/sad/` | PR #121 |
| Backend production-readiness backlog | — | complete per owner sign-off |
| C1–C3 seam-review fixes | `docs/superpowers/plans/2026-07-04-seam-review-critical-fixes.md` | #22, #23, #24 |
| Web spine Tasks 0–10 | `web/src/{domain,shared,generated}` | #122, #127, #129, #134, #139 |
| Mobile rebuild M0 Tasks 1–5 | `mobile/` | #136, #138 |
| Backend client-blocking gaps + ADR-035 | `docs/contracts/` | #128 |
| Public avatar URLs (ADR-036) | `app/application/document/` | #132 |
| Change requests (ADR-037) | `app/domain/change_request/` | #133 |
| persons RLS `RETURNING` fix (ADR-038) | `app/models/person.py` | #135 |
| Clan user-list identity fields (ADR-039) | `app/api/v1/clans.py` | #140 |
| Design system + 15 screen groups | `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` | #130, #137 |
| Remote branch sweep — 108 branches deleted, `main` only | `origin` | 2026-08-02, no merge commit |
| `METRICS_TOKEN` length floor + 404-preserving failure throttle (ADR-040) | `app/core/metrics_guard.py`, `app/core/config.py` | `chore/backend-metrics-and-test-db` |
