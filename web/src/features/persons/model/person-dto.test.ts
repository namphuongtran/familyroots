import { describe, expect, it } from 'vitest'
import {
  batchErrorDtoSchema,
  messageDataDtoSchema,
  personResponseDtoSchema,
  personSearchResultDtoSchema,
  toPerson,
  toPersonActionResult,
  toPersonSearchHit,
} from './person-dto'

/**
 * The `HistoricalDate` half of this fixture is the literal example from
 * docs/contracts/README.md, "HistoricalDate (canonical date shape)". The
 * rest of the person fields fill in what that doc's own `PersonResponse`
 * example elides (`{"id": "...", "full_name": "...", "...": "..."}`,
 * docs/contracts/rest-persons-api.md) with the full field set
 * `src/generated/api-types.ts`'s `PersonResponse` schema declares.
 */
const personResponseFixture = {
  id: '11111111-1111-1111-1111-111111111111',
  created_by_clan_id: '22222222-2222-2222-2222-222222222222',
  full_name: 'Nguyễn Văn An',
  birth_name: null,
  courtesy_name: null,
  posthumous_name: null,
  alias_name: null,
  gender: 'male',
  birth_date: {
    date: '1750-01-01',
    precision: 'circa',
    display: 'khoảng 1750',
    lunar: '15/08 Nhâm Tý',
  },
  death_date: { date: null, precision: 'unknown', display: null, lunar: null },
  birth_place: 'Hà Nội',
  death_place: null,
  burial_place: null,
  tomb_location: null,
  residence_place: null,
  religion: null,
  nationality: 'VN',
  occupation: null,
  education_level: null,
  title_rank: null,
  phone: null,
  email: null,
  biography: null,
  avatar_url: 'https://project.supabase.co/storage/v1/object/public/avatars/an.jpg',
  notes: null,
  is_deleted: false,
  created_by: '33333333-3333-3333-3333-333333333333',
  updated_by: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  version: 1,
}

describe('personResponseDtoSchema + toPerson', () => {
  it('maps a full PersonResponse fixture into the domain Person, camelCased', () => {
    const dto = personResponseDtoSchema.parse(personResponseFixture)
    expect(toPerson(dto)).toEqual({
      id: '11111111-1111-1111-1111-111111111111',
      createdByClanId: '22222222-2222-2222-2222-222222222222',
      fullName: 'Nguyễn Văn An',
      birthName: null,
      courtesyName: null,
      posthumousName: null,
      aliasName: null,
      gender: 'male',
      birthDate: {
        date: '1750-01-01',
        precision: 'circa',
        display: 'khoảng 1750',
        lunar: '15/08 Nhâm Tý',
      },
      deathDate: { date: null, precision: 'unknown', display: null, lunar: null },
      birthPlace: 'Hà Nội',
      deathPlace: null,
      burialPlace: null,
      tombLocation: null,
      residencePlace: null,
      religion: null,
      nationality: 'VN',
      occupation: null,
      educationLevel: null,
      titleRank: null,
      phone: null,
      email: null,
      biography: null,
      avatarUrl: 'https://project.supabase.co/storage/v1/object/public/avatars/an.jpg',
      notes: null,
      isDeleted: false,
      createdBy: '33333333-3333-3333-3333-333333333333',
      updatedBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      version: 1,
    })
  })

  it('normalises an absent birth_date/death_date key to null, not undefined', () => {
    const sparse = { ...personResponseFixture }
    // @ts-expect-error deleting an optional key to simulate `fields=` sparse selection
    delete sparse.birth_date
    // @ts-expect-error same, for death_date
    delete sparse.death_date
    const dto = personResponseDtoSchema.parse(sparse)
    expect(toPerson(dto).birthDate).toBeNull()
    expect(toPerson(dto).deathDate).toBeNull()
  })

  it('rejects a gender value outside the backend pattern (backend/app/schemas/person.py:37)', () => {
    const invalid = { ...personResponseFixture, gender: 'other' }
    expect(() => personResponseDtoSchema.parse(invalid)).toThrow()
  })

  it('rejects a precision value outside the five the contract defines', () => {
    const invalid = {
      ...personResponseFixture,
      birth_date: { ...personResponseFixture.birth_date, precision: 'approximate' },
    }
    expect(() => personResponseDtoSchema.parse(invalid)).toThrow()
  })
})

describe('personSearchResultDtoSchema + toPersonSearchHit', () => {
  const searchFixture = {
    id: '11111111-1111-1111-1111-111111111111',
    full_name: 'Nguyễn Văn An',
    gender: 'male',
    birth_date: {
      date: '1750-01-01',
      precision: 'circa',
      display: 'khoảng 1750',
      lunar: '15/08 Nhâm Tý',
    },
    avatar_url: null,
    version: 3,
    generation: 5,
    membership_role: 'editor',
    is_founder: true,
  }

  it('maps a PersonSearchResult row, where birth_date is required rather than optional', () => {
    const dto = personSearchResultDtoSchema.parse(searchFixture)
    expect(toPersonSearchHit(dto)).toEqual({
      id: '11111111-1111-1111-1111-111111111111',
      fullName: 'Nguyễn Văn An',
      gender: 'male',
      birthDate: {
        date: '1750-01-01',
        precision: 'circa',
        display: 'khoảng 1750',
        lunar: '15/08 Nhâm Tý',
      },
      avatarUrl: null,
      version: 3,
      generation: 5,
      membershipRole: 'editor',
      isFounder: true,
    })
  })

  it('rejects a fixture missing the required birth_date key', () => {
    const missing = { ...searchFixture }
    // @ts-expect-error simulate a malformed response missing the required key
    delete missing.birth_date
    expect(() => personSearchResultDtoSchema.parse(missing)).toThrow()
  })
})

describe('messageDataDtoSchema + toPersonActionResult', () => {
  it('maps the DELETE /persons/{id} confirmation body', () => {
    const dto = messageDataDtoSchema.parse({
      message: 'Person deleted',
      id: '11111111-1111-1111-1111-111111111111',
    })
    expect(toPersonActionResult(dto)).toEqual({
      message: 'Person deleted',
      id: '11111111-1111-1111-1111-111111111111',
    })
  })

  it('normalises an absent id to null', () => {
    const dto = messageDataDtoSchema.parse({ message: 'Person deleted' })
    expect(toPersonActionResult(dto).id).toBeNull()
  })
})

describe('batchErrorDtoSchema', () => {
  it('parses one row of POST /persons/batch meta.errors', () => {
    expect(
      batchErrorDtoSchema.parse({
        id: '99999999-9999-9999-9999-999999999999',
        code: 'person_not_found',
      }),
    ).toEqual({ id: '99999999-9999-9999-9999-999999999999', code: 'person_not_found' })
  })
})
