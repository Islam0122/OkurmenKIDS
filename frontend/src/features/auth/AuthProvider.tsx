import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { authApi } from '@/api/auth'
import { registerSessionExpiredHandler } from '@/api/client'
import { isNetworkOrServerError } from '@/lib/apiError'
import { tokenStorage } from '@/lib/tokenStorage'
import type { User } from '@/types/auth'

import { AuthContext, type AuthStatus } from './AuthContext'

/** Mirrors the backend's own login gate (see `LoginSerializer.validate`) so
 * the UI never shows an "authenticated" screen the API would reject anyway.
 * Verification gating applies to Teacher accounts only — an Admin account
 * (created via `createsuperuser`) is trusted from the start, same rule the
 * backend itself applies. */
function isEligibleUser(user: User): boolean {
  if (!user.is_active) return false
  if (user.role === 'teacher') return user.is_verified
  return user.role === 'admin'
}

function describeIneligibility(user: User): string {
  if (!user.is_active) return 'Аккаунт деактивирован.'
  if (user.role === 'teacher' && !user.is_verified) return 'Аккаунт ещё не подтверждён администратором.'
  return 'Доступ к личному кабинету недоступен для этой роли.'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0)

  const logout = useCallback(() => {
    tokenStorage.clear()
    queryClient.clear()
    setUser(null)
    setStatus('guest')
  }, [queryClient])

  const retry = useCallback(() => {
    setStatus('loading')
    setBootstrapAttempt((attempt) => attempt + 1)
  }, [])

  useEffect(() => {
    registerSessionExpiredHandler(logout)
  }, [logout])

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!tokenStorage.getAccess() && !tokenStorage.getRefresh()) {
        setStatus('guest')
        return
      }
      try {
        const me = await authApi.me()
        if (cancelled) return
        setUser(me)
        setStatus(isEligibleUser(me) ? 'authenticated' : 'forbidden')
      } catch (error) {
        if (cancelled) return
        // The backend being unreachable (down, offline, CORS misconfigured)
        // is not the same thing as "your token is invalid" — only the
        // latter should sign the user out. Otherwise a brief outage would
        // force everyone to log back in for no reason.
        if (isNetworkOrServerError(error)) {
          setStatus('offline')
          return
        }
        tokenStorage.clear()
        setStatus('guest')
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [bootstrapAttempt])

  const login = useCallback(async (username: string, password: string) => {
    const response = await authApi.login({ username, password })
    tokenStorage.setTokens(response.access, response.refresh)

    // Re-verify against `/me/` rather than trusting the login payload alone —
    // the same check every reload does, so both paths can never disagree.
    const me = await authApi.me()
    if (!isEligibleUser(me)) {
      tokenStorage.clear()
      setStatus('guest')
      throw new Error(describeIneligibility(me))
    }
    setUser(me)
    setStatus('authenticated')
  }, [])

  const value = useMemo<{
    user: User | null
    status: AuthStatus
    login: typeof login
    logout: typeof logout
    retry: typeof retry
  }>(() => ({ user, status, login, logout, retry }), [user, status, login, logout, retry])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
