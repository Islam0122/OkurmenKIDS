import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { newsApi } from '@/api/news'

export function useNewsList() {
  return useQuery({
    queryKey: ['news', 'list'],
    queryFn: () => newsApi.list(),
  })
}

export function useUnreadNewsCount() {
  return useQuery({
    queryKey: ['news', 'unread-count'],
    queryFn: () => newsApi.unreadCount(),
  })
}

export function useMarkNewsRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: number) => newsApi.markRead(id),
    onSuccess: () => {
      // Covers both ['news', 'list'] and ['news', 'unread-count'].
      void queryClient.invalidateQueries({ queryKey: ['news'] })
    },
  })
}
