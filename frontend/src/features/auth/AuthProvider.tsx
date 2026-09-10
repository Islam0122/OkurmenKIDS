import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { authApi } from '@/api/auth'
import { registerSessionExpiredHandler } from '@/api/client'
import { tokenStorage } from '@/lib/tokenStorage'
import type { User } from '@/types/auth'

import { AuthContext, type AuthStatus } from './AuthContext'

/** Mirrors the backend's own login gate (see `LoginSerializer.validate`) so the UI never shows an "authenticated" screen the API would reject anyway. */
function isEligibleTeacher(user: User): boolean {
  return user.role === 'teacher' && user.is_verified && user.is_active
}

function describeIneligibility(user: User): string {
  if (user.role !== 'teacher') return 'Этот кабинет доступен только тренерам.'
  if (!user.is_verified) return 'Аккаунт ещё не подтверждён администратором.'
  return 'Аккаунт деактивирован.'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  const logout = useCallback(() => {
    tokenStorage.clear()
    queryClient.clear()
    setUser(null)
    setStatus('guest')
  }, [queryClient])

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
        setStatus(isEligibleTeacher(me) ? 'authenticated' : 'forbidden')
      } catch {
        if (cancelled) return
        tokenStorage.clear()
        setStatus('guest')
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const response = await authApi.login({ username, password })
    tokenStorage.setTokens(response.access, response.refresh)

    // Re-verify against `/me/` rather than trusting the login payload alone —
    // the same check every reload does, so both paths can never disagree.
    const me = await authApi.me()
    if (!isEligibleTeacher(me)) {
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
  }>(() => ({ user, status, login, logout }), [user, status, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
