import { describe, expect, it } from 'vitest'
import { parentChildResponseDtoSchema, toParentChild } from './parent-child-dto'

const parentChildFixture = {
  id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  parent_id: '11111111-1111-1111-1111-111111111111',
  child_id: '33333333-3333-3333-3333-333333333333',
  created_by_clan_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  relationship_type: 'biological',
  birth_order: 1,
  notes: null,
  created_by: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
  updated_by: null,
  is_deleted: false,
  deleted_at: null,
  deleted_by: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  version: 1,
}

describe('parentChildResponseDtoSchema + toParentChild', () => {
  it('maps a full ParentChildResponse fixture into the domain ParentChild, camelCased', () => {
    const dto = parentChildResponseDtoSchema.parse(parentChildFixture)
    expect(toParentChild(dto)).toEqual({
      id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
      parentId: '11111111-1111-1111-1111-111111111111',
      childId: '33333333-3333-3333-3333-333333333333',
      createdByClanId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      relationshipType: 'biological',
      birthOrder: 1,
      notes: null,
      createdBy: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
      updatedBy: null,
      isDeleted: false,
      deletedAt: null,
      deletedBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      version: 1,
    })
  })

  it('rejects a relationship_type outside the four the contract defines', () => {
    expect(() =>
      parentChildResponseDtoSchema.parse({ ...parentChildFixture, relationship_type: 'guardian' }),
    ).toThrow()
  })

  it('maps birth_order null to null', () => {
    const dto = parentChildResponseDtoSchema.parse({ ...parentChildFixture, birth_order: null })
    expect(toParentChild(dto).birthOrder).toBeNull()
  })
})
