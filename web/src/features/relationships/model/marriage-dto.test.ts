import { describe, expect, it } from 'vitest'
import { marriageResponseDtoSchema, toMarriage } from './marriage-dto'

/**
 * Field set from `src/generated/api-types.ts`'s `MarriageResponse` (line 2774).
 * `HistoricalDate` subobjects use the docs/contracts/README.md canonical shape.
 */
const marriageResponseFixture = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  person1_id: '11111111-1111-1111-1111-111111111111',
  person2_id: '22222222-2222-2222-2222-222222222222',
  created_by_clan_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  marriage_date: {
    date: '1970-05-15',
    precision: 'exact',
    display: null,
    lunar: null,
  },
  divorce_date: { date: null, precision: 'unknown', display: null, lunar: null },
  marriage_place: 'Hà Nội',
  status: 'married',
  spouse_order: 1,
  notes: null,
  created_by: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
  updated_by: null,
  is_deleted: false,
  deleted_at: null,
  deleted_by: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  version: 2,
}

describe('marriageResponseDtoSchema + toMarriage', () => {
  it('maps a full MarriageResponse fixture into the domain Marriage, camelCased', () => {
    const dto = marriageResponseDtoSchema.parse(marriageResponseFixture)
    expect(toMarriage(dto)).toEqual({
      id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      person1Id: '11111111-1111-1111-1111-111111111111',
      person2Id: '22222222-2222-2222-2222-222222222222',
      createdByClanId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      status: 'married',
      marriageDate: { date: '1970-05-15', precision: 'exact', display: null, lunar: null },
      divorceDate: { date: null, precision: 'unknown', display: null, lunar: null },
      marriagePlace: 'Hà Nội',
      spouseOrder: 1,
      notes: null,
      createdBy: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
      updatedBy: null,
      isDeleted: false,
      deletedAt: null,
      deletedBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      version: 2,
    })
  })

  it('normalises absent marriage_date / divorce_date to null', () => {
    const sparse = { ...marriageResponseFixture }
    // @ts-expect-error optional key absent
    delete sparse.marriage_date
    // @ts-expect-error optional key absent
    delete sparse.divorce_date
    const dto = marriageResponseDtoSchema.parse(sparse)
    const marriage = toMarriage(dto)
    expect(marriage.marriageDate).toBeNull()
    expect(marriage.divorceDate).toBeNull()
  })

  it('rejects a status outside the four the contract defines', () => {
    expect(() =>
      marriageResponseDtoSchema.parse({ ...marriageResponseFixture, status: 'engaged' }),
    ).toThrow()
  })

  it('carries spouse_order through as a number so §3.3 group ordering can read it', () => {
    const dto = marriageResponseDtoSchema.parse({ ...marriageResponseFixture, spouse_order: 2 })
    expect(toMarriage(dto).spouseOrder).toBe(2)
  })

  it('maps spouse_order null to null rather than undefined', () => {
    const dto = marriageResponseDtoSchema.parse({ ...marriageResponseFixture, spouse_order: null })
    expect(toMarriage(dto).spouseOrder).toBeNull()
  })
})
