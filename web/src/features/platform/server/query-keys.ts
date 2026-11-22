/** The one place `platform` query keys are built. Not clan-scoped: the platform is one. */

const ROOT = 'platform' as const

export const platformKeys = {
  all: () => [ROOT] as const,
  clans: () => [...platformKeys.all(), 'clans'] as const,
  metrics: () => [...platformKeys.all(), 'metrics'] as const,
}
