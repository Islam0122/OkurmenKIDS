import MockAdapter from 'axios-mock-adapter'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient, refreshClient, registerSessionExpiredHandler } from '@/api/client'
import { tokenStorage } from '@/lib/tokenStorage'

describe('apiClient auth interceptor', () => {
  let apiMock: MockAdapter
  let refreshMock: MockAdapter

  beforeEach(() => {
    apiMock = new MockAdapter(apiClient)
    refreshMock = new MockAdapter(refreshClient)
    tokenStorage.clear()
    registerSessionExpiredHandler(() => {})
  })

  afterEach(() => {
    apiMock.restore()
    refreshMock.restore()
  })

  it('refreshes the access token on a 401 and retries the original request once', async () => {
    tokenStorage.setTokens('expired-access', 'valid-refresh')

    apiMock.onGet('/lessons/').replyOnce(401)
    apiMock.onGet('/lessons/').replyOnce((config) => {
      expect(config.headers?.Authorization).toBe('Bearer new-access')
      return [200, { count: 0, next: null, previous: null, results: [] }]
    })
    refreshMock.onPost('/auth/refresh/').replyOnce(200, { access: 'new-access', refresh: 'new-refresh' })

    const response = await apiClient.get('/lessons/')

    expect(response.status).toBe(200)
    expect(tokenStorage.getAccess()).toBe('new-access')
    expect(tokenStorage.getRefresh()).toBe('new-refresh')
  })

  it('deduplicates concurrent refreshes when several requests 401 at once', async () => {
    tokenStorage.setTokens('expired-access', 'valid-refresh')

    apiMock.onGet('/lessons/').replyOnce(401)
    apiMock.onGet('/lessons/').replyOnce(200, { count: 0, next: null, previous: null, results: [] })
    apiMock.onGet('/groups/').replyOnce(401)
    apiMock.onGet('/groups/').replyOnce(200, { count: 0, next: null, previous: null, results: [] })

    let refreshCalls = 0
    refreshMock.onPost('/auth/refresh/').reply(() => {
      refreshCalls += 1
      return [200, { access: 'new-access', refresh: 'new-refresh' }]
    })

    await Promise.all([apiClient.get('/lessons/'), apiClient.get('/groups/')])

    expect(refreshCalls).toBe(1)
  })

  it('clears tokens and notifies session-expired when the refresh token itself is rejected', async () => {
    tokenStorage.setTokens('expired-access', 'dead-refresh')
    const onSessionExpired = vi.fn()
    registerSessionExpiredHandler(onSessionExpired)

    apiMock.onGet('/lessons/').reply(401)
    refreshMock.onPost('/auth/refresh/').reply(401)

    await expect(apiClient.get('/lessons/')).rejects.toBeTruthy()

    expect(tokenStorage.getAccess()).toBeNull()
    expect(tokenStorage.getRefresh()).toBeNull()
    expect(onSessionExpired).toHaveBeenCalledTimes(1)
  })

  it('never retries a 401 coming from the login endpoint itself', async () => {
    apiMock.onPost('/auth/login/').reply(401, { detail: 'Invalid credentials' })

    await expect(apiClient.post('/auth/login/', { username: 'x', password: 'y' })).rejects.toBeTruthy()

    expect(refreshMock.history.post ?? []).toHaveLength(0)
  })
})
