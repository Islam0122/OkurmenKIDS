import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { createTestQueryClient } from '@/test/testUtils'

vi.mock('@/api/homework', () => ({
  homeworkApi: { saveResults: vi.fn().mockResolvedValue([]) },
  homeworkResultsApi: {},
}))

import { useSaveHomeworkResults } from './useHomework'
import { PARENT_REPORT_KEY } from './useLessons'

describe('useSaveHomeworkResults', () => {
  it('invalidates every «Мини-отчёт родителям» — the next opening refetches it', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setDefaultOptions({ queries: { staleTime: 30_000, gcTime: Infinity } })
    // The report of the lesson that checks this homework (lesson 5) — not the
    // homework's own lesson (4) — is the one that changes.
    queryClient.setQueryData([...PARENT_REPORT_KEY, 5], { message: 'old' })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(() => useSaveHomeworkResults(1, 4), { wrapper })

    expect(queryClient.getQueryState([...PARENT_REPORT_KEY, 5])?.isInvalidated).toBe(false)
    await act(() => result.current.mutateAsync([{ student: 1, status: 'submitted', score: 8, comment: '' }]))

    await waitFor(() => expect(queryClient.getQueryState([...PARENT_REPORT_KEY, 5])?.isInvalidated).toBe(true))
  })
})
