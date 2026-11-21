import { describe, expect, it } from 'vitest'
import type { Marriage, ParentChild } from '@/domain/relationship/relationship'
import { sortMarriagesBySpouseOrder, splitParentChildByOrientation } from './relationship-sort'

function marriage(overrides: Partial<Marriage>): Marriage {
  return {
    id: overrides.id ?? 'm-0',
    person1Id: 'target',
    person2Id: 'spouse',
    createdByClanId: 'clan',
    status: 'married',
    marriageDate: null,
    divorceDate: null,
    marriagePlace: null,
    spouseOrder: null,
    notes: null,
    createdBy: 'user',
    updatedBy: null,
    isDeleted: false,
    deletedAt: null,
    deletedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

function parentChild(overrides: Partial<ParentChild>): ParentChild {
  return {
    id: overrides.id ?? 'pc-0',
    parentId: 'target',
    childId: 'child-a',
    createdByClanId: 'clan',
    relationshipType: 'biological',
    birthOrder: null,
    notes: null,
    createdBy: 'user',
    updatedBy: null,
    isDeleted: false,
    deletedAt: null,
    deletedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

describe('sortMarriagesBySpouseOrder', () => {
  it('orders by spouse_order ascending, null last (§3.3)', () => {
    const second = marriage({ id: 'm-1', spouseOrder: 2 })
    const first = marriage({ id: 'm-2', spouseOrder: 1 })
    const third = marriage({ id: 'm-3', spouseOrder: 3 })
    const unknown = marriage({ id: 'm-4', spouseOrder: null })

    expect(sortMarriagesBySpouseOrder([second, unknown, first, third]).map((m) => m.id)).toEqual([
      'm-2',
      'm-1',
      'm-3',
      'm-4',
    ])
  })

  it('breaks ties on id for a deterministic order', () => {
    const left = marriage({ id: 'm-a', spouseOrder: 1 })
    const right = marriage({ id: 'm-b', spouseOrder: 1 })
    expect(sortMarriagesBySpouseOrder([right, left]).map((m) => m.id)).toEqual(['m-a', 'm-b'])
  })
})

describe('splitParentChildByOrientation', () => {
  it('separates parents of the target from children of the target', () => {
    const asChild = parentChild({ id: 'pc-1', parentId: 'parent-a', childId: 'target' })
    const asParent = parentChild({ id: 'pc-2', parentId: 'target', childId: 'child-a' })
    const { parents, children } = splitParentChildByOrientation([asChild, asParent], 'target')
    expect(parents.map((p) => p.id)).toEqual(['pc-1'])
    expect(children.map((c) => c.id)).toEqual(['pc-2'])
  })

  it('drops an edge whose neither end matches the target id, rather than placing it in a group', () => {
    const stray = parentChild({ id: 'pc-s', parentId: 'other', childId: 'someone' })
    const { parents, children } = splitParentChildByOrientation([stray], 'target')
    expect(parents).toEqual([])
    expect(children).toEqual([])
  })
})
