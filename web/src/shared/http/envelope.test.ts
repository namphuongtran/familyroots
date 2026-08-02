import { describe, expect, it } from 'vitest'
import { MalformedResponseError } from './errors'
import { unwrapData, unwrapPage } from './envelope'

const asString = (raw: unknown): string => {
  if (typeof raw !== 'string') throw new Error('expected string')
  return raw
}

describe('unwrapData', () => {
  it('returns the parsed payload', () => {
    expect(unwrapData({ data: 'hello' }, asString)).toBe('hello')
  })

  it('accepts a null payload, which is a legitimate data value', () => {
    expect(unwrapData({ data: null }, (raw) => raw)).toBeNull()
  })

  it('rejects a body with no data key', () => {
    expect(() => unwrapData({ result: 'hello' }, asString)).toThrow(MalformedResponseError)
  })

  it('rejects a bare payload that skipped the envelope', () => {
    expect(() => unwrapData('hello', asString)).toThrow(MalformedResponseError)
  })
})

describe('unwrapPage', () => {
  const body = {
    data: ['a', 'b'],
    meta: { cursor: 'opaque-token', has_more: true, limit: 20 },
  }

  it('maps the contract meta onto the internal Page shape', () => {
    expect(unwrapPage(body, asString)).toEqual({
      items: ['a', 'b'],
      cursor: 'opaque-token',
      hasMore: true,
      limit: 20,
    })
  })

  it('handles the last page', () => {
    const last = { data: ['c'], meta: { cursor: null, has_more: false, limit: 20 } }
    expect(unwrapPage(last, asString)).toEqual({
      items: ['c'],
      cursor: null,
      hasMore: false,
      limit: 20,
    })
  })

  it('rejects the pre-envelope shape outright', () => {
    // The exact shape the old client used. Failing loudly here is the point:
    // a silent partial parse is how these bugs stayed hidden.
    const legacy = { data: ['a'], next_cursor: null, has_more: false }
    expect(() => unwrapPage(legacy, asString)).toThrow(MalformedResponseError)
  })

  it('rejects a non-array data payload', () => {
    const wrong = { data: { a: 1 }, meta: { cursor: null, has_more: false, limit: 20 } }
    expect(() => unwrapPage(wrong, asString)).toThrow(MalformedResponseError)
  })

  it('propagates an item parse failure instead of dropping the item', () => {
    const mixed = { data: ['a', 42], meta: { cursor: null, has_more: false, limit: 20 } }
    expect(() => unwrapPage(mixed, asString)).toThrow()
  })
})
