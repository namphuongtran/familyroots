# ADR-063: Auth Email Links Land as a `token_hash` on a Page of Ours, Spent Only by a User Action, and the Templates Live in the Repository

## Status

Accepted (2026-10-04). Resolves issue #178, "Should auth email links land through Supabase's verify
redirect or as a token_hash on our page?", on the map in issue #158. The maintainer chose every
option below in a grilling session on 2026-10-04.

**This ADR ships no runtime code.** The diff is this file, its index row, and the documents that
described the old shape or deferred to #178, listed under Related. Documentation only, so no gate
applies. The code is in three build issues and one owner step, #200 to #203, listed in § 8.

Repository readings were taken on **2026-10-04** at commit `300c58b` on `main`. Supabase readings
are **source readings, not measurements**, at the versions named beside each. Nothing in this ADR
was observed against the hosted project. Treat line numbers as hints and quoted text as the claim.

## Context

### The two emails, and who sends them

The backend sends both, through the anon client of `supabase_auth` 2.31.0:

- **Confirm signup**, from `auth.resend` with type `signup`
  (`backend/app/infrastructure/supabase_identity_provider.py:178-187`). It is sent by
  `POST /auth/register` and `POST /auth/resend-verification`.
- **Reset password**, from `auth.reset_password_email` (`:163-176`). It is sent by
  `POST /auth/forgot-password`, and by `POST /auth/register` for an address that already has an
  account (`backend/app/application/auth/handlers.py:333`, ADR-021 § 1).

Neither call sends a `code_challenge`, so the flow is implicit and the link never lands as `?code=`.
#163 established this, in `docs/contracts/frontend-integration-guide.md` § 3.1.

**No client reads either link today.** The web has no confirmation landing, no forgot-password page
and no reset page, and its login page has no "forgot password" link. The mobile app has no deep-link
configuration: one `MAIN`/`LAUNCHER` intent-filter, no `CFBundleURLTypes`, no associated domains.
Its spec puts deep links out of scope (`docs/superpowers/specs/2026-08-02-mobile-architecture-design.md:380`).
Mobile also has no register or forgot-password call.

### What the default template does

With `{{ .ConfirmationURL }}`, the link opens Supabase's `/auth/v1/verify`. Supabase spends the
token on that GET, then redirects with the session in a URL fragment. Three problems follow:

1. **An email scanner can spend the token before the person clicks.** Supabase's own documentation
   warns about it (supabase/supabase@7353782,
   `apps/docs/content/guides/auth/auth-email-templates.mdx:133-165`): "the `{{ .ConfirmationURL }}`
   sent will be consumed instantly which leads to a 'Token has expired or is invalid' error." Its
   two remedies are a typed code, or a page of your own with a button.
2. **Sign-up is confirmed on the scanner's or the person's GET**, before any page of ours runs.
3. **Neither web client can read the landing.** A fragment never reaches a server, and
   `@supabase/ssr` 0.12.4 fixes the browser client to PKCE. That client throws
   `Not a valid PKCE flow url.` on an implicit fragment (§ 3.1 of the integration guide).

### What a `token_hash` link does

The template can build its own link from `{{ .TokenHash }}`. The landing page then calls
`verifyOtp({ type, token_hash })`.

- **It works on both PKCE clients.** auth-js v2.111.0 POSTs `/verify` and saves the session, with
  no code verifier and no flow-type check (`GoTrueClient.ts:2458-2495`). gotrue-dart v2.26.0, the
  version in `mobile/pubspec.lock`, is the same (`gotrue_client.dart:572-630`).
- **The type is `email` for sign-up and `recovery` for reset.** auth-js marks `signup` deprecated
  (`GoTrueClient.ts:2330`). `recovery` fires `PASSWORD_RECOVERY`.
- **A GET does not make it safe.** Supabase's Next.js guide spends the token in a GET route handler
  (`guides/auth/passwords.mdx:196-224`). A scanner's GET reaches that handler too.

### The template is state, and part of what was said about it was wrong

