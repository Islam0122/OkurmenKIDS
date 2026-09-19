import { apiClient } from '@/api/client'
import type { News, UnreadNewsCount } from '@/types/news'
import type { Paginated } from '@/types/common'

export const newsApi = {
  list: (): Promise<Paginated<News>> => apiClient.get<Paginated<News>>('/teacher/news/').then((r) => r.data),

  unreadCount: (): Promise<UnreadNewsCount> =>
    apiClient.get<UnreadNewsCount>('/teacher/news/unread-count/').then((r) => r.data),

  /** Idempotent — safe to call again for an already-read item. */
  markRead: (id: number): Promise<{ success: boolean }> =>
    apiClient.post<{ success: boolean }>(`/teacher/news/${id}/read/`).then((r) => r.data),
}
