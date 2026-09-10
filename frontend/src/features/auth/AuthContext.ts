import { createContext } from 'react'

import type { User } from '@/types/auth'

export type AuthStatus = 'loading' | 'guest' | 'forbidden' | 'authenticated'

export interface AuthContextValue {
  user: User | null
  status: AuthStatus
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
