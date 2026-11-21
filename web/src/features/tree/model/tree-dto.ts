/**
 * Zod DTOs for the tree read model (`TreeResponse`, `TreeNode`, `SpouseNode`, `FocusView`,
 * `FocusTreeNode`, `FocusAncestor`), each constrained to `src/generated/api-types.ts` by an
 * `assert*MatchesGenerated` function whose body is `return dto`, plus the mappers into
 * `@/domain/tree/tree`. Same pattern as `features/persons/model/person-dto.ts`.
 *
 * **The `HistoricalDate` DTO is not copied a third time.** persons holds the first copy and
 * relationships the second, whose header says the next slice must not ship a third. A new
 * `shared/` subtree is a structural decision with its own ADR, so this slice takes the schema
 * through `@/features/persons`, the public surface `cross-feature-only-via-index` allows.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { HistoricalDate } from '@/domain/date/historical-date'
import type {
  FamilyTree,
  FocusAncestor,
  FocusView,
  TreePerson,
  TreeSpouse,
} from '@/domain/tree/tree'
import {
  historicalDateDtoSchema,
  toHistoricalDate,
  type HistoricalDateDto,
} from '@/features/persons'

type Generated = components['schemas']

const nullableString = z.string().nullable().optional()
const nullableInt = z.number().int().nullable().optional()

function dateOrNull(dto: HistoricalDateDto | undefined): HistoricalDate | null {
  return dto === undefined ? null : toHistoricalDate(dto)
}

/** Mirrors `components["schemas"]["SpouseNode"]`. */
export const spouseNodeDtoSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  gender: z.string(),
  birth_date: historicalDateDtoSchema.optional(),
  death_date: historicalDateDtoSchema.optional(),
  avatar_url: nullableString,
  posthumous_name: nullableString,
  status: z.string(),
  marriage_date: nullableString,
  divorce_date: nullableString,
  spouse_order: nullableInt,
  membership_role: nullableString,
})
export type SpouseNodeDto = z.infer<typeof spouseNodeDtoSchema>

export function assertSpouseNodeDtoMatchesGenerated(dto: SpouseNodeDto): Generated['SpouseNode'] {
  return dto
}

/** The fields `TreeNode` and `FocusTreeNode` share, children aside. */
const nodeFields = {
  id: z.string(),
  full_name: z.string(),
  gender: z.string(),
  birth_name: nullableString,
  posthumous_name: nullableString,
  birth_date: historicalDateDtoSchema.optional(),
  death_date: historicalDateDtoSchema.optional(),
  birth_place: nullableString,
  avatar_url: nullableString,
  membership_role: nullableString,
  is_founder: z.boolean(),
  generation: nullableInt,
  depth: z.number(),
  mother_id: nullableString,
  mother_spouse_order: nullableInt,
  pedigree_collapse_ref: z.boolean(),
  spouses: z.array(spouseNodeDtoSchema),
}

export interface TreeNodeDto extends z.infer<z.ZodObject<typeof nodeFields>> {
  children: TreeNodeDto[]
}

/** Mirrors `components["schemas"]["TreeNode"]`, recursively. */
export const treeNodeDtoSchema: z.ZodType<TreeNodeDto> = z.object({
  ...nodeFields,
  get children() {
    return z.array(treeNodeDtoSchema)
  },
})

export function assertTreeNodeDtoMatchesGenerated(dto: TreeNodeDto): Generated['TreeNode'] {
  return dto
}

/** Mirrors `components["schemas"]["TreeResponse"]`. */
export const treeResponseDtoSchema = z.object({
  tree: treeNodeDtoSchema,
  total_persons: z.number(),
  total_generations: z.number(),
})
export type TreeResponseDto = z.infer<typeof treeResponseDtoSchema>

export function assertTreeResponseDtoMatchesGenerated(
  dto: TreeResponseDto,
): Generated['TreeResponse'] {
  return dto
}

export interface FocusTreeNodeDto extends z.infer<z.ZodObject<typeof nodeFields>> {
  branch_id?: string | null
  branch_name?: string | null
  branch_order?: number | null
  has_more_descendants: boolean
  children: FocusTreeNodeDto[]
}

