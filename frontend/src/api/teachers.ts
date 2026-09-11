import { apiClient } from '@/api/client'
import type { Teacher } from '@/types/academy'

export const teachersApi = {
  /** `GET /trainers/me/` — the logged-in Teacher's own profile (read-only). */
  me: (): Promise<Teacher> => apiClient.get<Teacher>('/trainers/me/').then((r) => r.data),
}
