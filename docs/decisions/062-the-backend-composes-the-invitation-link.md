# ADR-062: The Backend Composes the Invitation Link, on `INVITE_LINK_ORIGIN` and the Request Locale

## Status

Accepted (2026-10-05), resolving issue #191. **This ADR ships code**: `invite_url` replaces
`accept_path` in the 201 body of `POST /clans/{clan_id}/invitations`, and `INVITE_LINK_ORIGIN`
becomes a backend setting.

It discharges [ADR-057](057-the-invitation-link-is-the-primary-join-path.md)'s Owed item 2, and
it settles the variable name ADR-057 left undecided.

The issue's sources were read at `9d6ebbe` on 2026-10-04. This change was written on
`fix/191-invite-url`, based on `27ec0b5`. Where a line number is given, it was read there.

## Context

ADR-057 § 3 decided what an admin shares: `https://<origin>/<locale>/invitations/<token>`, a
browser URL on the web app's own origin. It decided that `<origin>` is its own variable and
**not** `NEXT_PUBLIC_API_URL`, which
[ADR-056](056-next-public-api-url-splits-into-a-browser-and-a-server-variable.md) gave to the
browser-facing API origin. It did not change the backend, and it named the repair as owed:
"Repair `accept_path` … so the field the admin is handed is the browser URL this ADR names. It
becomes actionable once the page exists and the origin variable has a name."

**Both conditions now hold.** The page exists at
`web/src/app/[locale]/(auth)/invitations/[token]/page.tsx`, since `d35decb`. That change recorded
a name, `NEXT_PUBLIC_INVITE_LINK_ORIGIN`, in `web/.env.example`, and said plainly that nothing read
it.

**What the admin was handed was still the API path.** The handler built `accept_path` as
`f"/api/v1/invitations/{token}/accept"` (`backend/app/application/invitation/handlers.py:65` at
`9d6ebbe`), and the schema comment beside it said "admin shares this". That route answers `POST`
only (`docs/contracts/rest-invitations-api.md:64`). A relative who opened it sent a `GET` and got
an error.

**Nothing read the field, so this was the cheapest time to change its shape.** Measured
2026-10-04: `git grep -n "accept_path" -- web/src mobile/lib` printed two comments and the
generated type. No code in either client called the create route. The admin invitation screen
(spec § 7.10c) is not built.

## Decision

### 1. The backend composes the link, and the 201 body carries it as `invite_url`

```
invite_url = <INVITE_LINK_ORIGIN>/<locale>/invitations/<token>
```

- `<token>` is the same value as the body's `token`, which stays.
- **`accept_path` is removed**, from the schema, the handler's return value, the contract and
  the tests that pinned it.
- A trailing slash on the origin does not produce a double slash.

**Composed in the route, `backend/app/api/v1/invitations.py` (`_invite_url`), not in the
handler.** The locale is request context, `app.core.locale`, and the handler could only read it
through a new `ignore_imports` entry in the ratchet "application must not import
core/services/i18n" in `backend/pyproject.toml`, which may only shrink. The handler does import
`app.core.config` already, for `INVITATION_TTL_DAYS`, through an entry the ratchet lists as debt
("config should be injected"). Reading `INVITE_LINK_ORIGIN` there would lean on that debt. The
route already holds both values, so the ratchet gains no entry. The handler returns the token.
The route turns it into a link.

### 2. The origin is the backend setting `INVITE_LINK_ORIGIN`

- It lives in `backend/app/core/config.py`, defaulting to `http://localhost:3000`, the local web
  dev server.
- **In production, boot fails when it is empty or names `localhost` or `127.0.0.1`**, the same
  way it already does for `CORS_ORIGINS` and `DATABASE_URL`. Every link built on such an origin
  is handed to a person outside the deployment and opens nothing.
- It is declared `sync: false` in `infra/render/render.yaml`. The owner sets it in the Render
  dashboard before the deploy that carries this change, or that deploy refuses to boot
  (`docs/ops/configuration.md`).
- **It is the web app's origin, never the API's.** ADR-056 and ADR-057 both warn against that
  mistake. The API answers `/<locale>/invitations/<token>` with a 404.

