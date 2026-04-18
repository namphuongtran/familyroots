export function personCreateInvalidationKeys() {
  return [
    ['persons', 'list'],
    ['tree'],
  ] as const
}

export function personUpdateInvalidationKeys(id: string) {
  return [
    ['persons', 'detail', id],
    ['persons', 'list'],
    ['tree'],
  ] as const
}

export function personDeleteInvalidationKeys(id: string) {
  return [
    ['persons', 'detail', id],
    ['persons', 'list'],
    ['tree'],
  ] as const
}

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
  const keys: Array<readonly unknown[]> = [...eventBaseInvalidationKeys(options?.upcomingDays ?? 30)]

  if (options?.detailId) {
    keys.push(['events', 'detail', options.detailId])
  }

  if (options?.personId) {
    keys.push(['persons', 'detail', options.personId, 'timeline'])
  }

  return keys
}
