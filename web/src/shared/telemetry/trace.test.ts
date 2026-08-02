import { describe, expect, it } from 'vitest'
import { newTraceparent, traceIdOf } from './trace'

const TRACEPARENT = /^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/

describe('newTraceparent', () => {
  it('produces a W3C traceparent the backend will accept', () => {
    expect(newTraceparent()).toMatch(TRACEPARENT)
  })

  it('never repeats', () => {
    const seen = new Set(Array.from({ length: 100 }, () => newTraceparent()))
    expect(seen.size).toBe(100)
  })

  it('never emits the all-zero ids the spec forbids', () => {
    for (let i = 0; i < 50; i += 1) {
      const [, traceId, spanId] = newTraceparent().split('-')
      expect(traceId).not.toBe('0'.repeat(32))
      expect(spanId).not.toBe('0'.repeat(16))
    }
  })
})

describe('traceIdOf', () => {
  it('extracts the trace id', () => {
    expect(traceIdOf('00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01')).toBe(
      '4bf92f3577b34da6a3ce929d0e0e4736',
    )
  })

  it('returns null for anything malformed', () => {
    expect(traceIdOf('garbage')).toBeNull()
    expect(traceIdOf('')).toBeNull()
  })
})
