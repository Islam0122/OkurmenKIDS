import { useContext } from 'react'

import { AuthContext, type AuthContextValue } from '@/features/auth/AuthContext'

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
