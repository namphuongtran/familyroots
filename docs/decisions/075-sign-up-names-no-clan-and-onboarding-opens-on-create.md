# ADR-075: Sign-Up Names No Clan, the Clan Step Is Onboarding, and Onboarding Opens on Create

## Status

Accepted (2026-10-24), resolving issue #291, "Sign-up asks for a clan code before an account
exists, and production has no clan to join". The owner made both choices on 2026-10-24: the clan
step moves after sign-in, and it opens on **create**.

**This ADR ships web code only.** `POST /auth/register` and `POST /auth/onboard` accept what they
accepted before, so no contract shape changes. It amends the amendment to
[ADR-058](058-registration-may-name-no-clan.md) § 2 (2026-10-06, #196), which had the web send
the clanless body "from one entry only".

Readings were taken on branch `fix/291-clanless-sign-up`, based on `main` at `4307bf6`.

## Context

**On 2026-10-18 the owner reported** that a new sign-up "has to enter a clan code, which isn't
reasonable yet". The same day, `supabase db query --linked` read `clans 0` and `auth_users 0` on
production (issue #291).

**The register form could not succeed on its default path.** Read on `main` at `4307bf6`:

- `web/src/features/auth/ui/RegisterScreen.tsx:57` opened the choice on join,
  `useState<'join' | 'create'>('join')`.
- The code field was `required` (`:361`), and its shape was checked before sending (`:132`).
- Only `?from=invitation` sent no `clan_action` (#196).

With no clan in the database, every code answered `clan_not_found`, which the form shows as "Không
tìm thấy dòng họ với mã này".

**A clanless account already had a clan step, after sign-in.** `accessStateOf` gives a signed-in
person with no membership `needs-onboarding` (`web/src/domain/session/access-state.ts`), and
`landingPath` sends that state to `/register?mode=oauth` (`web/src/features/auth/model/landing.ts:14`).
That is the same form a first-time Google user reaches (#290). Its copy opened on "Bạn đã đăng
nhập bằng Google", which every person in that state read, a password sign-up included.

**Create at sign-up created the clan before the email was confirmed.** `AuthCommandHandler.register`
(`backend/app/application/auth/handlers.py:271`) calls `create_user` at `:328`, writes the clan and
its admin membership through `_assign_clan_membership` at `:355`, and only then sends the
verification email at `:376`. So a person could claim a clan code with an address they do not
control, and the claim stood whether or not the address was ever confirmed.

## Decision

### 1. The web's sign-up form names no clan, for anyone

`RegisterScreen` sends `POST /auth/register` with `email`, `password` and `full_name` and nothing
else, reached from an invitation or not. That is the body ADR-058 § 1 made the invitee's. The form
says the clan comes after sign-in (`auth.register_clan_after_sign_in`), on the form and again on
the success screen.

The invitation marker (`?from=invitation`, #196) now decides only the copy. The invitee is still
told to open the link again after signing in, because their membership arrives from accept.

### 2. The clan step is onboarding, for every signed-in person with no clan

There is one clan step: `/{locale}/register?mode=oauth`, `POST /auth/onboard`. A password sign-up
reaches it after confirming and signing in, and a Google user reaches it after the callback. The
URL keeps its old `mode=oauth` name, because `landingPath` and every link to it already use it. The
screen names no sign-in provider: `auth.oauth_onboarding_subtitle` now reads "Tài khoản của bạn đã
sẵn sàng. Hãy tạo dòng họ mới, hoặc tham gia dòng họ bằng mã do quản trị dòng họ cung cấp."

### 3. Onboarding opens on create, and lists it first

**Tạo dòng họ mới** is chosen when the form opens and is the first option. **Tham gia dòng họ** is
one choice away and unchanged: the same code field, helper, shape check and inline
`clan_not_found`. A person with no invitation has no code to type. Joining by code is the
secondary path [ADR-057](057-the-invitation-link-is-the-primary-join-path.md) made it, and the
invitation link stays the primary one.

### 4. The backend does not change

`RegisterRequest.clan_action` stays optional (ADR-058 § 1), with the "clan named, no action" refusal
(§ 2). `AuthenticatedOnboardingRequest.clan_action` stays required (§ 3). So `POST /auth/register`
still accepts `join` and `create` from any client. No shipped client sends them now: the web sends
neither, and `mobile/lib` has no register caller.

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **Keep the clan step in sign-up, opening on create** | The smaller change, and the issue's option 2. It still creates a clan, and claims its code, for an address nobody has confirmed. It also keeps two clan steps, one at sign-up for a password and one after sign-in for Google, each to be kept in step with the other |
| **Open the clan step on neither, and show no field until one is chosen** | Favours no path. It costs every person one more choice, and the owner chose create |
| **Search for a clan by name** | Ruled out by ADR-057, which refused a searchable list of clan names as a new public surface, against [ADR-044](044-privacy-toggles-dropped-from-v1.md)'s dropping of `allow_public_tree`. Choosing it would reopen both |
| **Refuse `clan_action` on `POST /auth/register` in the backend too** | It would close the pre-confirmation clan claim for every caller, not only the web. But it is a breaking request change on a non-enumerating route, and #291 does not need it to reach its end state. It is left to its own decision (see "What this does not decide") |

## Consequences

### What this buys

- **A person with no invitation and no code can finish sign-up.** They name no clan, confirm,
  sign in, and create one on a form that opens on create.
- **One clan step for everyone.** A password sign-up and a Google sign-in meet the same form, and
  the form names no provider.
- **The web no longer creates a clan for an unconfirmed address.** The clan is created by
  `POST /auth/onboard`, which needs a signed-in caller, and sign-in needs a confirmed email.

### What this costs, stated plainly

- **A person who holds a code meets one more screen.** They sign up, confirm, sign in, and only then
  type the code.
- **The onboarding form asks for the name again.** `GET /auth/me` answers `full_name` out of the
  token's `user_metadata`, which `POST /auth/register` never sets. The name typed at sign-up sits in
  `user_profiles.display_name` (ADR-058 § 7), and nothing on the auth path reads it. Measured
  2026-10-24 on the walk below: `full_name: ""` against `display_name` 'Người Đăng Ký 291'. The
  field is required, so the person types their name a second time. This is older than #291, but
  #291 puts every password sign-up in front of it. #300 holds the backend fix. *(Fixed on
  2026-10-24 by [ADR-076](076-the-name-typed-at-sign-up-is-the-providers-full-name.md): register
  now writes the typed name to the provider, and the form opens filled.)*
- **An invitee who signs in before reopening the link lands on onboarding too**, which now offers to
  create a clan. That was already so under ADR-058. The invitee's success screen still says to open
  the link again.
- **Spec § 7.1b's join/create choice moves.** The spec put it on the register screen. It is § 7.2a's
  onboarding variant now, which already reused it. The spec carries a note saying so.

## What this deliberately does not decide

- **Whether `POST /auth/register` keeps accepting `clan_action`.** Any client can still create a
  clan at sign-up through the API, before the address is confirmed. Closing that is a backend
  change with its own breaking-change and non-enumeration questions.
- **Which store holds a person's name.** That is the issue named under "What this costs".
  [ADR-076](076-the-name-typed-at-sign-up-is-the-providers-full-name.md) decides it.
- **A mobile register screen.** Mobile has none.

## How it is held

- `web/src/features/auth/ui/RegisterScreen.invitee.test.tsx` reads the body `POST /auth/register`
  receives, through the real actions and repository against MSW, with and without the marker:
  exactly `email`, `password` and `full_name`. Before the fix, the case without the marker failed
  because the form stayed on screen and sent nothing.
- `web/src/features/auth/ui/RegisterScreen.onboarding.test.tsx` reads the body `POST /auth/onboard`
  receives. The form opens on create, a clan name alone sends `clan_action: 'create'` with the
  derived code, and join sends the code it was given. It also reads that the screen names no
  provider in all four locales. Each case failed before its fix: create was not checked, and every
  locale held "Google".
- `web/e2e/register-clan-code.spec.ts` and `register-join-code.spec.ts` measure the clan fields in
  Chromium where they now live, on `/vi/register?mode=oauth`, with a seeded session
  (`web/e2e/seeded-session.ts`). The 320 px and 200% readings carry over unchanged.
- `web/e2e/auth/signs-up-with-no-invitation.auth.spec.ts` is the issue's reading, against the local
  stack. A person registers with no invitation, confirms by the mailed link, signs in, lands on
  onboarding opening on create, creates a clan from its name, and lands on `/vi/dashboard`.
  `GET /me/clans` then holds one approved `admin` membership in that clan. It passed on 2026-10-24,
  spending 2 counted requests of 5 under `/api/v1/auth`. Each control below was seen to fail on
  2026-10-24:

| Plant | Reading |
|---|---|
| `RegisterScreen.tsx` put back to `origin/main` | failed at the first step: `sign-up offers a join/create choice`, `getByRole('radio')`, `Expected: 0`, `Received: 2` |
| the same, with the first step's three readings taken out | failed on the outcome: the required code field kept the submit in the browser, and `getByText('Nếu email hợp lệ, …')` was not found in 45 s |
| onboarding's default put back to join | failed at sign-in's landing: `getByRole('radio', { name: 'Tạo dòng họ mới' })`, `Expected: checked`, `Received: unchecked` |

  **The stop the issue names was read too**, by a throwaway probe on the old form, deleted after: a
  code no clan holds, `khong-co-dong-ho-291`, showed "Không tìm thấy dòng họ với mã này. Xin kiểm
  tra lại với quản trị dòng họ." The walk ran on the seeded local database, not an empty one. It
  types no code, so the clans already there do not change what it reads. **The issue's end state
  names the hosted site.** That reading waits for a release, because a merge to `main` deploys
  nothing (ADR-067).

## Related

- [ADR-058](058-registration-may-name-no-clan.md): registration may name no clan. This ADR extends
  its § 1 body to every web sign-up, and leaves its § 3 alone.
- [ADR-057](057-the-invitation-link-is-the-primary-join-path.md): the invitation link is the
  primary join path, and a code the secondary one.
- [ADR-044](044-privacy-toggles-dropped-from-v1.md): dropped the privacy toggles, the standing decision ADR-057 cites against a clan directory.
- `docs/contracts/rest-auth-api.md`, "Registering with no clan".
