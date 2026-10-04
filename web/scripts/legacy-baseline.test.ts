import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

/**
 * The legacy gate, read on its outcome: issue #171, ADR-060 § 4.
 *
 * Each case builds a throwaway git repository holding the real `.dependency-cruiser.cjs` and a
 * five-file `src/`, plants an import, and runs the real commands against it. Nothing here reads
 * the rule's regex or the baseline's contents back: a list is a setting, and
 * `.claude/rules/testing.md` ("A set is a setting too") is why reading 2 of the issue exists.
 * Every case asserts what a pull request would see, the exit code and the edge it names.
 *
 * **Naming.** `scripts/**\/*.test.ts` runs under `vitest --project unit` (its include glob in
 * `vitest.config.mts` names it).
 */

const WEB_ROOT = join(import.meta.dirname, '..')
const DEPCRUISE = join(WEB_ROOT, 'node_modules', '.bin', 'depcruise')
const SCRIPT = join(WEB_ROOT, 'scripts', 'legacy-baseline.mjs')

const TSCONFIG = JSON.stringify({
  compilerOptions: {
    module: 'esnext',
    moduleResolution: 'bundler',
    noEmit: true,
    paths: { '@/*': ['./src/*'] },
  },
})

/** A legacy hook, a second legacy hook that imports it, and one route already on the baseline. */
const SEED: Record<string, string> = {
  'src/lib/hooks/useAuth.ts': 'export const useAuth = () => 1\n',
  'src/lib/hooks/useSession.ts':
    "import { useAuth } from './useAuth'\nexport const useSession = () => useAuth()\n",
  'src/app/page.ts':
    "import { useSession } from '@/lib/hooks/useSession'\nexport default useSession\n",
  'src/features/persons/ui/PersonRow.ts': 'export const PersonRow = () => 0\n',
  'src/features/persons/index.ts': "export { PersonRow } from './ui/PersonRow'\n",
}

const PLANT = [
  'src/features/persons/ui/PersonRow.ts',
  "import { useAuth } from '@/lib/hooks/useAuth'\nexport const PersonRow = () => useAuth()\n",
] as const

type Run = { status: number; output: string }

let repo: string

function put(path: string, content: string) {
  mkdirSync(dirname(join(repo, path)), { recursive: true })
  writeFileSync(join(repo, path), content)
}

function git(...args: string[]) {
  return execFileSync(
    'git',
    [
      ...['-c', 'user.name=t', '-c', 'user.email=t@example.com'],
      ...['-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null'],
      ...args,
    ],
    { cwd: repo, encoding: 'utf8' },
  )
}

function run(command: string, args: string[]): Run {
  const result = spawnSync(command, args, { cwd: repo, encoding: 'utf8' })
  return { status: result.status ?? -1, output: `${result.stdout}${result.stderr}` }
}

/** `pnpm depcruise`, as `package.json` spells it, with the binary resolved from `web/`. */
function gate(): Run {
  const pkg = JSON.parse(readFileSync(join(WEB_ROOT, 'package.json'), 'utf8'))
  const [bin, ...args] = (pkg.scripts.depcruise as string).split(' ')
  expect(bin).toBe('depcruise')
  return run(DEPCRUISE, args)
}

const baseline = {
  write: () => run(process.execPath, [SCRIPT, 'write']),
  check: (ref: string) => run(process.execPath, [SCRIPT, 'check', ref]),
}

beforeEach(() => {
  repo = mkdtempSync(join(tmpdir(), 'legacy-baseline-'))
  copyFileSync(join(WEB_ROOT, '.dependency-cruiser.cjs'), join(repo, '.dependency-cruiser.cjs'))
  put('tsconfig.json', TSCONFIG)
  for (const [path, content] of Object.entries(SEED)) put(path, content)
  git('init', '-q', '-b', 'main')
  expect(baseline.write().status).toBe(0)
  git('add', '-A')
  git('commit', '-q', '-m', 'base')
  git('switch', '-q', '-c', 'feature')
})

afterEach(() => {
  rmSync(repo, { recursive: true, force: true })
})

