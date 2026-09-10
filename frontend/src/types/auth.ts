export type UserRole = 'admin' | 'teacher'

/** `apps.users.serializers.UserSerializer` — read-only in full. */
export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
  is_verified: boolean
  is_active: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

/** `POST /api/v1/users/auth/login/` */
export interface LoginResponse {
  access: string
  refresh: string
  user: User
}

/** `POST /api/v1/users/auth/refresh/` — SimpleJWT with ROTATE_REFRESH_TOKENS,
 * so a fresh refresh token comes back on every call and must be persisted. */
export interface RefreshResponse {
  access: string
  refresh: string
}