/** Mirrors `components["schemas"]["FocusTreeNode"]`, recursively. */
export const focusTreeNodeDtoSchema: z.ZodType<FocusTreeNodeDto> = z.object({
  ...nodeFields,
  branch_id: nullableString,
  branch_name: nullableString,
  branch_order: nullableInt,
  has_more_descendants: z.boolean(),
  get children() {
    return z.array(focusTreeNodeDtoSchema)
  },
})

export function assertFocusTreeNodeDtoMatchesGenerated(
  dto: FocusTreeNodeDto,
): Generated['FocusTreeNode'] {
  return dto
}

/** Mirrors `components["schemas"]["FocusAncestor"]`. */
export const focusAncestorDtoSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  gender: z.string(),
  birth_date: historicalDateDtoSchema.optional(),
  death_date: historicalDateDtoSchema.optional(),
  avatar_url: nullableString,
  generation: nullableInt,
  is_founder: z.boolean(),
})
export type FocusAncestorDto = z.infer<typeof focusAncestorDtoSchema>

export function assertFocusAncestorDtoMatchesGenerated(
  dto: FocusAncestorDto,
): Generated['FocusAncestor'] {
  return dto
}

/** Mirrors `components["schemas"]["FocusView"]`. */
export const focusViewDtoSchema = z.object({
  focus_person_id: z.string(),
  generation_of_focus: nullableInt,
  ancestors: z.array(focusAncestorDtoSchema),
  focus_subtree: focusTreeNodeDtoSchema.nullable().optional(),
})
export type FocusViewDto = z.infer<typeof focusViewDtoSchema>

export function assertFocusViewDtoMatchesGenerated(dto: FocusViewDto): Generated['FocusView'] {
  return dto
}

export function toTreeSpouse(dto: SpouseNodeDto): TreeSpouse {
  return {
    id: dto.id,
    fullName: dto.full_name,
    gender: dto.gender,
    birthDate: dateOrNull(dto.birth_date),
    deathDate: dateOrNull(dto.death_date),
    avatarUrl: dto.avatar_url ?? null,
    status: dto.status,
    spouseOrder: dto.spouse_order ?? null,
    membershipRole: dto.membership_role ?? null,
  }
}

/** `TreeNode` or `FocusTreeNode` into `TreePerson`. `hasMoreDescendants` is focus-only. */
export function toTreePerson(dto: TreeNodeDto | FocusTreeNodeDto): TreePerson {
  return {
    id: dto.id,
    fullName: dto.full_name,
    gender: dto.gender,
    birthDate: dateOrNull(dto.birth_date),
    deathDate: dateOrNull(dto.death_date),
    avatarUrl: dto.avatar_url ?? null,
    membershipRole: dto.membership_role ?? null,
    isFounder: dto.is_founder,
    generation: dto.generation ?? null,
    motherId: dto.mother_id ?? null,
    motherSpouseOrder: dto.mother_spouse_order ?? null,
    isPedigreeStub: dto.pedigree_collapse_ref,
    hasMoreDescendants: 'has_more_descendants' in dto ? dto.has_more_descendants : false,
    spouses: dto.spouses.map(toTreeSpouse),
    children: dto.children.map(toTreePerson),
  }
}

export function toFamilyTree(dto: TreeResponseDto): FamilyTree {
  return {
    root: toTreePerson(dto.tree),
    totalPersons: dto.total_persons,
    totalGenerations: dto.total_generations,
  }
}

export function toFocusAncestor(dto: FocusAncestorDto): FocusAncestor {
  return {
    id: dto.id,
    fullName: dto.full_name,
    gender: dto.gender,
    avatarUrl: dto.avatar_url ?? null,
    generation: dto.generation ?? null,
    isFounder: dto.is_founder,
  }
}

export function toFocusView(dto: FocusViewDto): FocusView {
  return {
    focusPersonId: dto.focus_person_id,
    generationOfFocus: dto.generation_of_focus ?? null,
    ancestors: dto.ancestors.map(toFocusAncestor),
    subtree: dto.focus_subtree ? toTreePerson(dto.focus_subtree) : null,
  }
}
