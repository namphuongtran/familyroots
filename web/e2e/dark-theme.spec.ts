import { expect, test } from '@playwright/test'

/**
 * Seed S-006, the half of it no other suite can reach: whether the dark palette
 * actually **reaches a screen**.
 *
 * `src/app/contrast.test.ts` reads the stylesheet, and that is the right place
 * to check a ratio, because Tailwind v4 drops an `@theme` variable no class
 * references and a browser cannot tell that apart from a dropped declaration
 * (`.claude/rules/tailwind.md` § 2). What the stylesheet cannot tell you is
 * whether the override wins the cascade. `@theme` emits its variables into
 * `@layer theme`; the dark block is unlayered, and unlayered CSS beats every
 * layer. That is a claim about a real cascade in a real engine, so it is
 * measured in one.
 *
 * `body` is the subject because it is the one element that paints a token on
 * every route today: `globals.css` gives it `bg-background` and `text-foreground`.
 * The 393 hardcoded palette utilities in `web/src` (`text-gray-*` and friends,
 * counted 2026-08-21) do **not** flip, and seed S-038 owns them. So this spec is
 * the honest statement of what S-006 delivered: the palette flips, and the
 * screens built on palette colours do not yet.
 *
 * ADR-045 is why there is no class and no attribute to set here. The mechanism is
 * the colour-scheme media query alone, so emulating the media query is the whole
 * of the setup, and the assertion that the document element carries no theme
 * marker is the assertion that no second mechanism crept back in.
 */

/** `--color-background` #fbf8f1 and `--color-foreground` #1a1a1a. */
const LIGHT = { background: 'rgb(251, 248, 241)', foreground: 'rgb(26, 26, 26)' }

/** Spec § 2.2 `surface` #15140f and `on-surface` #f1ebde. */
const DARK = { background: 'rgb(21, 20, 15)', foreground: 'rgb(241, 235, 222)' }

/** The two routes reachable without a Supabase session. */
const PUBLIC_PAGES = ['/vi/login', '/vi/register']

async function bodyColours(
  page: import('@playwright/test').Page,
): Promise<{ background: string; foreground: string }> {
  return page.evaluate(() => {
    const computed = getComputedStyle(document.body)
    return { background: computed.backgroundColor, foreground: computed.color }
  })
}

for (const path of PUBLIC_PAGES) {
  test.describe(`${path} paints the palette its colour scheme asks for`, () => {
    test('light is the default ground and ink', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'light' })
      await page.goto(path)

      expect(await bodyColours(page)).toEqual(LIGHT)
    })

    test('dark flips the ground and the ink together', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'dark' })
      await page.goto(path)

      // Both, in one assertion, on purpose. A ground that flips while the ink
      // does not is the failure this seed had to fix: `body` carried
      // `text-gray-900` #111827, a palette colour rather than a token, which
      // left near-black text on a near-black page. Asserting only the
      // background would have passed over it.
      expect(await bodyColours(page)).toEqual(DARK)
    })

    test('the flip needs no class and no attribute on the document', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'dark' })
      await page.goto(path)

      const marker = await page.evaluate(() => ({
        classes: document.documentElement.className,
        theme: document.documentElement.getAttribute('data-theme'),
      }))

      expect(marker.classes).not.toContain('dark')
      expect(marker.theme).toBeNull()
    })
  })
}

/**
 * Seed S-038 (folding in S-035): the sweep that moves the 393 hardcoded
 * `-gray-*` utilities counted above onto the semantic tokens they already had.
 * `body` alone (the three cases above) cannot see whether a form field or a
 * card boundary followed along, because those elements were never `body`.
 *
 * Two regions per public page, one text ink and one control boundary, each
 * read under both emulated schemes. `--color-muted-foreground` and
 * `--color-input` both flip between light and dark (`globals.css`'s dark
 * block overrides both), while the palette colours they replaced —
 * `text-gray-500` and `border-gray-300` — do not: a screen still built on
 * the palette would report the *light* value again under `dark`, not a
 * missing value, which is why each case checks both schemes rather than
 * only asserting dark is "different from light".
 */
const REGION = {
  /** `--color-muted-foreground`: light `#6e6653`, dark `#a99f89`. */
  mutedForeground: { light: 'rgb(110, 102, 83)', dark: 'rgb(169, 159, 137)' },
  /** `--color-input`: light `#8a8072`, dark `#a99f89`. */
  input: { light: 'rgb(138, 128, 114)', dark: 'rgb(169, 159, 137)' },
}

for (const path of PUBLIC_PAGES) {
  test.describe(`${path} carries the token sweep past body`, () => {
    test('the subtitle ink is muted-foreground in both schemes', async ({ page }) => {
      // The `<p>` right under the wordmark heading: `text-sm text-muted-foreground`
      // on both `/vi/login` and `/vi/register`, replacing `text-gray-500`.
      const subtitle = page.locator('h1').locator('xpath=following-sibling::p[1]')

      await page.emulateMedia({ colorScheme: 'light' })
      await page.goto(path)
      await expect(subtitle).toHaveCSS('color', REGION.mutedForeground.light)

      await page.emulateMedia({ colorScheme: 'dark' })
      await page.reload()
      await expect(subtitle).toHaveCSS('color', REGION.mutedForeground.dark)
    })

    test("the email field's boundary is the input token in both schemes", async ({ page }) => {
      // Both pages' email field carries `border-input`, replacing
      // `border-gray-300` — the exact class S-035 named as its whole point.
      const emailField = page.locator('input[type="email"]')

      await page.emulateMedia({ colorScheme: 'light' })
      await page.goto(path)
      await expect(emailField).toHaveCSS('border-top-color', REGION.input.light)

      await page.emulateMedia({ colorScheme: 'dark' })
      await page.reload()
      await expect(emailField).toHaveCSS('border-top-color', REGION.input.dark)
    })
  })
}
