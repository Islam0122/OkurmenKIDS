import axios, { isAxiosError, type AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { tokenStorage } from '@/lib/tokenStorage'
import type { RefreshResponse } from '@/types/auth'

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
})

// A bare instance with none of the interceptors below — used only to call
// the refresh endpoint itself, so that call can never recursively trigger
// the 401 handler it is part of. Exported so tests can mock it directly.
export const refreshClient = axios.create({ baseURL: API_BASE_URL })

type SessionExpiredHandler = () => void
let onSessionExpired: SessionExpiredHandler | null = null

/** Called once by the auth provider on mount so the client can force a logout+redirect without importing the router. */
export function registerSessionExpiredHandler(handler: SessionExpiredHandler): void {
  onSessionExpired = handler
}

apiClient.interceptors.request.use((config) => {
  const access = tokenStorage.getAccess()
  if (access) {
    config.headers.set('Authorization', `Bearer ${access}`)
  }
  return config
})

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

let refreshingPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStorage.getRefresh()
  if (!refresh) {
    throw new Error('No refresh token available')
  }
  const { data } = await refreshClient.post<RefreshResponse>('/auth/refresh/', { refresh })
  tokenStorage.setTokens(data.access, data.refresh)
  return data.access
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    // `isAxiosError` (a duck-typed `.isAxiosError === true` check) survives a
    // duplicated axios module instance the way `instanceof AxiosError` cannot
    // — which matters here since axios-mock-adapter (and some bundler setups)
    // can resolve a second copy of the axios package.
    if (!isAxiosError(error) || (error as AxiosError).response?.status !== 401) {
      throw error
    }

    const originalRequest = (error as AxiosError).config as RetryableRequestConfig | undefined
    const requestUrl = originalRequest?.url ?? ''

    // A 401 from the auth endpoints themselves means bad credentials or an
    // already-dead refresh token — never try to "refresh" those.
    const isAuthEndpoint = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/refresh')

    if (!originalRequest || originalRequest._retried || isAuthEndpoint) {
      if (isAuthEndpoint && requestUrl.includes('/auth/refresh')) {
        tokenStorage.clear()
        onSessionExpired?.()
      }
      throw error
    }

    originalRequest._retried = true

    try {
      refreshingPromise ??= refreshAccessToken().finally(() => {
        refreshingPromise = null
      })
      const access = await refreshingPromise
      originalRequest.headers.set('Authorization', `Bearer ${access}`)
      return await apiClient(originalRequest)
    } catch (refreshError) {
      tokenStorage.clear()
      onSessionExpired?.()
      throw refreshError
    }
  },
)
