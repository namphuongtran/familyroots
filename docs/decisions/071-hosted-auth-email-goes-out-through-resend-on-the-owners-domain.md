# ADR-071: Hosted Auth Email Goes Out Through Resend on the Owner's Domain

## Status

Accepted (2026-10-18). Configured the same day. Resolves the decision in issue #276, "Send hosted
auth email through a custom SMTP sender on the owner's domain". **#276's outcome check passed the
same day**: #203's recovery email came from `noreply@getnami.dev` and is in Resend's email log, as
the owner reported. A sign-up from a mailbox outside the team was not tried, because the web's
sign-up flow has open defects of its own. The procedure and the reading are in
`docs/ops/supabase-hosted-project.md` § 4d.

## Context

**On 2026-10-11 the template push of #203 was refused.** CLI 2.120.0, `config push --workdir
supabase --project-ref xkmutzxdhdigyfisfrwd`, answered:

```
unexpected status 400: {"message":"Email template modification is not available for free tier projects using the default email provider. Please upgrade your plan or configure a custom SMTP provider."}
```

**A plan upgrade alone would not have helped.** Supabase's default email provider delivers only to
members of the project's team, at most 2 emails an hour
([auth-smtp docs](https://supabase.com/docs/guides/auth/auth-smtp),
[changelog, 2024-09-26](https://supabase.com/changelog/29370-supabase-auth-changes-to-default-email-provider)).
With Confirm email on, a person outside the team could not finish signing up on any plan.

ADR-015 lists "SMTP configured" as an ops prerequisite of its verification flow. ADR-063 left the
sender undecided ("What this ADR deliberately does not decide").

## Decision

### 1. Supabase Auth sends through Resend's SMTP

The hosted project's custom SMTP points at Resend: host `smtp.resend.com`, port `465`, username
`resend`, and a Resend API key with sending access as the password. Supabase still composes every
auth email from its templates. Resend only carries it.

**The application sends no email of its own.** The backend reaches mail only through Supabase Auth:
`send_password_reset` calls `reset_password_email`, and `send_verification_email` calls ADR-015's
`resend` with type `signup` (`backend/app/infrastructure/supabase_identity_provider.py:166-176`,
read 2026-10-18). So no app setting, Vercel variable or GitHub secret names Resend.

### 2. The sender is a `noreply@` address on a domain the owner holds

The domain is named in the ops doc, not here. On 2026-10-18 it is `getnami.dev`, and the sender is
`noreply@getnami.dev`. **Changing the domain is an ops change, recorded in
`docs/ops/supabase-hosted-project.md` § 4d. Changing the provider needs a new ADR.**

No mailbox stands behind the address. Resend sends from any address on a verified domain, and
`getnami.dev` publishes no MX record at its apex (read 2026-10-18), so a reply bounces.

### 3. The API key lives in two places only

It lives in Resend, where it was created, and in the Supabase dashboard's SMTP Settings, where it
is used. It never enters the repository. `supabase config pull` reads every SMTP field back except
the password, so a read-back cannot leak it.

### 4. The DNS records live at the domain's DNS host, not in the repository

`getnami.dev`'s nameservers are Cloudflare's. Resend's records sit there: DKIM at
`resend._domainkey`, and a CNAME at `send` that carries the bounce MX and the SPF record. Pulumi's
resources are stubs, so nothing in the repository manages them. The ops doc records how to read
them back.

## Consequences

- **#203 is no longer blocked by the provider.** The 400 named only the default provider.
- **Auth email no longer depends on team membership.** Any address can receive confirmation and
  recovery email, once the templates and the web pages carry it through.
- **A third-party account joins the production path.** If the Resend account, its key, or the domain
  lapses, every auth email stops, silently: ADR-015 sends best-effort and never fails a
  registration on a mail error. Resend's own email log is the first place to look.
- **The sending domain differs from the web's host.** Mail comes from `getnami.dev` while links
  point at `familyroots-web.vercel.app`. That was accepted for now. A custom web domain would let
  the two match.
- **A new domain carries no sending reputation.** Early mail may land in spam folders.
- **Supabase's hosted email rate limit applies on top.** Read 2026-10-18 as 30 emails an hour
  (`auth.rate_limit.email_sent`).

## Alternatives considered

| Alternative | Why not |
|---|---|
| Upgrade the Supabase plan and keep the default provider | Unlocks template edits but still delivers only to team members |
| Gmail SMTP with an app password | Ties production auth email to a personal account, sends from `@gmail.com`, and is subject to Google's sending limits |
| Another transactional provider (SES, Postmark, Brevo) | Not compared in depth. #276 recommended Resend, and the owner chose it on 2026-10-18 |

## Verification

Read 2026-10-18, before this ADR merged:

- **The hosted project holds the SMTP settings.** `npx --yes supabase@2.120.0 config pull --workdir
  <scratch dir> --project-ref xkmutzxdhdigyfisfrwd --dry-run`, which writes nothing: `smtp.enabled`
  `true`, `host` `smtp.resend.com`, `port` `465`, `user` `resend`, `admin_email`
  `noreply@getnami.dev`, `sender_name` `Familyroots`. The password is the one field it does not
  return.
- **The DNS records are published.** `dig @galilea.ns.cloudflare.com` read a TXT at
  `resend._domainkey.getnami.dev` (`p=MIGfMA0…`), a CNAME from `send.getnami.dev` to
  `send.forge.rmta.net` (which carries `MX 10 feedback.forge.rmta.net` and
  `v=spf1 ip4:52.3.252.119 ip4:44.222.39.36 ip4:199.249.231.0/24 ~all`), and a DMARC record
  `v=DMARC1; p=none;`. Resend showed the domain as verified (the owner's report).
- **Read 2026-10-18: an email leaves through Resend.** #203's recovery email came from
  `noreply@getnami.dev` and is in Resend's email log (the owner's report). That is #276's outcome
  check.

## Related

- [ADR-015: Email Verification via Admin-Create-Unconfirmed + Best-Effort Resend](015-email-verification-flow.md):
  its "SMTP configured" prerequisite is met by this ADR.
- [ADR-063: Auth Email Links Land as a `token_hash` on a Page of Ours](063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md):
  the sender it left undecided is decided here.
- `docs/ops/supabase-hosted-project.md` § 4d: the configuration, its read-back, and how to change
  the domain or rotate the key.
- Issue #203: the template push this unblocks.
