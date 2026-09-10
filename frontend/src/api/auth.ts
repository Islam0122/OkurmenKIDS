import { apiClient } from '@/api/client'
import type { LoginRequest, LoginResponse, User } from '@/types/auth'

export const authApi = {
  login: (payload: LoginRequest): Promise<LoginResponse> =>
    apiClient.post<LoginResponse>('/users/auth/login/', payload).then((r) => r.data),

  me: (): Promise<User> => apiClient.get<User>('/users/auth/me/').then((r) => r.data),
}
