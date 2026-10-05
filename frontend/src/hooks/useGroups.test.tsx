import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { createTestQueryClient } from '@/test/testUtils'

vi.mock('@/api/groups', () => ({
  groupsApi: {
    saveProgram: vi.fn().mockResolvedValue({ programs: [] }),
    createProgram: vi.fn().mockResolvedValue({ programs: [] }),
    generateLessons: vi.fn().mockResolvedValue({ created: 0 }),
  },
}))

import { useGenerateLessons, useSaveAcademicProgram } from './useGroups'

const WEEK = ['schedule', { date_from: '2026-10-05', date_to: '2026-10-11' }]

function setup() {
  const queryClient = createTestQueryClient()
  // The app's global 30 s staleTime: without an invalidation the «Расписание»
  // week would keep showing the lessons' old time for half a minute.
  queryClient.setDefaultOptions({ queries: { staleTime: 30_000, gcTime: Infinity } })
  queryClient.setQueryData(WEEK, [{ id: 1, start_time: '10:00:00' }])
  queryClient.setQueryData(['lessons', 'list', {}], { results: [] })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

describe('schedule changes refresh every lesson view', () => {
  it('saving a program (its slots moved the lessons on the server) invalidates the schedule week and lesson lists', async () => {
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useSaveAcademicProgram(1), { wrapper })
    expect(queryClient.getQueryState(WEEK)?.isInvalidated).toBe(false)
    await act(() => result.current.mutateAsync({ programId: 7, payload: { teacher: 1, subject: 1, schedule: [] } }))
    await waitFor(() => expect(queryClient.getQueryState(WEEK)?.isInvalidated).toBe(true))
    expect(queryClient.getQueryState(['lessons', 'list', {}])?.isInvalidated).toBe(true)
  })

  it('«Сгенерировать занятия» invalidates them too', async () => {
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useGenerateLessons(1), { wrapper })
    await act(() => result.current.mutateAsync())
    await waitFor(() => expect(queryClient.getQueryState(WEEK)?.isInvalidated).toBe(true))
  })
})
