import api from './axios'
import type { TreeApiResponse, RelationshipPath, ApiResponse } from '@/lib/types'
import type { TreeNode } from '@/lib/types/tree'

// ── Mock tree data ────────────────────────────────────────────────────────────
const MOCK_TREE: TreeNode = {
  id: '1',
  full_name: 'Nguyễn Văn Tổ',
  gender: 'male',
  birth_date: '1850-01-01',
  birth_date_approx: true,
  death_date: '1920-03-15',
  death_date_approx: false,
  generation: 1,
  membership_role: 'blood',
  is_founder: true,
  depth: 0,
  spouses: [
    {
      id: 'spouse-1',
      full_name: 'Trần Thị Lan',
      gender: 'female',
      birth_date: '1855-05-10',
      death_date: '1925-07-20',
      status: 'married',
      spouse_order: 1,
      membership_role: 'spouse',
    },
  ],
  children: [
    {
      id: '2',
      full_name: 'Nguyễn Văn Hai',
      gender: 'male',
      birth_date: '1880-06-12',
      birth_date_approx: false,
      death_date: '1960-03-01',
      death_date_approx: false,
      generation: 2,
      membership_role: 'blood',
      is_founder: false,
      depth: 1,
      spouses: [],
      children: [
        {
          id: '3',
          full_name: 'Nguyễn Văn An',
          gender: 'male',
          birth_date: '1965-03-08',
          birth_date_approx: false,
          death_date_approx: false,
          generation: 3,
          membership_role: 'blood',
          is_founder: false,
          depth: 2,
          spouses: [],
          children: [],
        },
      ],
    },
  ],
}

const isMock = !process.env.NEXT_PUBLIC_API_URL

export const treeApi = {
  getFullTree: async (params?: {
    root_person_id?: string
    max_generations?: number
  }): Promise<TreeApiResponse> => {
    if (isMock) {
      return { tree: MOCK_TREE, total_persons: 3, total_generations: 3 }
    }
    const { data } = await api.get<ApiResponse<TreeApiResponse>>('/tree', { params })
    return data.data
  },

  getSubtree: async (
    rootId: string,
    maxGenerations = 5,
  ): Promise<TreeApiResponse> => {
    if (isMock) {
      return { tree: MOCK_TREE, total_persons: 3, total_generations: 3 }
    }
    const { data } = await api.get<ApiResponse<TreeApiResponse>>(`/tree/subtree/${rootId}`, {
      params: { max_generations: maxGenerations },
    })
    return data.data
  },

  getAncestors: async (
    personId: string,
    maxGenerations = 10,
  ): Promise<TreeApiResponse> => {
    const { data } = await api.get<TreeApiResponse>(`/tree/ancestors/${personId}`, {
      params: { max_generations: maxGenerations },
    })
    return data
  },

  getRelationshipPath: async (
    fromId: string,
    toId: string,
  ): Promise<RelationshipPath> => {
    const { data } = await api.get<ApiResponse<RelationshipPath>>('/tree/path', {
      params: { from_id: fromId, to_id: toId },
    })
    return data.data
  },
}
