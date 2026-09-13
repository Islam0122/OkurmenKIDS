import { createContext } from 'react'

import type { User } from '@/types/auth'

export type AuthStatus = 'loading' | 'guest' | 'forbidden' | 'authenticated' | 'offline'

export interface AuthContextValue {
  user: User | null
  status: AuthStatus
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  retry: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
