# Operations Index

This folder captures the operational knowledge needed to run and support FamilyRoots.

## Runbooks
- [deployment.md](deployment.md)
- [migrations.md](migrations.md)
- [configuration.md](configuration.md)
- [secrets.md](secrets.md)
- [monitoring.md](monitoring.md)
- [incident-response.md](incident-response.md)
- [backup-restore.md](backup-restore.md) — ACTIVE since 2026-07-12: nightly GitHub Actions backup to Supabase Storage + a real drilled restore; go-live checklist for the 3 secrets still pending
- [local-supabase.md](local-supabase.md): the local auth + Storage stack (2026-08-22): how to start and stop it, what it costs, which services are off, and the `SUPABASE_URL` value that `supabase status` gets wrong
- [seed-test-users.md](seed-test-users.md): `make seed` (2026-08-22) — one command that puts an admin, an editor, a viewer and an outsider into BOTH databases, and how it names a half that is missing instead of leaving a user who logs in and can reach nothing

## Usage
- Use these docs when planning deploys, rotating secrets, running migrations, or responding to incidents.
- Keep them aligned with current CI/CD, Render, Vercel, Supabase, and Pulumi behavior.
