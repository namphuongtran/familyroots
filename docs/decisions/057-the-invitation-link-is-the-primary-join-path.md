# ADR-057: The Invitation Link Is the Primary Join Path, and the Clan Code Is the Secondary One

## Status

Accepted (2026-08-26), by seed **S-080**, opened by the maintainer from using the register screen.

The maintainer made the choice this ADR records. The three questions S-080 posed were put to them
on 2026-08-26 and answered: the invitation link is primary, a typed clan code survives as a
secondary path in the form of the slug, and what an admin shares is a browser URL.

Every reading below was taken on **2026-08-26** from commit `afc806a` on branch
`docs/open-s-080-to-s-084-register-join`. Where a line number is given, the claim was read at that
line and not inferred from a file name or a nearby document.

## Context

### What the form asks for today does not match what its label says

In join mode the label is `t('clan_slug')`. That key renders "Clan Code" in English
(`web/messages/en.json:184`) and "Mã dòng họ" in Vietnamese (`web/messages/vi.json:184`). The input
beside it carries `placeholder="UUID"`
(`web/src/app/[locale]/(auth)/register/page.tsx:246`), binds `clanId` (`:244`), and is submitted as
`clan_id` at `:81` and `:91`. The backend types that field `clan_id: uuid.UUID | None`
(`backend/app/schemas/auth.py:19`) and rejects a join without it
(`backend/app/application/auth/handlers.py:128-129`).

**So a person is asked to type a 36-character UUID under a label that promises a code.**

### The design spec already decided against this, and it was never built

Spec § 7.1b, at `docs/superpowers/specs/2026-08-02-design-system-and-screens.md:860-861`, gives the
join field the helper text *"Mã do quản trị dòng họ cung cấp, ví dụ: nguyen-huu-thanh-oai."* That is
a readable slug supplied by the clan admin, not a UUID. The same section, at `:868-869`, writes the
`clan_not_found` copy the code does not use: *"Không tìm thấy dòng họ với mã này. Xin kiểm tra lại
với quản trị dòng họ."*

Where the code and this spec disagree, **the code is the bug**, because the spec is a design that
was never carried out rather than a record of what shipped.

### A bare surname cannot be the identifier

`nguyen-huu-thanh-oai` is họ plus chi plus quán: surname, branch, and origin place. A surname alone
is shared by a very large share of the population, so two unrelated families collide on the first
attempt. The `clans` table already carries the columns that tell one from another, read at
`backend/app/models/clan.py`: `origin_place` (`:19`), `founded_year` (`:20`), and
`ancestral_hall_location` (`:26`). `slug` is `String(100)` and `unique=True` (`:17`).

### A searchable list of clan names is not free, and this ADR does not create one

Root `CLAUDE.md:40` forbids bypassing clan isolation, and
[ADR-044](044-privacy-toggles-dropped-from-v1.md) dropped `allow_public_tree` rather than enforce
it. There is no clan discovery endpoint. Counted 2026-08-26 from `backend/app/api/v1/clans.py`:
nine routes, at lines 46, 68, 87, 123, 161, 180, 199, 220, and 239, and **every one of them is
under `/me`**. A field that lets a stranger type "Nguyễn" and browse the matching families would be
a new public surface.

### The third path is already built, and nothing in the product reaches it

Invitations exist. The token is a `secrets.token_urlsafe(32)` value
(`docs/contracts/rest-invitations-api.md:41`), and accept verifies that the caller's email matches
the invited email, case-insensitively, or answers `invitation.email_mismatch` (`:67-68`). An invited
person types nothing at all.

**But what the admin is handed is not shareable with a human.** `accept_path` is built as
`f"/api/v1/invitations/{token}/accept"` (`backend/app/application/invitation/handlers.py:65`), and
`backend/app/schemas/invitation.py:41` comments that the admin shares it. That path answers `POST`
only (`docs/contracts/rest-invitations-api.md:64`). Pasting it into a browser is a `GET`.
`find web/src/app -ipath "*invit*"` returned nothing on 2026-08-26, so there is no page for such a
link to land on either. That gap is seed S-084.

### Two things the seed did not know, read at source while writing this ADR

Both were found on 2026-08-26 and both change what "primary" costs. Neither is a reason to reverse
the decision; both are recorded here so the next reader does not discover them as a surprise.

**1. Accept requires an authenticated caller, so the token is not self-sufficient in a browser.**
`backend/app/api/v1/invitations.py:95-99` declares the route with
`current_user: dict[str, Any] = Depends(get_current_user)`, and the handler call at `:104-105` reads
`current_user["sub"]` and `current_user.get("email", "")`. The contract's invitee table says the
same: `Auth | Yes` at `docs/contracts/rest-invitations-api.md:62`. A relative who opens the link
while signed out cannot accept it by opening it. The link must first carry them to sign in or
register, and then back to the token.

