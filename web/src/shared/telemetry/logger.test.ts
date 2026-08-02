import { afterEach, describe, expect, it, vi } from 'vitest'
import { createLogger } from './logger'

afterEach(() => vi.restoreAllMocks())

describe('createLogger', () => {
  it('emits one structured record per call', () => {
    const sink = vi.fn()
    createLogger({ sink }).info('persons.list.loaded', { count: 20 })

    expect(sink).toHaveBeenCalledTimes(1)
    expect(sink.mock.calls[0][0]).toMatchObject({
      level: 'info',
      event: 'persons.list.loaded',
      count: 20,
    })
  })

  it('carries the trace id so a browser log lines up with a backend log', () => {
    const sink = vi.fn()
    createLogger({ sink }).error('persons.list.failed', {
      traceId: '4bf92f3577b34da6a3ce929d0e0e4736',
    })

    expect(sink.mock.calls[0][0].traceId).toBe('4bf92f3577b34da6a3ce929d0e0e4736')
  })

  it('drops debug records below the configured level', () => {
    const sink = vi.fn()
    const logger = createLogger({ sink, level: 'info' })

    logger.debug('noisy')
    logger.info('kept')

    expect(sink).toHaveBeenCalledTimes(1)
    expect(sink.mock.calls[0][0].event).toBe('kept')
  })

  it('never lets a logging failure break the caller', () => {
    const sink = vi.fn(() => {
      throw new Error('sink exploded')
    })
    expect(() => createLogger({ sink }).info('anything')).not.toThrow()
  })
})
