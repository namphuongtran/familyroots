import type { PersonBatchGetInput } from '@/lib/types'

const PERSON_PROFILES = new Set(['summary', 'detail', 'full'])

function parseCsv(value: string | undefined): string[] {
  if (!value) {
    return []
  }

  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function toCsv(values: Iterable<string>): string | undefined {
  const normalized = Array.from(new Set(values)).filter(Boolean)
  return normalized.length > 0 ? normalized.join(',') : undefined
}

export function normalizePersonsProfile(profile: string | undefined):
  | 'summary'
  | 'detail'
  | 'full'
  | undefined {
  if (!profile) {
    return undefined
  }

  return PERSON_PROFILES.has(profile) ? (profile as 'summary' | 'detail' | 'full') : undefined
}

/**
 * Ensures sparse fields include compound include keys to prevent backend filtering.
 */
export function normalizeIncludeAndFields(input: {
  include?: string
  fields?: string
}): {
  include?: string
  fields?: string
} {
  const includeSet = new Set(parseCsv(input.include))
  const fieldSet = new Set(parseCsv(input.fields))

  includeSet.forEach((includeKey) => {
    fieldSet.add(includeKey)
  })

  return {
    include: toCsv(includeSet),
    fields: toCsv(fieldSet),
  }
}

/**
 * Normalizes batch request payload to match backend include/fields expectations.
 */
export function normalizePersonsBatchInput(input: PersonBatchGetInput): PersonBatchGetInput {
  const includeById: Record<string, string> | undefined = input.include_by_id
    ? Object.entries(input.include_by_id).reduce<Record<string, string>>(
        (acc, [id, includes]) => {
          const key = id.trim().toLowerCase()
          const normalizedIncludes = toCsv(parseCsv(includes))
          if (key && normalizedIncludes) {
            acc[key] = normalizedIncludes
          }
          return acc
        },
        {},
      )
    : undefined

  const includeSet = new Set(parseCsv(input.include))
  if (includeById) {
    Object.values(includeById).forEach((includes) => {
      parseCsv(includes).forEach((key) => includeSet.add(key))
    })
  }

  const normalizedIncludeAndFields = normalizeIncludeAndFields({
    include: toCsv(includeSet),
    fields: input.fields,
  })

  return {
    ...input,
    profile: normalizePersonsProfile(input.profile),
    include: normalizedIncludeAndFields.include,
    fields: normalizedIncludeAndFields.fields,
    include_by_id: includeById,
  }
}