# ADR-067: Production Ships on a Published Release, Not on a Merge to `main`

## Status

Accepted, shipped (2026-10-10). Resolves issue #267, "Production deploys on a published release,
not on every merge to main".

The maintainer took the decision on 2026-10-10: a merge to `main` runs CI and deploys nothing.
Production moves only when a GitHub Release named `vX.Y.Z` is published, and only after the
maintainer approves the run. Staging was considered and deferred to its own issue. This ADR ships
with the workflow change, in the same pull request. Source readings were taken at `a6c7124` on
`main` on 2026-10-10.

It amends the pipeline that #252 set. ADR-065 and ADR-066 are unchanged, and so is the order of the
deploy steps.

## Context

Until this change, two workflows each deployed to production on every push to `main` that matched
their path filters:

- `backend-ci.yml`'s `deploy` job ran for any push touching `backend/**`, `infra/**`, `scripts/**`,
  `supabase/**` or `docs/ops/migrations.md`. It migrated the production database, ran
  `vercel deploy --prod`, then read `/health`.
- `web-ci.yml`'s `deploy` job ran for any push touching `web/**` or `backend/app/**`, and ran
  `vercel deploy --prod`.

Four readings made that costly here:

1. **Hobby's Instant Rollback reaches only the immediately previous deployment**
   (`docs/ops/deployment.md`, "Rollback"). With a deploy per merge, the previous deployment is one
   pull request back, not the last version anyone chose to ship.
2. **Every deploy that carries a migration opens a cold-start window.** In that window the old
   deployment cannot boot against the migrated database (#255). More deploys means more windows.
3. **The two deploys did not know about each other.** A web build could go live before the API it
   calls, or while the API's own deploy was failing its health read.
4. **`main` has no branch protection**, so a green `main` was not a given. On 2026-10-10 the merges
   of #259, #260 and #262 each went live, and each run concluded `failure`
   (`gh run list --workflow backend-ci.yml --branch main --limit 8`, run 2026-10-10).

## Decision

### 1. A merge to `main` deploys nothing

The `deploy` jobs leave `backend-ci.yml` and `web-ci.yml`. Both workflows gain `on: workflow_call`
and keep every gate they ran before. Their push and pull-request triggers and path filters are
unchanged.

### 2. A published release runs one ordered workflow

`.github/workflows/release.yml` runs on `release: published`, and on `workflow_dispatch`
dispatched on a tag, which is how a release is re-run. Its jobs run in this order:

1. **`verify-ref`** refuses a run on a branch, a tag not named `v[0-9]*`, or a tagged commit that
   is not an ancestor of `origin/main`. Only code that reached `main` through a pull request ships.
   A pre-release skips the whole workflow.
2. **`backend-gate` and `web-gate`** call the two CI workflows on the tagged commit, in parallel.
   Path filters do not apply to `workflow_call`, so both gates run in full whatever the release
   touched.
3. **`deploy`** names `environment: production` and runs in concurrency group `production-release`
   without cancel-in-progress. It runs the steps the two old deploy jobs ran, in this order:
   migrate, deploy `familyroots-api`, read `/health` on the production host, deploy
   `familyroots-web`.

**One job, not two.** Each job that names an environment with a required reviewer waits for its
own approval. The web deploy must follow the backend's health read, so two jobs would mean two
approvals per release.

**The web deploys last.** A red health read stops the job before the web deploy, so the web never
goes live against an API that failed its read.

**Missing configuration fails the release.** The old jobs skipped green with a `::warning::` when
a secret was unset, so that `main` stayed green before go-live. A release that deploys nothing
must not look like one that shipped.

### 3. The `production` environment is the approval gate

The repository is public, so GitHub environments with required reviewers cost nothing. The
environment has:
- **Required reviewer:** the maintainer.
- **Deployment policy:** tags matching `v*` only.

Creating it, and moving the deploy secrets into it, are owner actions, listed in
`docs/ops/deployment.md` under "Go-live checklist", B. **Until the environment exists, GitHub
creates it on first use with no protection rules.** The first release would then deploy without
waiting, so create the environment before publishing one.

### 4. Releases are versioned as one SemVer tag

- **One tag covers backend and web**, because they ship together. Both packages read `0.1.0`, so
  the first release is `v0.2.0`. The tag is the version, and neither package file is bumped.
- **Mobile versions separately**, through its store builds.
- **A hotfix is a pull request to `main`, then a patch release.** Nothing ships from a branch.

### 5. A backend release must not remove what the live web still reads

The backend and web deploy one after the other, not atomically. For the minutes between the two,
the new API serves the old web. A change that removes or renames a field, route or behaviour the
web uses ships in two releases:
1. The first release makes the web stop using it.
2. A later release removes it from the API.

Migrations already follow the same rule: "Keep every migration compatible with the code already
live" (`docs/ops/migrations.md`, "How migrations reach production").

## Consequences

- **Rolling back goes to the previous release.** Under Hobby's previous-deployment-only rule, that
  is now the last version someone chose to ship.
- **Fewer migration windows (#255).** A release that batches several merged migrations opens one
  window, not one per merge. The window itself is unchanged.
- **Every release re-runs the full backend and web gates** on the tagged commit, which adds their
  runtime (several minutes) before the approval.
- **Merged work waits for a release.** Nothing reaches users until someone publishes a release, so
  a fix needs one too.
- **The deploy secrets can be scoped to the environment**, so only an approved release job can read
  them. `db-backup.yml` reads its own three secrets and keeps them at repository level.
- **Vercel Cron is unaffected.** It runs against whichever deployment is production.

## Alternatives considered

- **A `workflow_dispatch` button that takes a commit SHA.** It is simpler, but it leaves no version
  name and no release notes, and rollback targets are SHAs.
- **A scheduled deploy of `main`'s tip.** It needs no human step, but a bad merge still ships
  unattended.
- **Staging first, then promote on a tag.** It is safer, but it needs a second Supabase project,
  Preview variables on both Vercel projects, and a second go-live checklist. It is deferred to its
  own issue, not rejected.
- **Two deploy jobs, backend then web, each in `production`.** It means two approvals per release
  (§ 2).

## Verification

- **actionlint.** `actionlint` 1.7.12 with ShellCheck 0.11.0 reports 0 errors on `release.yml`,
  `backend-ci.yml` and `web-ci.yml`.
  - Three defects planted in a copy are each reported: `needs:` naming a job that does not exist, a
    `uses:` pointing at a workflow file that does not exist, and an unquoted `$url`.
  - With `workflow_call:` removed from a copy of `backend-ci.yml`, actionlint reports
    `"workflow_call" event trigger is not found`.
- **The ref check.** The `verify-ref` script, extracted from `release.yml` with PyYAML and run in a
  scratch clone on 2026-10-10:
  - It exits 0 for a `v9.9.9` tag on `main`'s tip `a6c7124`.
  - It exits 1 for each of three refusals: a `v9.9.8` tag on `b016420`
    (`prototype/backoffice-shell-320`, not on `main`), a tag named `release-1`, and the branch
    `main`.
- **Live, after merge.** The merge commit's `backend-ci` and `web-ci` runs show no deploy job. The
  first release waits for approval, then migrates, deploys, reads `/health` 200 with
  `"migrations":"current"`, and deploys the web.

## Related

- #252: the pipeline this amends. #255: the migration cold-start window, which this narrows but
  does not close.
- ADR-065, ADR-066.
- `docs/ops/deployment.md`: "Pipeline", "Cutting a release", "Rollback", "Go-live checklist".
