# ADR-068: `next dev` Carries a Patch That Serializes Its Route Watcher

## Status

Accepted, shipped (2026-10-11). Resolves issue #228, "invitation-accept.spec.ts once served Next's
own 404 for every case in a full e2e run".

The maintainer chose the form on 2026-10-11, from three: a pnpm patch of Next, a harness-only
preload, or recording the cause with no fix. This ADR ships with the patch, in the same pull
request. Sources were read in Next 16.2.12, the version `web/pnpm-lock.yaml` pins, and in the
16.4.0 (`latest`) and 16.5.0-canary.7 (`canary`) tarballs from npm, on 2026-10-11.

## Context

On 2026-10-05 a full `pnpm test:e2e` failed all 20 cases of `e2e/invitation-accept.spec.ts`, in
both projects, each on Next's own 404 page. Every other spec passed, and the next run passed.
#228 asked for a bounded reproduction.

**The cause is a race in `next dev`'s route watcher, and it is not this app's code.** In
`next/dist/server/lib/router-utils/setup-dev-bundler.js` (16.2.12):

- Watchpack watches the project with `aggregateTimeout: 5` (`:289`), so it fires `aggregated` each
  time its startup scan pauses for 5 ms. One startup fired it 3 to 9 times, tens of milliseconds
  apart, each time with more of the tree.
- The listener is `async` and nothing serializes it (`:301`). Each run reads the file list when it
  starts (`:307`), clears and refills the router's shared sets (`:324`), and only after about a
  dozen `await`s writes the dynamic route list (`opts.fsChecker.dynamicRoutes`, `:729`).
- **So the last run to write wins, not the run that saw the most.** A run that started on a partial
  scan can finish after the run that saw every file, and overwrite the complete list with its
  partial one. Nothing runs the listener again until a watched file changes, so any route the
  partial list lacked answers 404 for the life of the server.

**Why only that spec.** The scan reaches the deepest directories last. The routes a partial list
drops are the pages four or more directories below `src/app`, 8 of the 28 entries in the complete
route list:
`(auth)/invitations/[token]`, `(auth)/auth/callback`, `(auth)/verify-email/confirm`, and five under
`(dashboard)/members` and `(dashboard)/admin`. The hermetic e2e projects request only one of those,
the invitation page.

**Upstream has not fixed it.** 16.4.0 and 16.5.0-canary.7 carry the same listener (`:341`), the
same snapshot (`:348`) and the same write (`:912`), with eleven `await`s between them.

### Readings, 2026-10-10 and 2026-10-11

A probe preload logged each listener run's start, end and file count, and each write of the route
list. It was loaded through `NODE_OPTIONS` and edited no file on disk. One startup of the banner
server, on 3201:

```
14:26:44.854 ASSIGN dynamicRoutes routes=28 invitationRoute=true
14:26:47.452 ASSIGN dynamicRoutes routes=20 invitationRoute=false
```

The second write came from a run that had started on a scan holding 17 of the 25 page files under
`src/app/[locale]`. It landed 2.6 s after the complete one.

Startups of the e2e server pair, 3200 and the banner server on 3201. "At once" starts both
together. "In order" starts 3201 once 3200 answers, which is what Playwright's `webServer` array
does: in runs 1 and 2 of #228, 3101 started about 16 s after 3100. Each server was asked for
`/vi/invitations/abc` six seconds after it first answered `/`:

| Next | Command, order | Where | Servers stuck on 404 |
|---|---|---|---|
| 16.2.12 as published | `next dev`, at once, probe loaded | a second worktree | 8 of 12 |
| 16.2.12 as published | `next dev`, at once, probe loaded | the primary checkout | 3 of 8 |
| 16.2.12 as published | `next dev`, at once | a second worktree | 6 of 8 |
| 16.2.12 as published | `next dev`, in order | a second worktree | 7 of 12 |
| 16.2.12 as published | `pnpm dev`, in order, as Playwright runs it | a second worktree | 3200: 0 of 6. 3201: 3 of 6 |
| 16.2.12, listener serialized by the probe | `next dev`, at once, probe loaded | a second worktree | 0 of 16 |
| 16.2.12, this patch before review added the catch (below) | `next dev`, at once, probe loaded and not | the primary checkout | 0 of 24 |
| 16.2.12, this patch before review added the catch | `pnpm dev`, in order | the primary checkout | 0 of 12 |
| **16.2.12 with this patch** | **`next dev`, at once, probe loaded** | **the primary checkout** | **0 of 12** |

In every probed startup, a 404 matched a last write without the route and a 200 matched a last
write with it. Three patched servers did not answer within curl's 60 s, each on the first startups
after an install that changed the patch. All three had matched the route and were compiling it
cold (Consequences, last item), and none was a 404. Touching `src/app/[locale]/(auth)/login/page.tsx`
on a stuck server turned the invitation route from 404 to 200 within 3 s, on 2 of 2 servers. On a server that came up stuck, `pnpm test:e2e e2e/invitation-accept.spec.ts` read
**22 failed**, and all 22 page snapshots were `heading "404"` and `This page could not be found.`,
the 2026-10-05 shape. The spec has 11 cases per project now, where it had 10 then. **Negative
control, 2026-10-11:** with the patch taken out of the primary checkout, the first startup came up
stuck: its log shows all 23 invitation requests answered 404, none after a `○ Compiling` line, and
the spec read the same 22 of 22. With the patch back, none of 48 servers came up stuck, in either
order, across both versions of the patch.

