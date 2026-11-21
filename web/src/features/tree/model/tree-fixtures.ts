/**
 * Wire fixtures for the tree tests, typed as this slice's DTOs so a field the contract does not
 * have fails `tsc`. Test support only: imported by `*.test.ts(x)` files, never by the app.
 *
 * The family is spec § 7.4a's đa thê example: a father with two wives, two children of the first,
 * one of the second, and one child with no recorded mother whose đời is unknown.
 */

import type {
  FocusTreeNodeDto,
  FocusViewDto,
  SpouseNodeDto,
  TreeNodeDto,
  TreeResponseDto,
} from './tree-dto'

export const FATHER_ID = '00000000-0000-0000-0000-000000000001'
export const WIFE_1_ID = '00000000-0000-0000-0000-0000000000a1'
export const WIFE_2_ID = '00000000-0000-0000-0000-0000000000a2'
export const FOUNDER_ID = '00000000-0000-0000-0000-000000000099'

const UNKNOWN_DATE = { date: null, precision: 'unknown', display: null, lunar: null } as const

export function spouseDto(id: string, fullName: string, spouseOrder: number | null): SpouseNodeDto {
  return {
    id,
    full_name: fullName,
    gender: 'female',
    birth_date: UNKNOWN_DATE,
    death_date: UNKNOWN_DATE,
    avatar_url: null,
    posthumous_name: null,
    status: 'married',
    marriage_date: null,
    divorce_date: null,
    spouse_order: spouseOrder,
    membership_role: 'spouse',
  }
}

export function treeNodeDto(
  overrides: Partial<TreeNodeDto> & { id: string; full_name: string },
): TreeNodeDto {
  return {
    gender: 'male',
    birth_name: null,
    posthumous_name: null,
    birth_date: { date: '1900-01-01', precision: 'year', display: '1900', lunar: null },
    death_date: UNKNOWN_DATE,
    birth_place: null,
    avatar_url: null,
    membership_role: 'blood',
    is_founder: false,
    generation: 5,
    depth: 1,
    mother_id: null,
    mother_spouse_order: null,
    pedigree_collapse_ref: false,
    spouses: [],
    children: [],
    ...overrides,
  }
}

export function focusNodeDto(
  overrides: Partial<FocusTreeNodeDto> & { id: string; full_name: string },
): FocusTreeNodeDto {
  const { children = [], ...rest } = overrides
  return {
    ...treeNodeDto(rest),
    branch_id: null,
    branch_name: null,
    branch_order: null,
    has_more_descendants: false,
    children,
  }
}

/**
 * The children in the backend's order (birth order, date, name), which is not the wife order:
 * the second wife's child comes first, and the motherless child sits between two wives' children,
 * so a grouping that folds it into a wife already seen, or that keeps backend order, is visible.
 */
type ChildOverrides = Pick<TreeNodeDto, 'id' | 'full_name' | 'mother_id' | 'mother_spouse_order'> &
  Partial<Pick<TreeNodeDto, 'generation' | 'gender'>>

function children<T extends TreeNodeDto>(make: (o: ChildOverrides) => T): T[] {
  return [
    make({
      id: '00000000-0000-0000-0000-0000000000c3',
      full_name: 'Nguyễn Hữu Trác',
      mother_id: WIFE_2_ID,
      mother_spouse_order: 2,
    }),
    make({
      id: '00000000-0000-0000-0000-0000000000c4',
      full_name: 'Nguyễn Hữu Bảo',
      generation: null,
      mother_id: null,
      mother_spouse_order: null,
    }),
    make({
      id: '00000000-0000-0000-0000-0000000000c1',
      full_name: 'Nguyễn Hữu Lộc',
      mother_id: WIFE_1_ID,
      mother_spouse_order: 1,
    }),
    make({
      id: '00000000-0000-0000-0000-0000000000c2',
      full_name: 'Nguyễn Thị Sen',
      gender: 'female',
      mother_id: WIFE_1_ID,
      mother_spouse_order: 1,
    }),
  ]
}

const SPOUSES = [spouseDto(WIFE_2_ID, 'Lê Thị Nhàn', 2), spouseDto(WIFE_1_ID, 'Trần Thị Mão', 1)]

/** `GET /tree`, rooted at the father. */
export function treeResponseDto(): TreeResponseDto {
  return {
    tree: treeNodeDto({
      id: FATHER_ID,
      full_name: 'Nguyễn Hữu Đàm',
      generation: 4,
      depth: 0,
      spouses: SPOUSES,
      children: children(treeNodeDto),
    }),
    total_persons: 7,
    total_generations: 2,
  }
}

/** `GET /tree/focus/{FATHER_ID}?descendants=1`. */
export function focusViewDto(): FocusViewDto {
  return {
    focus_person_id: FATHER_ID,
    generation_of_focus: 4,
    ancestors: [
      {
        id: FOUNDER_ID,
        full_name: 'Nguyễn Hữu Tổ',
        gender: 'male',
        birth_date: UNKNOWN_DATE,
        death_date: UNKNOWN_DATE,
        avatar_url: null,
        generation: 1,
        is_founder: true,
      },
    ],
    focus_subtree: focusNodeDto({
      id: FATHER_ID,
      full_name: 'Nguyễn Hữu Đàm',
      generation: 4,
      depth: 0,
      spouses: SPOUSES,
      children: children(focusNodeDto),
    }),
  }
}
