import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * The two mandated typefaces ship twice: once for Flutter in
 * `mobile/assets/fonts/`, once for `next/font/local` here. Two copies can drift,
 * and drift means the two clients render different shapes for the same clan
 * name, which is the failure this seed (S-002) was written to prevent.
 *
 * Why two copies at all: `next/font/local` resolves `src` through the bundler,
 * and the web app is built with `web/` as its root. A path reaching out to
 * `mobile/` builds here and in CI, but depends on the deploy uploading files
 * outside the project root. That is a deployment setting nobody in this repo can
 * read, so the copies are deliberate and this test is the guard.
 *
 * If this fails, copy the file that changed rather than editing either in place:
 *   cp mobile/assets/fonts/<name>.ttf web/src/app/fonts/<name>.ttf
 */
const FONTS = ['PlusJakartaSans.ttf', 'Manrope.ttf']

const sha256 = (url: URL) => createHash('sha256').update(readFileSync(url)).digest('hex')

describe('the web typefaces match the ones the mobile app ships', () => {
  it.each(FONTS)('%s is byte-for-byte identical to the mobile copy', (name) => {
    const web = sha256(new URL(name, import.meta.url))
    const mobile = sha256(new URL(`../../../../mobile/assets/fonts/${name}`, import.meta.url))

    expect(web).toBe(mobile)
  })
})
