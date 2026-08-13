import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * Seed S-005. ADR-041 § 5 makes the focus ring the on-surface colour `#1d1b16`
 * rather than an accent, and the offset that ships with it is load-bearing
 * rather than decoration. Measured 2026-08-14: the ring is **2.29:1** drawn
 * straight onto a filled `primary` button, and **16.22:1** against
 * `background`. So a `focus:ring-ring` with no offset is non-compliant under
 * WCAG 1.4.11 whatever the token says, and the ADR's own words are that S-005
 * "must ship the offset with the ring".
 *
 * Nothing else can see this. The class list type-checks, lints, and builds
 * either way, and `contrast.test.ts` measures token pairs rather than the
 * classes a screen composes. Hence a source scan.
 *
 * It matches `focus:ring-ring` only, not every `ring-ring`. A selection
 * indicator is a different thing from a focus ring and does not need an offset:
 * `components/events/EventCalendar.tsx` rings a selected day, and
 * `components/family-tree/MemberNode.tsx` rings a selected node.
 */
// `fileURLToPath`, not `.pathname`: this repository lives under a path with a
// space in it, and a URL keeps that percent-encoded.
const SRC = fileURLToPath(new URL('..', import.meta.url))

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return entry.name.endsWith('.tsx') ? [path] : []
  })

const focusRingLines = sourceFiles(SRC).flatMap((path) =>
  readFileSync(path, 'utf8')
    .split('\n')
    .map((line, index) => ({ path: path.slice(SRC.length), line: index + 1, text: line }))
    .filter(({ text }) => text.includes('focus:ring-ring')),
)

describe('every focus ring ships its offset', () => {
  it('found the focus rings at all', () => {
    // Guards the scan. A walk that matches nothing passes the assertion below
    // without checking anything. There were 28 on 2026-08-14, in 12 files.
    expect(focusRingLines.length).toBeGreaterThanOrEqual(20)
  })

  it.each(focusRingLines)('$path:$line carries focus:ring-offset-', ({ text }) => {
    expect(text).toContain('focus:ring-offset-')
  })
})
