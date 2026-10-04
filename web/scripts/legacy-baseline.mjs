#!/usr/bin/env node
/**
 * The legacy baseline: the imports of legacy code that existed when the gate landed, and that may
 * only go away (ADR-060 § 4, issue #171).
 *
 *   pnpm depcruise:baseline            # rewrite the baseline from the tree as it is now
 *   pnpm depcruise:ratchet origin/main # fail if the baseline gained an entry since the merge base
 *
 * `pnpm depcruise` fails on a legacy import the baseline does not list. That alone admits any
 * import a contributor regenerates the baseline to include, so the ratchet compares the committed
 * baseline against the one at the merge base with `<ref>` and fails on any entry the merge base
 * did not have. Removing entries passes.
 *
 * It also fails on an entry that no longer matches an import. `--ignore-known` does not, and such
 * an entry would quietly re-admit the import it named: deleting an import without dropping its
 * entry would not shrink anything. import-linter's `ignore_imports`, the backend ratchet this
 * mirrors (ADR-013), refuses an unmatched entry the same way.
 *
 * The baseline holds `nothing-imports-legacy` entries only. dependency-cruiser's own
 * `depcruise-baseline` writes every violation, warnings included, and `--ignore-known` would then
 * hide the `no-orphans` warnings too: a change to a rule this gate was not meant to touch.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const RULE = 'nothing-imports-legacy'
const BASELINE = '.dependency-cruiser-known-violations.json'
const DEPCRUISE = fileURLToPath(new URL('../node_modules/.bin/depcruise', import.meta.url))

/**
 * Every `nothing-imports-legacy` violation in the tree under the working directory, sorted, and cut
 * to the four fields `--ignore-known` matches on (`soften-known-violations.mjs`).
 */
function currentEntries() {
  const output = execFileSync(
    DEPCRUISE,
    ['src', '--config', '.dependency-cruiser.cjs', '--output-type', 'baseline'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
  )
  return JSON.parse(output)
    .filter((violation) => violation.rule.name === RULE)
    .map(({ type, from, to, rule }) => ({ type, from, to, rule }))
    .sort((a, b) => a.from.localeCompare(b.from) || a.to.localeCompare(b.to))
}

/** The key dependency-cruiser itself matches a known violation on (`is-same-violation.mjs`). */
function key(entry) {
  return `${entry.rule.name}\t${entry.from}\t${entry.to}`
}

function describe(entry) {
  return `${entry.from} → ${entry.to}`
}

function git(...args) {
  return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
}

/** The baseline as committed at `commit`, or null when that commit has none. */
function baselineAt(commit) {
  try {
    return JSON.parse(git('show', `${commit}:./${BASELINE}`))
  } catch {
    return null
  }
}

function write() {
  const entries = currentEntries()
  writeFileSync(BASELINE, `${JSON.stringify(entries, null, 2)}\n`)
  console.log(`Wrote ${BASELINE}: ${entries.length} ${RULE} entries.`)
}

function check(ref) {
  const mergeBase = git('merge-base', 'HEAD', ref)
  const short = mergeBase.slice(0, 12)
  const before = baselineAt(mergeBase)
  const now = JSON.parse(readFileSync(BASELINE, 'utf8'))
  let failed = false

  const imports = new Set(currentEntries().map(key))
  const stale = now.filter((entry) => !imports.has(key(entry)))
  if (stale.length > 0) {
    failed = true
    console.error(
      `${BASELINE} lists ${stale.length} import${stale.length === 1 ? '' : 's'} the tree no ` +
        `longer has. Run \`pnpm depcruise:baseline\` and commit the result.`,
    )
    for (const entry of stale) console.error(`  stale  ${describe(entry)}`)
  }

  if (before === null) {
    console.log(`No ${BASELINE} at the merge base ${short}: this change introduces it.`)
    return failed ? 1 : 0
  }

  const known = new Set(before.map(key))
  const added = now.filter((entry) => !known.has(key(entry)))
  if (added.length > 0) {
    failed = true
    console.error(
      `${BASELINE} gained ${added.length} entr${added.length === 1 ? 'y' : 'ies'} since the ` +
        `merge base ${short}. The legacy may only shrink (ADR-060 § 4): import the slice's ` +
        `index.ts instead of legacy code.`,
    )
    for (const entry of added) console.error(`  added  ${describe(entry)}`)
  }

  if (failed) return 1
  console.log(
    `${BASELINE}: ${before.length} entries at the merge base ${short}, ${now.length} now. ` +
      `None added, none stale.`,
  )
  return 0
}

const [command, ref] = process.argv.slice(2)
if (command === 'write') {
  write()
} else if (command === 'check' && ref !== undefined) {
  process.exit(check(ref))
} else {
  console.error('Usage: legacy-baseline.mjs write | check <ref>')
  process.exit(2)
}
