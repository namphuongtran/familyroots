import { spawn, type ChildProcess } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

/**
 * Whether an e2e run uses a dev server it did not start, read on its outcome: issue #192.
 *
 * Two stand-in servers hold the hermetic and banner ports, the way another worktree's `next dev`
 * would, and record every path they are asked for. Each case runs the real `playwright test`
 * with the real `playwright.config.ts` and reads which server a spec reached: the run refuses
 * before any spec and names the URL, or the spec's request lands on the stand-in. Nothing here
 * reads `reuseExistingServer` or a port back from the config. Those are settings, and
 * `.claude/rules/testing.md` is why this file exists instead.
 *
 * **The spec is a throwaway, and so is the config that points at it.** The wrapper config spreads
 * the real one and changes only `testDir`, so every `webServer` entry, port and reuse rule is the
 * real one. The spec uses the `request` fixture and no `page`, so it needs no browser, which the
 * CI job running the unit gate does not install.
 *
 * **`CI` is removed from every run but one.** Under `CI` the old config never attached either, so
 * a case that inherited it from the CI job would pass the defect this file is named for.
 *
 * **Naming.** `playwright.config.test.ts` runs under `vitest --project unit` (its include glob in
 * `vitest.config.mts` names it). It sits outside `e2e/`, so Playwright's `testDir` never claims
 * it.
 */

const WEB_ROOT = import.meta.dirname
const PLAYWRIGHT = join(WEB_ROOT, 'node_modules', '.bin', 'playwright')

/** The path the throwaway spec asks the hermetic server for. Only a spec run sends it. */
const SPEC_PATH = '/a-spec-ran-here'

type Run = { status: number | null; output: string }

let standIns: Server[] = []
let requested: string[] = []
/** The `Host` header of each request for `SPEC_PATH`: the name the spec's origin was spelled with. */
let specHosts: string[] = []
let child: ChildProcess | undefined
let scratch: string | undefined

/** A server that answers every path with 200, as a `next dev` would, and records each path. */
function standIn(port: number): Promise<Server> {
  return new Promise((resolve, reject) => {
    const server = createServer((request, response) => {
      requested.push(request.url ?? '')
      if (request.url === SPEC_PATH) specHosts.push(request.headers.host ?? '')
      response.writeHead(200, { 'content-type': 'text/html' })
      response.end('<!doctype html><html lang="vi"><body>another worktree</body></html>')
    })
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => resolve(server))
  })
}

function close(server: Server): Promise<void> {
  return new Promise((resolve) => server.close(() => resolve()))
}

/**
 * Holds `count` adjacent ports from `base`, and returns `base`: two for the hermetic and banner
 * servers, three with the authenticated one.
 */
async function holdPorts(count: 2 | 3): Promise<number> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const base = 20_000 + 3 * Math.floor(Math.random() * 10_000)
    const held: Server[] = []
    try {
      for (let port = base; port < base + count; port++) held.push(await standIn(port))
      standIns = held
      return base
    } catch {
      await Promise.all(held.map(close))
    }
  }
  throw new Error(`could not find ${count} free adjacent ports`)
}

/**
 * The authenticated project, `auth-chromium`, claims a spec by its path, so the throwaway sits at
 * `e2e/auth/reach.auth.spec.ts` under the scratch `testDir`. The three inputs are never dialled:
 * with every port held and `E2E_REUSE_SERVER=1`, no dev server starts to read them.
 */
const AUTH_PROJECT = {
  project: 'auth-chromium',
  spec: join('e2e', 'auth', 'reach.auth.spec.ts'),
  env: {
    E2E_AUTH_STACK: '1',
    E2E_AUTH_SUPABASE_URL: 'http://supabase.invalid:54321',
    E2E_AUTH_SUPABASE_ANON_KEY: 'unused',
    E2E_AUTH_API_ORIGIN: 'http://api.invalid:8073',
    E2E_REUSE_SERVER: '1',
  },
}

