import api from './axios'
import type { Person, ApiResponse } from '@/lib/types'

// the legacy-component deletion trimmed this transport to the one call still live: `personsApi.get`,
// reached through `usePerson` in `src/lib/hooks/useMembers.ts`. `list`,
// `search`, `getMarriages`, `getParentChild`, `getTimeline`, `getDocuments`,
// `batchGet`, `create`, `update`, and `delete` are gone — each one's only
// caller was a `src/components/members/*.tsx` component this same seed
// deleted. This file, like `axios.ts` itself, does not leave yet: the tree
// and relationships slices still reach the rest of this chain through
// `usePerson` and `personKeys`. See `web/CLAUDE.md`, "Migration notes".

export const personsApi = {
  get: async (id: string): Promise<Person> => {
    const { data } = await api.get<ApiResponse<Person>>(`/persons/${id}`)
    return data.data
  },
}