**`NEXT_PUBLIC_INVITE_LINK_ORIGIN` is deleted** from `web/.env.example`. Nothing read it, and
keeping it would leave a second answer to the question this setting answers.

### 3. The locale is the one the request was served in

`<locale>` is the `current_locale` that `LanguageMiddleware` sets: the first two letters of
`Accept-Language` when they name a member of `SUPPORTED_LOCALES` (`vi`, `en`, `zh`, `fr`), and
`vi` when the header is absent or names anything else. Those are the four locales the web app
routes (`web/src/i18n/routing.ts`, `localePrefix: 'always'`), so every value this can produce is
a route that exists.

The admin is the one who sent the request, so the link opens in the admin's language. A
per-invitee locale would need a field nobody stores yet.

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **Return only the token, and let each client compose the link** | Four reasons. **The contract has two consumers**, web and mobile, and the link must point at the web app whichever client created the invitation. Mobile has no way to know the web origin today, and only the backend is common to both. **The backend already holds absolute URLs for the same reason**: `PASSWORD_RESET_REDIRECT_URL` and `EMAIL_VERIFY_REDIRECT_URL` are links that leave the app through a person (ADR-063 § 4 retires those two, with #202, in favour of the Site URL, which is still a backend-side origin), and `_public_object_url` builds absolute avatar URLs from `SUPABASE_URL` (`backend/app/infrastructure/storage/supabase_adapter.py:87-96`). **It is what ADR-057's Owed item 2 says**: "so the field the admin is handed is the browser URL this ADR names". **It is checkable today, in the response body.** Client-side composition would have nothing to check until the admin screen exists |
| **Compose the link in the handler, with the origin injected** | Satisfies the ratchet too, but the locale would still have to reach the handler, through the command or a second import of request context. Both are presentation, and the route already holds both |
| **Keep `accept_path` beside `invite_url` for one release** | It had no reader, so a deprecation window protects nobody. Keeping it keeps a field whose own comment describes a use it cannot serve |
| **Name it `NEXT_PUBLIC_INVITE_LINK_ORIGIN`, the name `web/.env.example` recorded** | That name is a web build-time variable, read by the browser bundle. The value now lives on the backend, which no `NEXT_PUBLIC_` prefix describes |

## Consequences

### What this buys

- **The value an admin is handed opens the invitation page.** Read in a browser by
  `web/e2e/auth/invitation-link.auth.spec.ts`: the heading renders and the page's
  `Referrer-Policy: no-referrer` header is present.
- Web and mobile hand an admin the same link, from one setting.

### What this costs, stated plainly

- **A breaking contract change**: a field is removed. It broke nothing, because the field had no
  reader. `docs/contracts/rest-invitations-api.md` records why.
- **One more production-required setting.** A deploy that carries this change, onto a Render
  service where the owner has not set `INVITE_LINK_ORIGIN`, refuses to boot. On Render the
  previous release keeps serving.
- **The link's origin is per-deployment, not per-request.** A deployment that serves two web
  origins hands out links on one of them.

## What this ADR deliberately does not decide

- **The admin invitation screen**, spec § 7.10c. It will display `invite_url` when it is built.
- **Sending invitations by email.** Nothing in this repository does that today.
- **The accept handler and its rules**, including the email match.
- **The raw `token` in the 201 body.** It stays.
- **An invitee with no account.** That is a separate issue.
- **Mobile deep links.** The link opens the web app on every device.

## Related

- [ADR-057](057-the-invitation-link-is-the-primary-join-path.md): decided the link's shape, and
  owed this repair.
- [ADR-056](056-next-public-api-url-splits-into-a-browser-and-a-server-variable.md): owns
  `NEXT_PUBLIC_API_URL`, the reason the link origin is its own setting.
- [ADR-063](063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md): rejected composing
  its email links from this setting, to stay decoupled from #191.
- `docs/contracts/rest-invitations-api.md`: the 201 shape and the compatibility record.
- `docs/ops/configuration.md`: the setting's row and its production requirement.
