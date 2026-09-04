import { expect, test, type Page } from '@playwright/test'

/**
 * the clan-code spec, spec § 7.1b: on `/vi/register` in create mode the clan code is
 * "auto-suggested, slugified live from the name, editable", and `auth.clan_slug_taken`
 * renders inline on the code field with a suggested alternative.
 *
 * Why this exists beside the jsdom test
 * (`src/app/[locale]/(auth)/register/page.test.tsx`): two of the four claims below are
 * about **layout**, and jsdom has no layout engine, so only a real browser can measure
 * them. `.claude/rules/tailwind.md` § 7 records the same lesson twice — trap 1 (the text-scale spec,
 * the wordmark) and the fifth trap (the Supabase banner). A clan code is the third
 * field on this page that can be one long unbreakable word, and this time it is generated
 * from user input rather than hardcoded, so its worst case is longer than either.
 *
 * The `409` is served by `page.route`, not by a backend. That is deliberate: no e2e spec
 * in this suite talks to a live service, and a route handler gives the exact
 * envelope `backend/app/core/exceptions.py` produces —
 * `{"error": {"code": "auth.clan_slug_taken", "message": ..., "detail": {}}}`, with the
 * `message` already localised, copied from `backend/app/i18n/vi.json:96`.
 */

/** 320dp is the width `T-04` names, and 32px is 200% of the 16px default root size. */
const NARROW_VIEWPORT = { width: 320, height: 640 }
const DOUBLED_ROOT_FONT_SIZE = '32px'

/** `web/messages/vi.json`, `auth` namespace. `/vi/…` is the default locale route. */
const VI = {
  createClan: 'Tạo dòng họ mới',
  clanName: 'Tên dòng họ',
  clanCode: 'Mã dòng họ',
  clanCodeHelper: 'Người khác dùng mã này để xin tham gia dòng họ của bạn.',
  register: 'Đăng ký',
}

/** `backend/app/i18n/vi.json:96`, keyed `error.auth.clan_slug_taken`. */
const BACKEND_VI_TAKEN_MESSAGE = 'Đường dẫn dòng họ đã được sử dụng'

/**
 * A single-word clan name with no space and no hyphen anywhere, so its code is one
 * unbreakable word — the shape that scrolled the whole page in both earlier instances.
 * Every diacritic in it decomposes; the two `Đ`/`đ` do not, which is the other half of
 * what this seed fixes.
 */
const ONE_LONG_WORD_NAME = 'ĐặngĐìnhHữuThọQuảngNgãiĐạiTônTừĐường'
const ONE_LONG_WORD_CODE = 'dangdinhhuuthoquangngaidaitontuduong'

async function openCreateMode(page: Page): Promise<void> {
  await page.goto('/vi/register')
  await page.getByLabel(VI.createClan).check()
  await expect(page.getByLabel(VI.clanCode)).toBeVisible()
}

/** Fills the three fields the clan-code spec does not own, so the form can be submitted. */
async function fillTheRest(page: Page): Promise<void> {
  await page.locator('form input').first().fill('Trần Văn A')
  await page.locator('form input[type="email"]').fill('a@example.com')
  await page.locator('form input[type="password"]').fill('correct horse battery')
}

async function serveClanSlugTaken(page: Page): Promise<void> {
  await page.route('**/auth/register', async (route) => {
    await route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        error: { code: 'auth.clan_slug_taken', message: BACKEND_VI_TAKEN_MESSAGE, detail: {} },
      }),
    })
  })
}

test.describe('/vi/register, create mode: the clan code field', () => {
  test('a Vietnamese name with diacritics fills the code field with its slug', async ({ page }) => {
    await openCreateMode(page)

    await page.getByLabel(VI.clanName).fill('Trần Gia')

    await expect(page.getByLabel(VI.clanCode)).toHaveValue('tran-gia')
  })

  test('Đ survives into the field rather than being dropped', async ({ page }) => {
    await openCreateMode(page)

    await page.getByLabel(VI.clanName).fill('Đặng Đình')

    // A naive NFD strip yields "ang-inh": `'Đ'.normalize('NFD')` is still U+0110.
    await expect(page.getByLabel(VI.clanCode)).toHaveValue('dang-dinh')
  })

  test('editing the code stops further typing in the name from overwriting it', async ({
    page,
  }) => {
    await openCreateMode(page)
    const code = page.getByLabel(VI.clanCode)

    await page.getByLabel(VI.clanName).fill('Trần Gia')
    await expect(code).toHaveValue('tran-gia')

    await code.fill('tran-gia-quang-ngai')
    await page.getByLabel(VI.clanName).fill('Trần Gia Hà Nội')

    await expect(code).toHaveValue('tran-gia-quang-ngai')
  })

  test('the helper text spec § 7.1b asks for is on screen', async ({ page }) => {
    await openCreateMode(page)

    await expect(page.getByText(VI.clanCodeHelper)).toBeVisible()
  })

  test('a clan_slug_taken 409 renders on the code field with an alternative', async ({ page }) => {
    await openCreateMode(page)
    await serveClanSlugTaken(page)

    await fillTheRest(page)
    await page.getByLabel(VI.clanName).fill('Trần Gia')
    await page.getByRole('button', { name: VI.register }).click()

    const code = page.getByLabel(VI.clanCode)
    await expect(code).toHaveAttribute('aria-invalid', 'true')

    // "on the code field" is the claim: the alert is the element the input names in its
    // own `aria-describedby`, so a screen reader reaches it from the field.
    const describedBy = await code.getAttribute('aria-describedby')
    expect(describedBy).toContain('clan-slug-error')
    const alert = page.locator('#clan-slug-error')
    await expect(alert).toContainText(BACKEND_VI_TAKEN_MESSAGE)

    const suggestion = alert.getByRole('button', { name: /tran-gia-2/ })
    await expect(suggestion).toBeVisible()
    await suggestion.click()
    await expect(code).toHaveValue('tran-gia-2')
  })
})

test.describe('/vi/register, create mode, at 320dp and 200% text scale', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(NARROW_VIEWPORT)
    // Through a stylesheet, not `documentElement.style`: `<html>` is React-owned and
    // writing to it before hydration finishes prints a hydration mismatch the test
    // itself caused. `e2e/text-scale.spec.ts` explains it at length.
    await page.goto('/vi/register')
    await page.addStyleTag({ content: `:root { font-size: ${DOUBLED_ROOT_FONT_SIZE}; }` })
    await page.evaluate(() => document.fonts.ready)
    await page.getByLabel(VI.createClan).check()
  })

  test('the helper text and the code field do not scroll the page', async ({ page }) => {
    await page.getByLabel(VI.clanName).fill(ONE_LONG_WORD_NAME)
    await expect(page.getByLabel(VI.clanCode)).toHaveValue(ONE_LONG_WORD_CODE)

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))

    expect(scrollWidth).toBe(clientWidth)
  })

  test('the taken-code error and its suggestion do not scroll the page', async ({ page }) => {
    await serveClanSlugTaken(page)
    await fillTheRest(page)
    await page.getByLabel(VI.clanName).fill(ONE_LONG_WORD_NAME)
    await page.getByRole('button', { name: VI.register }).click()

    // The suggestion is the longest generated string on the page: the whole code plus a
    // counter, with no break opportunity in it at all.
    const suggestion = page.locator('#clan-slug-error').getByRole('button')
    await expect(suggestion).toContainText(`${ONE_LONG_WORD_CODE}-2`)

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))

    expect(scrollWidth).toBe(clientWidth)
  })
})