describe('the legacy gate', { timeout: 60_000 }, () => {
  it('passes on the seeded tree, whose one non-legacy import of legacy is on the baseline', () => {
    const { status, output } = gate()

    expect(output).not.toContain('nothing-imports-legacy')
    expect(status).toBe(0)
  })

  it('reading 1: fails on a planted import and names the rule and the edge', () => {
    put(...PLANT)

    const { status, output } = gate()

    expect(output).toContain(
      'nothing-imports-legacy: src/features/persons/ui/PersonRow.ts → src/lib/hooks/useAuth.ts',
    )
    expect(status).toBe(1)
  })
})

/**
 * "The rules that exist today still do not fire on edges inside the legacy set. That includes
 * `no-circular` and the `no-orphans` warning." Each silence is paired with the same plant outside
 * legacy, where the rule must fire: a rule that fires nowhere passes every silence case.
 */
describe('the other rules inside legacy', { timeout: 60_000 }, () => {
  it('no-circular fires on a cycle outside legacy', () => {
    put('src/features/persons/ui/PersonRow.ts', "import '../index'\nexport const PersonRow = 0\n")

    const { status, output } = gate()

    expect(output).toMatch(/no-circular: src\/features\/persons\//)
    expect(status).toBe(1)
  })

  it('no-circular stays silent on a cycle inside legacy', () => {
    put('src/lib/hooks/useAuth.ts', "import './useSession'\nexport const useAuth = () => 1\n")

    const { status, output } = gate()

    expect(output).not.toContain('no-circular')
    expect(status).toBe(0)
  })

  it('no-circular still reports a cycle through legacy, on its edges outside legacy', () => {
    put(...PLANT)
    put('src/lib/hooks/useAuth.ts', "import '@/features/persons'\nexport const useAuth = () => 1\n")

    const { status, output } = gate()

    expect(output).toContain(
      'no-circular: src/features/persons/index.ts → \n      src/features/persons/ui/PersonRow.ts',
    )
    expect(output).not.toMatch(/no-circular: src\/lib\/hooks\//)
    expect(status).not.toBe(0)
  })

  it('no-orphans fires on a module nothing imports', () => {
    put('src/lib/utils/label.ts', 'export const label = 0\n')

    expect(gate().output).toContain('no-orphans: src/lib/utils/label.ts')
  })

  it('no-orphans stays silent on a legacy module nothing imports', () => {
    put('src/lib/hooks/useDead.ts', 'export const useDead = 0\n')

    expect(gate().output).not.toContain('src/lib/hooks/useDead.ts')
  })

  it('no-orphans stays silent on a module only legacy imports', () => {
    put('src/lib/utils/label.ts', 'export const label = 0\n')
    put('src/lib/hooks/useAuth.ts', "import '@/lib/utils/label'\nexport const useAuth = () => 1\n")

    expect(gate().output).not.toContain('no-orphans: src/lib/utils/label.ts')
  })
})

describe('the ratchet', { timeout: 60_000 }, () => {
  it('passes when nothing changed', () => {
    const { status } = baseline.check('main')

    expect(status).toBe(0)
  })

  it('reading 2: fails when the baseline was regenerated to admit a planted import', () => {
    put(...PLANT)
    expect(baseline.write().status).toBe(0)
    expect(gate().status).toBe(0)
    git('commit', '-q', '-am', 'plant')

    const { status, output } = baseline.check('main')

    expect(output).toContain('src/features/persons/ui/PersonRow.ts → src/lib/hooks/useAuth.ts')
    expect(status).toBe(1)
  })

  it('reading 3: passes a shrink, an import deleted and its entry dropped', () => {
    put('src/app/page.ts', 'export default () => 0\n')
    expect(baseline.write().status).toBe(0)
    expect(gate().status).toBe(0)
    git('commit', '-q', '-am', 'shrink')

    const { status, output } = baseline.check('main')

    expect(output).toContain('1 entry at the merge base')
    expect(output).toContain('0 now')
    expect(status).toBe(0)
  })

  it('fails when an import is gone but its entry stays, since the entry would re-admit it', () => {
    put('src/app/page.ts', 'export default () => 0\n')
    git('commit', '-q', '-am', 'delete the import, keep the entry')

    const { status, output } = baseline.check('main')

    expect(output).toContain('src/app/page.ts → src/lib/hooks/useSession.ts')
    expect(output).toContain('pnpm depcruise:baseline')
    expect(status).toBe(1)
  })
})