**2. A person with no clan cannot register at all, so a brand-new invitee cannot use the link
today.** `clan_action: Literal["join", "create"]` carries no default on `RegisterRequest`
(`backend/app/schemas/auth.py:18`) or on `AuthenticatedOnboardingRequest` (`:25`), so it is
required on both. `backend/app/application/auth/handlers.py:128-131` then rejects `join` without a
`clan_id` and `create` without both a `clan_name` and a `clan_slug`. An invited stranger holds a
token and has neither.

**Taken together, these two mean the invitation flow is unreachable end to end for a new user
today, and it is unreachable for a reason no seed had named.** S-084 builds the page; the page alone
does not close this. The register-without-a-clan gap is opened as seed **S-085**.

## Decision

### 1. The invitation link is the primary join path

An admin invites a relative by email. The relative opens a link in a browser and joins. That is the
path the product points at, the path the copy describes, and the path that gets built first.

**The typed clan code stays as the secondary path** and the register screen keeps offering it. It
serves the case the invitation flow cannot: a relative whose email the admin does not have, or who
finds the clan through a family member rather than an inbox.

**Nothing about clan discovery follows from this.** See "What this ADR deliberately does not
decide".

### 2. The typed identifier is the slug, not the UUID

The join field submits a **clan code** matching `_SLUG_PATTERN`
(`^[a-z0-9]+(?:-[a-z0-9]+)*$`, declared at `backend/app/schemas/auth.py:11` with its reason in the
comment above it), and the backend resolves it through the `get_clan_by_slug` lookup that already
exists at every layer: declared on the port at `backend/app/domain/auth/repository.py:31`,
implemented at `backend/app/infrastructure/persistence/auth_repository.py:47`, and already called
by the create path at `backend/app/application/auth/handlers.py:137` and `:238` to detect a taken
slug. **Nothing new has to reach the database.**

- An unknown code answers the existing **`clan_not_found`**, rendered **inline on the field**, with
  spec § 7.1b's own wording. It is not a page-level error.
- `placeholder="UUID"` is deleted.
- The helper text is spec § 7.1b's: *"Mã do quản trị dòng họ cung cấp, ví dụ:
  nguyen-huu-thanh-oai."*
- **`_SLUG_PATTERN` is reused, not re-written.** A second pattern for the same shape is a second
  place to be wrong.

**Whether `clan_id` is removed at once or accepted alongside the code for one release is not decided
here.** It is a contract question, and `docs/contracts/rest-auth-api.md` owns it. Seed S-081
decides it and writes it down there.

### 3. What an admin shares is a browser URL

The admin copies a URL a relative can open in a browser. Its shape is:

```
https://<origin>/<locale>/invitations/<token>
```

- **`<origin>` is its own configuration variable.** It is **not** `NEXT_PUBLIC_API_URL`:
  [ADR-056](056-next-public-api-url-splits-into-a-browser-and-a-server-variable.md) decided that
  name holds the browser-facing **API** origin only, and an invitation link points at the web app,
  not at the API. Introducing the new name, and documenting it where `web/` documents its
  environment, belongs to the seed that builds the page.
- **`accept_path` at `backend/app/application/invitation/handlers.py:65` is now wrong for the
  purpose its own sibling comment claims.** `backend/app/schemas/invitation.py:41` says the admin
  shares it, and after this ADR the admin does not: an API path that answers `POST` only is not
  shareable with a person. **This ADR does not change the backend.** Repairing that field, and the
  comment, is named as owed below.
- The page must handle the signed-out case, per finding 1 in Context. **How the token survives the
  round trip through sign-in is the page's decision, and the page must not leak it** — not to a
  log, an analytics call, a Sentry breadcrumb, or the `Referer` of a later request. The contract
  states the stake at `docs/contracts/rest-invitations-api.md:74`: the token "is the only thing that
  decides".
- **The email-match rule is not relaxed.** `invitation.email_mismatch` stays exactly as the
  contract has it at `docs/contracts/rest-invitations-api.md:67`. A link forwarded to a different
  person does not work, and that is the property that makes the link safe to share at all.

## Alternatives considered