On 2026-10-04 both hosted templates held a placeholder `href` (#163). `docs/ops/supabase-hosted-project.md`
then said no command could read a template body. That is true of `config diff` and `config pull`.
In CLI 2.119.0 they carry only subjects (supabase/cli@v2.119.0,
`packages/config/src/project-config/registry-auth.ts:694-699,732-735`). But:

- **The Management API returns the body.** `GET /v1/projects/{ref}/config/auth` answers
  `AuthConfigResponse_Output`, whose required fields include `mailer_templates_confirmation_content`
  and `mailer_templates_recovery_content`. The scope is `auth:read`.
- **`config push` sends the body** read from `content_path` (`apps/cli`
  `push.auth-email-content.ts:88-108`, `push.encoders.ts:1412-1425`). **It writes only the
  properties the file declares** (`push.command.ts:44`: "Properties the file does not declare are
  left unchanged"). The older Go CLI always built `site_url` and others into the body
  (`apps/cli-go/pkg/config/auth.go:408-443`), so this holds for the TypeScript CLI only.

So a template kept in the repository can be pushed without touching other settings, and read back.

## Decision

### 1. Both emails carry a `token_hash` link to a page of ours

| Template | Link |
|---|---|
| Confirm signup | `{{ .SiteURL }}/verify-email/confirm?token_hash={{ .TokenHash }}&type=email` |
| Reset Password | `{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery` |

Neither template uses `{{ .ConfirmationURL }}` or `{{ .RedirectTo }}`.

### 2. The token is spent only by a user action

Never on page load and never in a GET route handler. A scanner fetches. It does not press buttons
or submit forms.

- **Confirmation:** the page shows a "Xác nhận email" button. Pressing it calls
  `verifyOtp({ type: 'email', token_hash })`.
- **Reset:** the page shows the new-password form at once. One submit calls
  `verifyOtp({ type: 'recovery', token_hash })`, then `updateUser({ password })`. If `verifyOtp`
  fails, the page shows the expired state, with a link to `/forgot-password`. If `updateUser` fails,
  for example on a weak password, the session from `verifyOtp` still holds, so the person retries on
  the same screen.

### 3. A confirmed or reset person stays signed in

`verifyOtp` returns a session, and the confirmation page keeps it. The success state's "Tiếp tục"
goes to the one server guard of ADR-061 § 3, which routes to pending approval, onboarding or the
dashboard. The copy also says the person can now sign in on the app.

The reset page does the same after `updateUser` succeeds.

This grants nothing new. Anyone holding the mailbox can already reach a session through the recovery
link. It replaces spec § 7.1c's "auto-route to login after 3s", and the integration guide's "route
to login" after a reset.

### 4. The origin comes from the Site URL, and the locale from the reader

The link's origin is the project's **Site URL**, one value per Supabase project, which a deploy must
set anyway (ops § 3). The link path carries **no locale**. `localePrefix: 'always'` makes next-intl's
middleware redirect it to the reader's locale, and that redirect keeps the query string
(`t.nextUrl.search` in `next-intl/dist/esm/production/middleware/middleware.js`).

**The backend's `EMAIL_VERIFY_REDIRECT_URL` and `PASSWORD_RESET_REDIRECT_URL` are deleted.** The
template ignores `{{ .RedirectTo }}`, and both settings are empty in every environment today
(`backend/.env.example:57-58`, with neither set in `infra/render/render.yaml`).

### 5. One web landing serves web and mobile users

A person who registered on mobile finishes in the browser, then signs in on the app. Deep links
stay out of scope. Later, an App Link or Universal Link can claim the same `https` paths without a
template change.

### 6. The templates live in the repository and are read back after a push

- `supabase/templates/confirmation.html` and `supabase/templates/recovery.html` hold the bodies.
- The local `supabase/config.toml` points at them through `content_path`, so the local stack's
  Mailpit renders the same body.
- The hosted project gets them by `supabase config push` from a **separate, checked-in config that
  declares only `[auth.email.template.confirmation]` and `[auth.email.template.recovery]`**. Never
  from `supabase/config.toml`, which configures the local stack (ops trap 4).
- A read-back script compares the hosted bodies from the Management API with the files. **The owner
  runs it after every push.** It needs a personal access token, so it is not a CI job.

### 7. Vietnamese first, English below, in one body

The template cannot branch per person. The backend creates the user with no `preferred_locale` in
`user_metadata` (`supabase_identity_provider.py:69-74`). Branching on `{{ .Data.preferred_locale }}`
is additive, and needs that write first.

### 8. Three build issues and one owner step, all in M2

| Issue | What | Blocked by |
|---|---|---|
| #200 | Sign-up confirmation lands on `/{locale}/verify-email/confirm` | #183 |
| #201 | Forgot and reset password: the login link, `/{locale}/forgot-password` and `/{locale}/reset-password` | #183 |
| #202 | The templates live in the repository and can be read back. Deletes the two settings | #200, #201 |
| #203 | The owner pushes the templates to the hosted project and reads them back (`ready-for-human`) | #202 |

#200 and #201 wait on "build features/auth" (#183), because new auth pages belong in the slice
(ADR-060, ADR-061 § 1). **The templates wait on both pages.** Pushing the confirmation template
before its page exists would leave every new sign-up unconfirmable. Today's default template at
least confirms on the click. The push is its own issue because it needs the owner's Supabase login,
so no agent can reach that end state.

## Consequences

Easier:

- A scanner can no longer spend a confirmation or recovery token.
- Both clients the project ships can spend a token. Neither has to parse a fragment.
- The failure arrives as a value the page reads, so spec § 7.1c's expired state is reachable.
- The template body has history, review, and a read-back that measures the hosted copy.
- One source names each environment's landing origin.

Harder:

- Sign-up confirmation costs one extra tap.
- The two web paths and the two templates are coupled. Renaming a path needs a template push.
- A push and its read-back are owner steps that CI cannot take.
- A wrong Site URL now breaks every email link, not only redirects. That was already true for
  redirects, and the deploy step that sets it is the same.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep `{{ .ConfirmationURL }}` | A scanner spends the token. The fragment throws on the web's PKCE client. Sign-up confirms before any page of ours runs |
| `token_hash`, spent on page load or in a GET route (Supabase's Next.js guide) | A scanner's GET spends it the same way |
| A typed `{{ .Token }}` code only | Each client needs a code-entry screen, and the person types an address and an 8-digit code. Adding the code to the same email later is additive, because the hash is derived from the code (`supabase/auth` `mail.go:330-332`) |
| `{{ .RedirectTo }}` as the base, composed per request from #191's `INVITE_LINK_ORIGIN` and the locale | Couples this work to #191. A URL that fails Supabase's allow-list silently falls back to the bare Site URL, and the path is lost |
| One landing page that branches on `type` | The two have different states: a success panel against a new-password form |
| Reset: a "Continue" button first, then the form | One more tap, for no safety the form's submit does not already give |
| Sign out after confirming, and route to login | One more password step. It protects nothing the recovery link does not already expose |
| Templates in the dashboard only | That is how a placeholder `href` reached the hosted project, with no history |
| Templates in the repository without a read-back | Drift is invisible again |
| A mobile deep link now | No intent-filter, no associated domain, no register or forgot-password screen, and an empty Redirect URLs list |
| Branch the template on a per-person locale | Needs the backend to write `preferred_locale` at creation first |

## What this ADR deliberately does not decide

- **Mobile deep links.** They stay out of scope, per the mobile spec § 7.
- **The deployed origin and the Redirect URLs list.** That is M3, per ops § 3.
- **The typed code.** It stays open as an addition.
- **The email copy**, beyond its language order. That is build issue 3.
- **The SMTP sender.**

## Related

- [ADR-015: Email Verification via Admin-Create-Unconfirmed + Best-Effort Resend](015-email-verification-flow.md):
  its `EMAIL_VERIFY_REDIRECT_URL` line is superseded by § 4.
- [ADR-021: Non-Enumerating Auth Surfaces](021-non-enumerating-auth-surfaces.md): the recovery
  nudge on register lands on the reset page of § 1.
- [ADR-061](061-the-auth-session-is-server-state-and-access-is-routed-on-the-server.md): its
  "What this ADR deliberately does not decide" pointed here. § 3 above hands off to its server guard.
- `docs/contracts/frontend-integration-guide.md` § 3, § 3.1 and § 4, `docs/contracts/rest-auth-api.md`,
  `docs/architecture/auth-flow.md`: now describe this shape as decided and not yet built.
- `docs/ops/supabase-hosted-project.md` § 4 and traps 3 and 4: corrected about reading and pushing
  template bodies.
- Spec `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` § 7.1c: the landing's states
  now follow § 2 and § 3.
- Mobile spec `docs/superpowers/specs/2026-08-02-mobile-architecture-design.md`, risk R2: answered.
