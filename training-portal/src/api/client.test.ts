import { afterEach, vi } from 'vitest'

import { ApiError, NETWORK_ERROR, apiClient } from './client'

afterEach(() => vi.restoreAllMocks())

describe('apiClient', () => {
  it('uses VITE_API_URL, the training prefix, query params and the attempt token', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    await apiClient.get('/leaderboard/', { query: { test: 'abc', limit: undefined }, token: 'tok' })
    const [url, init] = spy.mock.calls[0]
    expect(String(url)).toBe('http://api.test/api/v1/training/leaderboard/?test=abc')
    expect((init?.headers as Record<string, string>)['X-Attempt-Token']).toBe('tok')
    expect(init?.body).toBeUndefined()
  })

  it('turns backend errors and network failures into ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Аты кеминде 2 белгиден турушу керек.', code: 'name_too_short' }), { status: 400 }),
    )
    await expect(apiClient.post('/attempts/', {})).rejects.toMatchObject({ status: 400, code: 'name_too_short' })

    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const error = (await apiClient.get('/tests/').catch((e: unknown) => e)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(NETWORK_ERROR)
  })
})