| Alternative | Why it lost |
|---|---|
| **Typed clan code only, invitations left unadvertised** | The invitation flow is already built, tested, and audited (`docs/contracts/rest-invitations-api.md:70`, invitation create/accept/revoke emit auditable domain events). Leaving it unreachable keeps a built feature dead and keeps the weaker path — a person copying a string by hand — as the only door. It also does not remove the collision problem: two unrelated Nguyễn clans still need `origin_place` in the code to be told apart |
| **Invitation link only, no typed identifier at all** | Cheapest to build and the narrowest surface: S-081 and S-082 would both close as withdrawn. Rejected because it makes the admin's email list the only way into a clan. A relative the admin cannot email has no path, and the slug remains the clan's URL identifier either way, so the field is not saved by removing it from one screen |
| **A searchable list of clan names** | The register screen would let a stranger type "Nguyễn" and pick from the matching families. Rejected as a new public surface: root `CLAUDE.md:40` forbids bypassing clan isolation, and ADR-044 dropped `allow_public_tree` rather than enforce it. It is not merely more work — it is a privacy decision against a standing one, and it would need its own ADR |
| **Keep the UUID and fix only the label** | Honest, and one edit. Rejected because it makes the screen worse in the direction the maintainer complained about: the label would stop promising a code and would start promising a UUID, which nobody can be asked to type. Spec § 7.1b already decided the field is a code |

## Consequences

### What this buys

- **The register screen's label stops lying.** The field asks for the code its label names.
- **The invitation flow becomes reachable by a human**, which it has never been.
- **The lookup already exists**, so the backend half of the secondary path (seed S-081) is small.
- **No new public surface.** No route lets a stranger enumerate clans.

### What this costs, stated plainly

- **Two public routes change shape.** `POST /auth/register` and `POST /auth/onboard` accept a code
  where they accepted a UUID. `docs/contracts/rest-auth-api.md` moves in the same pull request as
  the code, per root `CLAUDE.md`. Seed S-081 owns it.
- **The invitation link cannot work end to end until seed S-085 lands.** Findings 1 and 2 in
  Context are the reason. A page built against the token is necessary and not sufficient.
- **`accept_path` and its comment are now wrong** and are not fixed here. Owed below.
- **This ADR is documentation only and no gate ran.** Nothing in it is verified by a test, because
  nothing in it is code. Saying so is the requirement, per `.claude/rules/seeds.md`.

### Owed, named rather than left to be found

1. **Seed S-085: let a person register with no clan, so an invitee can create an account.** Finding
   2 in Context. Backend, and it changes `RegisterRequest`, `AuthenticatedOnboardingRequest`, the
   handler validation at `backend/app/application/auth/handlers.py:128-131`, and
   `docs/contracts/rest-auth-api.md`.
2. **Repair `accept_path` and the comment at `backend/app/schemas/invitation.py:41`** so the field
   the admin is handed is the browser URL this ADR names. It becomes actionable once the page exists
   and the origin variable has a name. Recorded in `docs/SEEDS.md`.

## What this ADR deliberately does not decide

- **Public clan discovery or search.** Out of scope, and it would need its own ADR against
  [ADR-044](044-privacy-toggles-dropped-from-v1.md). **Do not read a clan directory into this
  document.** Nothing here creates a route that answers "which clans exist".
- **Whether `clan_id` is dropped at once or deprecated over one release.** Seed S-081 decides it in
  `docs/contracts/rest-auth-api.md`.
- **The name of the web-origin configuration variable.** Only that it is not
  `NEXT_PUBLIC_API_URL`.
- **Renaming a clan's code after creation.** Spec § 9 covers it under clan settings, at
  `docs/superpowers/specs/2026-08-02-design-system-and-screens.md:1771-1772`, and what it says is
  narrower than "invite links break": existing invite links and join codes **keep working**, and
  what changes is "the code people quote". Read it there before designing a rename. Untouched
  here.
- **The RBAC matrix.** An invitation carries a role already; nothing about which roles exist
  changes.
- **The mobile register screen, which does not exist.** Listed 2026-08-26,
  `mobile/lib/features/auth/presentation/` holds `login_page`, `verify_email_page`,
  `pending_approval_page`, `blocked_page`, and `message_page` only.

## Related

- Seed **S-080** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seeds **S-081**,
  **S-082**, **S-083**, and **S-084**, which it unblocks.
- [ADR-056](056-next-public-api-url-splits-into-a-browser-and-a-server-variable.md) — owns
  `NEXT_PUBLIC_API_URL`, and the reason the link origin cannot reuse that name.
- [ADR-044](044-privacy-toggles-dropped-from-v1.md) — dropped the privacy toggles, and the standing
  decision that public clan discovery would have to argue against.
- [ADR-048](048-invitation-accept-runs-on-the-system-session.md) — why accept runs on the system
  session, and what that costs at the database layer.
- Spec § 7.1b, `docs/superpowers/specs/2026-08-02-design-system-and-screens.md:854-871` — the
  design this ADR finally carries out.
- `docs/contracts/rest-invitations-api.md` and `docs/contracts/rest-auth-api.md` — the two contracts
  the follow-on seeds move.