**Why a full run shows it rarely.** Started the way Playwright starts it, the server the hermetic
specs use came up stuck in none of six startups, and the banner server in three. No hermetic spec
asks the banner server for a deep route. So a full run fails only when 3100 itself loses the race,
as it did on 2026-10-05. That last step is inferred: the 2026-10-05 shape matches a stuck server
exactly, but a stuck 3100 was not seen in Playwright's order in six startups. #228 records each full
run.

## Decision

**`web/patches/next@16.2.12.patch` serializes the listener and re-runs it once if events arrived
while it ran.** The body moves into `onAggregated`, unchanged. The listener runs it, and an event
that arrives meanwhile sets a flag that asks for one more run. That run reads the file list
afresh, so the last write always comes from the latest scan:

```js
let aggregating = false;
let aggregateAgain = false;
wp.on('aggregated', async ()=>{
    if (aggregating) { aggregateAgain = true; return; }
    aggregating = true;
    try {
        do {
            aggregateAgain = false;
            try { await onAggregated(); }
            catch (err) { if (!aggregateAgain) throw err; _log.error(err); }
        } while (aggregateAgain);
    } finally { aggregating = false; }
});
```

**A run that throws keeps its old visibility and does not cancel a queued re-run.** Unpatched, a
throwing run was an unhandled rejection, which `next dev` logs and survives (`router-server.js:595`
to `:602`), and the next event ran as usual. Patched, the error still surfaces: rethrown when no
re-run is queued, logged with the same `_log.error` when one is, and the re-run goes ahead.

Review found the need for that catch, and a plant measured it. The plant made the first run touch a
page file, so that an event queued a re-run, then throw. Before the catch, the queued re-run was
dropped, the startup promise that only a finished run resolves never resolved, and the server never
answered `/`, in 1 of 1 startup. With the catch, the error was logged as
`⨯ Error: planted 228 throw`, the re-run wrote all 28 routes, and the invitation route answered
200, in 2 of 2.

Each serialized server wrote the route list once or twice, and the last write always came from
the complete scan. No startup hung, in 64 serialized starts.

**`web/pnpm-workspace.yaml` names the patch, not `package.json`.** pnpm 10.6.0 reads a fixed list
of keys from `package.json`'s `pnpm` field (`getOptionsFromRootManifest`, read in pnpm 10.6.0's
`dist/pnpm.cjs` on 2026-10-11), and `patchedDependencies` is not on it. `pnpm patch-commit` wrote
it there anyway. The next `pnpm install` dropped the patch from the lockfile and put the unpatched
Next back, and `pnpm install --frozen-lockfile` failed with `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`.
From `pnpm-workspace.yaml`, both installs apply the patch.

**`web/Dockerfile` copies `pnpm-workspace.yaml` and `patches/` into the deps stage.** It copied only
`package.json` and `pnpm-lock.yaml` before its frozen install. Measured by running that stage's
install in a scratch directory: with the old copy it fails with `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`,
and with the new one it installs, with the patch in `node_modules/next`.

## Consequences

- **Production is untouched.** `router-server.js` requires `setup-dev-bundler` only inside
  `if (opts.dev)` (`:127`, `:135`), so `next build`, `next start` and the standalone image never
  load the patched file.
- **Every `next dev` gets the fix**: a developer's `pnpm dev`, local e2e, and CI's e2e jobs.
- **A Next bump fails until the patch is redone.** With `next` moved to 16.4.0 in a scratch copy,
  `pnpm install` stopped with `ERR_PNPM_PATCH_NOT_APPLIED  The following patches were not applied:
  next@16.2.12`. Upstream still has the race as of 16.5.0-canary.7, so redo the patch against the
  new version, then repeat the startup reading above, unpatched and patched. If upstream has fixed
  it, delete the patch and the `pnpm-workspace.yaml` entry, take both out of the Dockerfile's deps
  stage (`pnpm-workspace.yaml` from its first `COPY`, and the `COPY patches` line), and record that
  here as an amendment.
- **The first startups after installing the patch compile cold.** The patched Next has its own
  directory under `node_modules/.pnpm`, so Turbopack's persistent cache in `.next/dev` misses. The
  invitation route took over 60 s, over 60 s and 43 s on the first three startups, and 5 to 7 s from
  the fourth. That is once per checkout, the same as a fresh clone. The first full e2e run after
  the patch went out and back in for the negative control read one failure, a `/vi/login` 500
  (`SyntaxError: Unexpected end of JSON input`) while the banner server beside it was compacting
  its Turbopack cache. It was not the 404, it is not explained, and the next two full runs passed.
  `web/CLAUDE.md` records it.

## Alternatives not taken

- **A harness-only preload**, loaded through `NODE_OPTIONS` in `playwright.config.ts`'s `webServer`
  env, wrapping the same listener at runtime. It fixes only e2e servers, so a developer's
  `pnpm dev` still comes up with deep routes on 404. It hooks a module path inside Next, and when a
  bump moves that path it stops applying with no error.
- **Record the cause and fix nothing.** The flake stays, and #228's "Reproduced" end state asks for
  a fix.
- **Upgrade Next.** 16.4.0 and 16.5.0-canary.7 carry the same listener.
- **Run e2e against `next build && next start`.** Production has no watcher, so the race cannot
  happen there. But it changes what the whole suite measures, for a defect in a file that only
  `next dev` loads.
- **Retry, skip, or lengthen a timeout in the spec.** #228 forbids it. A stuck server stays stuck,
  so a retry fails the same way.

## Owed

- **An upstream report to vercel/next.js.** It is a public post, so the maintainer files it. A draft
  is in the pull request that carries this ADR.
