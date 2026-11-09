import { createContext } from 'react'

import type { User } from '@/types/auth'

export type AuthStatus = 'loading' | 'guest' | 'forbidden' | 'authenticated' | 'offline'

export interface AuthContextValue {
  user: User | null
  status: AuthStatus
  login: (username: string, password: string) => Promise<User>
  /** The user's own «Выйти»: clears the session and sends them to the public portal. */
  logout: () => void
  retry: () => void
  /** True after an explicit logout (until the next login) — protected pages
   * then lead to /portal, not /login. An expired session leaves it false, so
   * the user is asked to sign in again and returns to the same page. */
  signedOut?: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)
