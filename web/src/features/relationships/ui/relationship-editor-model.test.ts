import { describe, expect, it } from 'vitest'
import type { Marriage, MarriageStatus } from '@/domain/relationship/relationship'
import { ApiError } from '@/shared/http/errors'
import {
  nextSpouseOrder,
  parentTooYoungDetail,
  planSpouseReorder,
  rankedMarriages,
} from './relationship-editor-model'

function marriage(
  id: string,
  spouseOrder: number | null,
  version: number,
  status: MarriageStatus = 'married',
): Marriage {
  return {
    id,
    person1Id: 'husband',
    person2Id: `wife-${id}`,
    createdByClanId: 'clan',
    status,
    marriageDate: null,
    divorceDate: null,
    marriagePlace: null,
    spouseOrder,
    notes: null,
    createdBy: 'u',
    updatedBy: null,
    isDeleted: false,
    deletedAt: null,
    deletedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version,
  }
}

describe('nextSpouseOrder', () => {
  it('is 1 with no spouse, and one past the highest live rank otherwise', () => {
    expect(nextSpouseOrder([])).toBe(1)
    expect(nextSpouseOrder([marriage('a', 1, 1)])).toBe(2)
    expect(nextSpouseOrder([marriage('a', 1, 1), marriage('b', 3, 1)])).toBe(4)
  })

  it('ignores a divorced marriage, which holds no rank', () => {
    expect(nextSpouseOrder([marriage('a', 1, 1), marriage('b', 2, 1, 'divorced')])).toBe(2)
  })
})

describe('rankedMarriages', () => {
  it('orders by spouse_order ascending, null last, and drops divorced', () => {
    const ranked = rankedMarriages([
      marriage('n', null, 1),
      marriage('b', 2, 1),
      marriage('d', 1, 1, 'divorced'),
      marriage('a', 1, 1),
    ])
    expect(ranked.map((m) => m.id)).toEqual(['a', 'b', 'n'])
  })
})

describe('planSpouseReorder', () => {
  const ranked = [marriage('a', 1, 4), marriage('b', 2, 7)]

  it('parks the neighbour, moves the wife up, then gives the neighbour her old rank', () => {
    expect(planSpouseReorder(ranked, 1, 'up')).toEqual([
      { marriageId: 'a', spouseOrder: null, expectedVersion: 4 },
      { marriageId: 'b', spouseOrder: 1, expectedVersion: 7 },
      { marriageId: 'a', spouseOrder: 2, expectedVersion: 'chained' },
    ])
  })

  it('down is the same swap seen from the other wife', () => {
    expect(planSpouseReorder(ranked, 0, 'down')).toEqual([
      { marriageId: 'b', spouseOrder: null, expectedVersion: 7 },
      { marriageId: 'a', spouseOrder: 2, expectedVersion: 4 },
      { marriageId: 'b', spouseOrder: 1, expectedVersion: 'chained' },
    ])
  })

  it('two writes when one of the pair holds no rank', () => {
    expect(planSpouseReorder([marriage('a', 1, 1), marriage('n', null, 2)], 1, 'up')).toEqual([
      { marriageId: 'a', spouseOrder: null, expectedVersion: 1 },
      { marriageId: 'n', spouseOrder: 1, expectedVersion: 2 },
    ])
  })

  it('nothing past either end', () => {
    expect(planSpouseReorder(ranked, 0, 'up')).toEqual([])
    expect(planSpouseReorder(ranked, 1, 'down')).toEqual([])
  })
})

describe('parentTooYoungDetail', () => {
  it('reads min_age_gap and actual off the 422', () => {
    const error = new ApiError({
      code: 'relationship.parent_too_young',
      message: 'x',
      status: 422,
      detail: { min_age_gap: 12, actual: 9.5 },
    })
    expect(parentTooYoungDetail(error)).toEqual({ minAgeGap: 12, actual: 9.5 })
  })

  it('is null for any other error', () => {
    const error = new ApiError({ code: 'validation_error', message: 'x', status: 422 })
    expect(parentTooYoungDetail(error)).toBeNull()
    expect(parentTooYoungDetail(new Error('x'))).toBeNull()
  })
})
