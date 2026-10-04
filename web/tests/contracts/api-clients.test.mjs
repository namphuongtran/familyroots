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

// #183 deleted the two auth tests that sat here, with the files they read:
// `src/infrastructure/auth/http-auth-profile-repository.ts` and
// `src/application/auth/use-cases/auth-context.ts`. Both read source text, which pins a setting
// (`.claude/rules/testing.md`). `src/features/auth/server/auth-repository.test.ts` sends each
// request and reads what comes back instead.

// the legacy-component deletion deleted both person contract tests that used to sit here.
//
// 'person API uses backend person routes and preserves normalization hooks' asserted on
// `src/lib/api/members.ts`'s `list`/`search`/`batch`/`getMarriages`/`getParentChild`/
// `getTimeline`/`getDocuments` methods and the `query-policy.ts` normalizers they called.
// The legacy-component deletion deleted all seven methods — each one's only caller was a
// `src/components/members/*.tsx` component this same seed deleted — leaving `members.ts`
// with just `personsApi.get`, which this test never asserted on.
//
// 'person batch query contract supports include_by_id and backend profiles' asserted on
// `src/infrastructure/http/query-policy.ts` (deleted outright — its only importer was the
// batch method above) and on `src/lib/types/member.ts`'s `PersonProfile`/`include_by_id`
// (deleted from that file for the same reason: their last reader went with `query-policy.ts`
// and `members.ts`'s batch method).
//
// The persons chain that stayed (`useMembers.ts`, `members.ts`'s `get`) was deleted by #172,
// which re-pointed its last readers at `@/features/persons`. Persons' contract is tested there,
// against real envelopes, not here.
