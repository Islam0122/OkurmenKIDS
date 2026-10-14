import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { publicLeaderboardApi } from '@/api/publicLeaderboard'
import type { BoardParams } from '@/api/publicLeaderboard'

/** How often an open page re-reads the leaderboard (plus on window focus). */
export const LEADERBOARD_REFRESH_MS = 2 * 60_000
export const LEADERBOARD_PAGE_SIZE = 20

export function useLeaderboardMeta() {
  return useQuery({ queryKey: ['public-leaderboard', 'meta'], queryFn: publicLeaderboardApi.meta, staleTime: 5 * 60_000 })
}

/** Students, page by page («Показать ещё»). */
export function useStudentBoard(params: Omit<BoardParams, 'page'>, enabled = true) {
  return useInfiniteQuery({
    queryKey: ['public-leaderboard', 'students', params],
    queryFn: ({ pageParam }) => publicLeaderboardApi.students({ page_size: LEADERBOARD_PAGE_SIZE, ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.num_pages ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
    refetchInterval: LEADERBOARD_REFRESH_MS,
    refetchOnWindowFocus: true,
    enabled,
  })
}

export function useGroupBoard(params: Omit<BoardParams, 'page' | 'group'>, enabled = true) {
  return useInfiniteQuery({
    queryKey: ['public-leaderboard', 'groups', params],
    queryFn: ({ pageParam }) => publicLeaderboardApi.groups({ page_size: LEADERBOARD_PAGE_SIZE, ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.num_pages ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
    refetchInterval: LEADERBOARD_REFRESH_MS,
    refetchOnWindowFocus: true,
    enabled,
  })
}