function runPlaywright(
  env: Record<string, string>,
  { project = 'chromium', spec = 'reach.spec.ts' }: { project?: string; spec?: string } = {},
): Promise<Run> {
  const dir = mkdtempSync(join(tmpdir(), 'e2e-servers-'))
  scratch = dir
  const config = join(dir, 'playwright.config.ts')
  writeFileSync(
    config,
    `import config from ${JSON.stringify(join(WEB_ROOT, 'playwright.config.ts'))}\n` +
      `export default { ...config, testDir: ${JSON.stringify(join(dir, 'specs'))} }\n`,
  )
  mkdirSync(dirname(join(dir, 'specs', spec)), { recursive: true })
  writeFileSync(
    join(dir, 'specs', spec),
    `import { test } from ${JSON.stringify(join(WEB_ROOT, 'node_modules', '@playwright', 'test'))}\n` +
      `test('reaches the server of its project', async ({ request }) => {\n` +
      `  await request.get(${JSON.stringify(SPEC_PATH)})\n` +
      `})\n`,
  )

  const inherited = { ...process.env }
  for (const name of [
    'CI',
    'E2E_AUTH_STACK',
    'E2E_AUTH_HOST',
    'E2E_AUTH_SUPABASE_URL',
    'E2E_AUTH_SUPABASE_ANON_KEY',
    'E2E_AUTH_API_ORIGIN',
    'E2E_PORT_BASE',
    'E2E_REUSE_SERVER',
  ]) {
    delete inherited[name]
  }

  return new Promise((resolve) => {
    let output = ''
    // Async, unlike `scripts/legacy-baseline.test.ts`'s `spawnSync`: the stand-ins answer from this
    // process's event loop, so blocking it would make every port look dead to Playwright.
    // `detached` gives the run its own process group, so `afterEach` can stop it, and anything it
    // started, if a case times out.
    const playwright = spawn(
      PLAYWRIGHT,
      [
        'test',
        `--config=${config}`,
        `--project=${project}`,
        '--reporter=list',
        `--output=${join(dir, 'results')}`,
      ],
      { cwd: WEB_ROOT, env: { ...inherited, FORCE_COLOR: '0', ...env }, detached: true },
    )
    child = playwright
    playwright.stdout.on('data', (chunk: Buffer) => (output += chunk.toString()))
    playwright.stderr.on('data', (chunk: Buffer) => (output += chunk.toString()))
    playwright.on('close', (status) => {
      child = undefined
      resolve({ status, output })
    })
  })
}

afterEach(async () => {
  if (child?.pid !== undefined) process.kill(-child.pid, 'SIGKILL')
  child = undefined
  await Promise.all(standIns.map(close))
  standIns = []
  requested = []
  specHosts = []
  if (scratch) rmSync(scratch, { recursive: true, force: true })
  scratch = undefined
})

describe('a busy e2e port, held by a server this run did not start', { timeout: 60_000 }, () => {
  it('fails the run before any spec, naming the URL, when nothing asks to reuse it', async () => {
    const base = await holdPorts(2)

    const run = await runPlaywright({ E2E_PORT_BASE: String(base) })

    expect(run.output).toContain(`http://127.0.0.1:${base} is already used`)
    expect(requested).not.toContain(SPEC_PATH)
    expect(run.status).not.toBe(0)
  })

  it('is what the spec reaches when E2E_REUSE_SERVER=1 asks for it by name', async () => {
    const base = await holdPorts(2)

    const run = await runPlaywright({ E2E_PORT_BASE: String(base), E2E_REUSE_SERVER: '1' })

    expect(run.output).not.toContain('is already used')
    expect(requested).toContain(SPEC_PATH)
    expect(run.status).toBe(0)
  })

  it('is never attached to under CI, even when E2E_REUSE_SERVER=1 asks', async () => {
    const base = await holdPorts(2)

    const run = await runPlaywright({
      CI: '1',
      E2E_PORT_BASE: String(base),
      E2E_REUSE_SERVER: '1',
    })

    expect(run.output).toContain(`http://127.0.0.1:${base} is already used`)
    expect(requested).not.toContain(SPEC_PATH)
    expect(run.status).not.toBe(0)
  })
})

describe('E2E_PORT_BASE', { timeout: 60_000 }, () => {
  it('fails the run, naming the variable and the value, when it is not a port', async () => {
    const run = await runPlaywright({ E2E_PORT_BASE: '31OO' })

    expect(run.output).toContain('E2E_PORT_BASE')
    expect(run.output).toContain('"31OO"')
    expect(run.status).not.toBe(0)
  })
})

describe(
  'E2E_AUTH_HOST, the name the authenticated project reaches its server by (#231)',
  {
    timeout: 60_000,
  },
  () => {
    it('unset, is 127.0.0.1 on base+2, as before it existed', async () => {
      const base = await holdPorts(3)

      const run = await runPlaywright(
        { ...AUTH_PROJECT.env, E2E_PORT_BASE: String(base) },
        AUTH_PROJECT,
      )

      expect(run.output).not.toContain('is already used')
      expect(specHosts).toEqual([`127.0.0.1:${base + 2}`])
      expect(run.status).toBe(0)
    })

    it('set, is the name every request of the project carries, on the same port', async () => {
      const base = await holdPorts(3)

      // `localhost` stands in for image-e2e.yml's `familyroots-web.test`: it reaches the same
      // stand-in on every machine with no /etc/hosts line, under a name that is not 127.0.0.1.
      const run = await runPlaywright(
        { ...AUTH_PROJECT.env, E2E_PORT_BASE: String(base), E2E_AUTH_HOST: 'localhost' },
        AUTH_PROJECT,
      )

      expect(specHosts).toEqual([`localhost:${base + 2}`])
      expect(run.status).toBe(0)
    })

    it('fails the run, naming the variable and the value, when it is not a bare host name', async () => {
      const run = await runPlaywright({ E2E_AUTH_HOST: 'http://familyroots-web.test' })

      expect(run.output).toContain('E2E_AUTH_HOST')
      expect(run.output).toContain('"http://familyroots-web.test"')
      expect(run.status).not.toBe(0)
    })
  },
)
