import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..', '..')

async function read(relativePath) {
  return readFile(path.join(root, relativePath), 'utf8')
}

test('relationships API uses backend-prefixed relationship routes', async () => {
  const source = await read('src/lib/api/relationships.ts')

  assert.match(source, /\/relationships\/marriages/)
  assert.match(source, /\/relationships\/parent-child/)
  assert.doesNotMatch(source, /['"`]\/marriages['"`]/)
  assert.doesNotMatch(source, /['"`]\/parent-child['"`]/)
})

test('tree API uses backend tree routes and ancestors response type', async () => {
  const source = await read('src/lib/api/tree.ts')

  assert.match(source, /['"`]\/tree['"`]/)
  assert.match(source, /\/tree\/subtree\/\$\{rootId\}/)
  assert.match(source, /\/tree\/ancestors\/\$\{personId\}/)
  assert.match(source, /ApiResponse<TreeAncestorsResponse>/)
})

test('document contracts do not assume file_url in summary payloads', async () => {
  const types = await read('src/lib/types/document.ts')
  const gallery = await read('src/components/documents/DocumentGallery.tsx')

  assert.doesNotMatch(types, /\bfile_url\b/)
  assert.match(types, /\bpresigned_url\b/)
  assert.match(gallery, /\bpresigned_url\b/)
  assert.match(gallery, /getDocument\(documentQueryRepository, id\)/)
})

test('event contracts do not include unsupported end_date or location fields', async () => {
  const types = await read('src/lib/types/event.ts')
  const card = await read('src/components/events/EventCard.tsx')

  assert.doesNotMatch(types, /\bend_date\??:/)
  assert.doesNotMatch(types, /\blocation\??:/)
  assert.doesNotMatch(card, /\bevent\.end_date\b/)
  assert.doesNotMatch(card, /\bevent\.location\b/)
})

test('admin repositories use backend clan and platform endpoints', async () => {
  const source = await read('src/infrastructure/admin/http-admin-repositories.ts')

  assert.match(source, /['"`]\/clans\/me\/users['"`]/)
  assert.match(source, /['"`]\/clans\/me\/users\/pending['"`]/)
  assert.match(source, /\/clans\/me\/users\/\$\{userId\}\/approve/)
  assert.match(source, /\/clans\/me\/users\/\$\{userId\}\/reject/)
  assert.match(source, /['"`]\/platform\/clans['"`]/)
  assert.match(source, /['"`]\/platform\/metrics['"`]/)
})

test('platform metrics type matches backend counters', async () => {
  const types = await read('src/lib/types/admin.ts')
  const page = await read('src/app/[locale]/platform/metrics/page.tsx')

  assert.match(types, /\bactive_clans: number\b/)
  assert.match(types, /\bsuspended_clans: number\b/)
  assert.doesNotMatch(types, /\bactive_clans_30d: number\b/)
  assert.match(page, /\bactive_clans\b/)
  assert.match(page, /\bsuspended_clans\b/)
  assert.doesNotMatch(page, /\bactive_clans_30d\b/)
})

test('auth profile repository uses backend auth and me-clan endpoints', async () => {
  const source = await read('src/infrastructure/auth/http-auth-profile-repository.ts')

  assert.match(source, /['"`]\/auth\/me['"`]/)
  assert.match(source, /['"`]\/me\/clans['"`]/)
  assert.match(source, /\/me\/clans\/\$\{clanId\}\/select/)
  assert.match(source, /api\.post<RegisterResult>\('\/auth\/register'/)
  assert.match(source, /api\.post<RegisterResult>\('\/auth\/onboard'/)
})

test('auth context session fallback remains identity-only', async () => {
  const source = await read('src/application/auth/use-cases/auth-context.ts')

  assert.match(source, /role: undefined/)
  assert.match(source, /clan_id: undefined/)
  assert.match(source, /clan_name: undefined/)
  assert.match(source, /platform_role: undefined/)
  assert.match(source, /has_pending_membership: false/)
  assert.match(
    source,
    /Keep a minimal identity-only fallback; do not derive clan or role truth from Supabase metadata\./,
  )
})

test('person API uses backend person routes and preserves normalization hooks', async () => {
  const source = await read('src/lib/api/members.ts')

  assert.match(source, /normalizeIncludeAndFields/)
  assert.match(source, /normalizePersonsBatchInput/)
  assert.match(source, /normalizePersonsProfile/)
  assert.match(source, /['"`]\/persons['"`]/)
  assert.match(source, /['"`]\/persons\/search['"`]/)
  assert.match(source, /['"`]\/persons\/batch['"`]/)
  assert.match(source, /\/persons\/\$\{id\}\/marriages/)
  assert.match(source, /\/persons\/\$\{id\}\/parent-child/)
  assert.match(source, /\/persons\/\$\{id\}\/timeline/)
  assert.match(source, /\/persons\/\$\{id\}\/documents/)
})

test('person batch query contract supports include_by_id and backend profiles', async () => {
  const queryPolicy = await read('src/infrastructure/http/query-policy.ts')
  const memberTypes = await read('src/lib/types/member.ts')

  assert.match(queryPolicy, /normalizePersonsBatchInput/)
  assert.match(queryPolicy, /input\.include_by_id/)
  assert.match(queryPolicy, /profile: normalizePersonsProfile\(input\.profile\)/)
  assert.match(queryPolicy, /fieldSet\.add\(includeKey\)/)
  assert.match(memberTypes, /include_by_id\?: Record<string, string>/)
  assert.match(memberTypes, /export type PersonProfile = 'summary' \| 'detail' \| 'full'/)
})
