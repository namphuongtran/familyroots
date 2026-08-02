import { describe, expect, it, vi } from 'vitest'
import { createSingleFlight } from './refresh'

describe('createSingleFlight', () => {
  it('runs the operation once for concurrent callers and gives everyone the result', async () => {
    let resolveOperation: (value: string) => void = () => {}
    const operation = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveOperation = resolve
        }),
    )
    const guarded = createSingleFlight(operation)

    const calls = [guarded(), guarded(), guarded()]
    resolveOperation('fresh-token')

    expect(await Promise.all(calls)).toEqual(['fresh-token', 'fresh-token', 'fresh-token'])
    expect(operation).toHaveBeenCalledTimes(1)
  })

  it('allows a new attempt after the previous one resolves', async () => {
    const operation = vi.fn(async () => 'token')
    const guarded = createSingleFlight(operation)

    await guarded()
    await guarded()

    expect(operation).toHaveBeenCalledTimes(2)
  })

  it('rejects all concurrent callers when the operation fails', async () => {
    const operation = vi.fn(async () => {
      throw new Error('refresh failed')
    })
    const guarded = createSingleFlight(operation)

    const results = await Promise.allSettled([guarded(), guarded()])

    expect(results.every((r) => r.status === 'rejected')).toBe(true)
    expect(operation).toHaveBeenCalledTimes(1)
  })

  it('does not latch a failure — a later attempt runs again', async () => {
    // Otherwise one network blip at token-expiry time would sign the user out
    // permanently until a full reload.
    const operation = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce('token')
    const guarded = createSingleFlight(operation)

    await expect(guarded()).rejects.toThrow('blip')
    await expect(guarded()).resolves.toBe('token')
  })
})
