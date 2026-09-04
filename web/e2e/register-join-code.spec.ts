import { expect, test, type Page } from '@playwright/test'

/**
 * the web register form, spec § 7.1b and ADR-057 § 2: on `/vi/register` the **join** field asks for
 * the clan code, carries the spec's helper text, and renders `clan_not_found` inline on
 * itself rather than in the page-level banner.
 *
 * Why this exists beside the jsdom test
 * (`src/app/[locale]/(auth)/register/page.test.tsx`): the last describe block is about
 * **layout**, and jsdom has no layout engine.
 *
 * **The join field is not the fourth instance of the overflow shape
 * `.claude/rules/tailwind.md` § 7 records, and this is where the measurement lives.**
 * Measured 2026-08-26 at 320px and 200% root font size, with the not-found error showing
 * beside a 100-character code: page `scrollWidth` 320 against `clientWidth` 320, the
 * helper paragraph 158/158, the error paragraph 158/158. Adding `wrap-anywhere` to both
 * paragraphs changed `overflowWrap` from `normal` to `anywhere` and changed **no**
 * measurement, so the class was removed rather than kept as a claim nothing supports. Two
 * reasons it does not overflow: a hyphen is already a break opportunity under
 * `overflow-wrap: normal`, so `nguyen-huu-thanh-oai` in the helper wraps by itself; and
 * the 100-character code stays inside the input, which scrolls internally (1604px against
 * a 156px box) without widening the page. The clan-code spec's instance differs because its suggestion
 * button echoed the code back as **text**. The three tests below stay because T-04 is the
 * requirement, not `wrap-anywhere`.
 *
 * The 404 is served by `page.route`, not by a backend: no e2e spec in this suite talks to
 * a live service. The envelope is the one `backend/app/core/exceptions.py` builds
 * for `EntityNotFoundError("clan_not_found")`
 * (`backend/app/application/auth/handlers.py:147`), with the generic message from
 * `backend/app/i18n/vi.json:4` — deliberately the *wrong* string for this screen, so a
 * test that accepted it would pass on the message spec § 7.1b replaces.
 */

/** 320dp is the width `T-04` names, and 32px is 200% of the 16px default root size. */
const NARROW_VIEWPORT = { width: 320, height: 640 }
const DOUBLED_ROOT_FONT_SIZE = '32px'

/** `web/messages/vi.json`, `auth` namespace. `/vi/…` is the default locale route. */
const VI = {
  joinClan: 'Tham gia dòng họ',
  clanCode: 'Mã dòng họ',
  joinHelper: 'Mã do quản trị dòng họ cung cấp, ví dụ: nguyen-huu-thanh-oai.',
  notFound: 'Không tìm thấy dòng họ với mã này. Xin kiểm tra lại với quản trị dòng họ.',
  invalid:
    'Mã dòng họ chỉ gồm chữ thường không dấu, số và dấu gạch ngang, ví dụ: nguyen-huu-thanh-oai.',
  registerError: 'Không thể tạo tài khoản',
  register: 'Đăng ký',
}

/** `backend/app/i18n/vi.json:4`, keyed `error.clan_not_found`. */
const BACKEND_VI_CLAN_NOT_FOUND_MESSAGE = 'Không tìm thấy dòng họ'

/**
 * The longest code the field accepts: `maxLength` is 100 and there is no hyphen in it, so
 * it is one unbreakable word. This is the worst case the field can hold, and the shape
 * that scrolled the whole page in all three earlier instances.
 */
const ONE_LONG_WORD_CODE = 'a'.repeat(100)

/** Fills the three fields this seed does not own, so the form can be submitted. */
async function fillTheRest(page: Page): Promise<void> {
  await page.locator('form input').first().fill('Trần Văn A')
  await page.locator('form input[type="email"]').fill('a@example.com')
  await page.locator('form input[type="password"]').fill('correct horse battery')
}

async function serveClanNotFound(page: Page): Promise<void> {
  await page.route('**/auth/register', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        error: {
          code: 'clan_not_found',
          message: BACKEND_VI_CLAN_NOT_FOUND_MESSAGE,
          detail: {},
        },
      }),
    })
  })
}

