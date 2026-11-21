import test from 'node:test'
import assert from 'node:assert/strict'

// #183 deleted the auth half of this file with `src/application/auth/`: the
// `mapSessionUserToProfile`, `hydrateAuthContext` and `selectActiveClan` cases. The session is one
// TanStack Query query now, and where a user belongs is one pure function,
// `src/domain/session/access-state.ts`, whose table test replaces those cases. What is left here
// is the legacy query-invalidation helpers.
// the legacy-component deletion deleted `personCreateInvalidationKeys`, `personUpdateInvalidationKeys`, and
// `personDeleteInvalidationKeys` from `query-invalidation.ts`, along with the
// `'person invalidation helpers cover list, detail, and tree refreshes'` test below that
// covered only them — their sole caller was `useMembers.ts`'s `usePersonMutations`, deleted
// the same seed because its own sole caller, `src/components/members/MemberForm.tsx`, was
// dead (the persons form had already found it unreachable; the legacy-component deletion confirmed zero importers and deleted
// it). `documentUploadInvalidationKeys` still backs the live `src/lib/hooks/useDocuments.ts`, so
// it and its own test stay. #312 deleted `eventMutationInvalidationKeys` and its test with
// `useEvents.ts`, its one caller.
import {
  documentDeleteInvalidationKeys,
  documentUploadInvalidationKeys,
} from '../../src/lib/hooks/query-invalidation.ts'

test('document invalidation helpers cover person document/detail refreshes when linked', () => {
  assert.deepEqual(documentDeleteInvalidationKeys(), [['documents']])
  assert.deepEqual(documentUploadInvalidationKeys(), [['documents']])
  assert.deepEqual(documentUploadInvalidationKeys('person-1'), [
    ['documents'],
    ['persons', 'detail', 'person-1', 'documents'],
    ['persons', 'detail', 'person-1'],
  ])
})
