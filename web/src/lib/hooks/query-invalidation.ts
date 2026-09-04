// The legacy-component deletion deleted `personCreateInvalidationKeys`, `personUpdateInvalidationKeys`, and
// `personDeleteInvalidationKeys`: their one caller, `useMembers.ts`'s `usePersonMutations`,
// was deleted the same seed (its own one caller, `MemberForm.tsx`, was already
// unreachable — the persons form flagged it, the legacy-component deletion confirmed and deleted it). See
// `tests/behavior/auth-and-invalidation.test.ts` for the test that covered only these three
// and was deleted with them.

export function documentUploadInvalidationKeys(personId?: string) {
  const keys: Array<readonly unknown[]> = [['documents']]

  if (personId) {
    keys.push(['persons', 'detail', personId, 'documents'])
    keys.push(['persons', 'detail', personId])
  }

  return keys
}

export function documentDeleteInvalidationKeys() {
  return [['documents']] as const
}

export function eventBaseInvalidationKeys(days = 30) {
  return [
    ['events', 'list'],
    ['events', 'upcoming', days],
  ] as const
}

export function eventMutationInvalidationKeys(options?: {
  detailId?: string
  personId?: string
  upcomingDays?: number
}) {
  const keys: Array<readonly unknown[]> = [
    ...eventBaseInvalidationKeys(options?.upcomingDays ?? 30),
  ]

  if (options?.detailId) {
    keys.push(['events', 'detail', options.detailId])
  }

  if (options?.personId) {
    keys.push(['persons', 'detail', options.personId, 'timeline'])
  }

  return keys
}