test.describe('/vi/register, join mode: the clan code field', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/vi/register')
    // Join is the mode the screen opens in. Checking it anyway makes that a reading
    // rather than an assumption, and keeps the test honest if the default ever moves.
    await page.getByLabel(VI.joinClan).check()
    await expect(page.getByLabel(VI.clanCode)).toBeVisible()
  })

  test('the helper text spec § 7.1b asks for is on screen and names the field', async ({
    page,
  }) => {
    const code = page.getByLabel(VI.clanCode)

    await expect(page.getByText(VI.joinHelper)).toBeVisible()
    await expect(code).toHaveAttribute('aria-describedby', /clan-code-helper/)
  })

  test('nothing on the field still asks for a UUID', async ({ page }) => {
    const placeholder = await page.getByLabel(VI.clanCode).getAttribute('placeholder')

    expect(placeholder).toBeNull()
  })

  test('a clan_not_found 404 renders on the field, not in the page banner', async ({ page }) => {
    await serveClanNotFound(page)
    await fillTheRest(page)
    await page.getByLabel(VI.clanCode).fill('khong-co-dong-ho-nay')
    await page.getByRole('button', { name: VI.register }).click()

    const code = page.getByLabel(VI.clanCode)
    await expect(code).toHaveAttribute('aria-invalid', 'true')

    // "on the field" is the claim: the alert is the element the input names in its own
    // `aria-describedby`, so a screen reader reaches it from the field.
    await expect(code).toHaveAttribute('aria-describedby', /clan-code-error/)
    await expect(page.locator('#clan-code-error')).toHaveText(VI.notFound)

    // The page-level banner is where this failure used to land. `register_error` is the
    // copy it shows for a rejection that is not an Error, so its absence discriminates.
    await expect(page.getByText(VI.registerError)).toHaveCount(0)
    // And the backend's generic wording is not what the field says.
    await expect(page.getByText(BACKEND_VI_CLAN_NOT_FOUND_MESSAGE, { exact: true })).toHaveCount(0)
  })

  test('a code the pattern refuses never leaves the browser', async ({ page }) => {
    let attempts = 0
    await page.route('**/auth/register', async (route) => {
      attempts += 1
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
    })

    await fillTheRest(page)
    // A space and capitals: `^[a-z0-9]+(?:-[a-z0-9]+)*$` refuses both.
    await page.getByLabel(VI.clanCode).fill('Nguyen Huu Thanh Oai')
    await page.getByRole('button', { name: VI.register }).click()

    await expect(page.locator('#clan-code-error')).toHaveText(VI.invalid)
    expect(attempts).toBe(0)
  })
})

test.describe('/vi/register, join mode, at 320dp and 200% text scale', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(NARROW_VIEWPORT)
    // Through a stylesheet, not `documentElement.style`: `<html>` is React-owned and
    // writing to it before hydration finishes prints a hydration mismatch the test itself
    // caused. `e2e/text-scale.spec.ts` explains it at length.
    await page.goto('/vi/register')
    await page.addStyleTag({ content: `:root { font-size: ${DOUBLED_ROOT_FONT_SIZE}; }` })
    await page.evaluate(() => document.fonts.ready)
    await page.getByLabel(VI.joinClan).check()
  })

  async function pageWidths(page: Page) {
    return page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
  }

  test('the helper text does not scroll the page', async ({ page }) => {
    await expect(page.getByText(VI.joinHelper)).toBeVisible()

    const { scrollWidth, clientWidth } = await pageWidths(page)

    expect(scrollWidth).toBe(clientWidth)
  })

  test('the not-found error does not scroll the page', async ({ page }) => {
    await serveClanNotFound(page)
    await fillTheRest(page)
    await page.getByLabel(VI.clanCode).fill(ONE_LONG_WORD_CODE)
    await page.getByRole('button', { name: VI.register }).click()

    await expect(page.locator('#clan-code-error')).toHaveText(VI.notFound)

    const { scrollWidth, clientWidth } = await pageWidths(page)

    expect(scrollWidth).toBe(clientWidth)
  })

  test('the shape error beside a 100-character code does not scroll the page', async ({ page }) => {
    await fillTheRest(page)
    // 100 characters, no hyphen, plus one capital so the pattern refuses it. The field
    // itself holds the longest unbreakable string this screen can be given.
    await page.getByLabel(VI.clanCode).fill(`A${ONE_LONG_WORD_CODE.slice(1)}`)
    await page.getByRole('button', { name: VI.register }).click()

    await expect(page.locator('#clan-code-error')).toHaveText(VI.invalid)

    const { scrollWidth, clientWidth } = await pageWidths(page)

    expect(scrollWidth).toBe(clientWidth)
  })
})
