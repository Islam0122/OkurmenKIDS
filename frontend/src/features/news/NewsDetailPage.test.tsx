import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NewsDetailPage } from '@/features/news/NewsDetailPage'
import { buildNews } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

const mockUseNewsDetail = vi.fn()
const mockMutate = vi.fn()
vi.mock('@/hooks/useNews', () => ({
  useNewsDetail: (id: number) => mockUseNewsDetail(id),
  useMarkNewsRead: () => ({ mutate: mockMutate, isPending: false }),
}))

function renderNewsDetail(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/news" element={<div>News list page</div>} />
      <Route path="/app/news/:id" element={<NewsDetailPage />} />
    </Routes>,
    { route },
  )
}

describe('NewsDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the full News and marks it read exactly once', async () => {
    mockUseNewsDetail.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: buildNews({ id: 42, title: 'Завтра выходной', text: 'Завтра занятий не будет.', is_read: false }),
    })

    renderNewsDetail('/app/news/42')

    expect(screen.getByRole('heading', { name: 'Завтра выходной' })).toBeInTheDocument()
    expect(screen.getByText('Завтра занятий не будет.')).toBeInTheDocument()

    await waitFor(() => expect(mockMutate).toHaveBeenCalledWith(42))
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('does not call mark-read again for an already-read News', () => {
    mockUseNewsDetail.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: buildNews({ id: 43, is_read: true }),
    })

    renderNewsDetail('/app/news/43')

    expect(screen.getByText('✓ Прочитано')).toBeInTheDocument()
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('does not repeat the title as a separate description when text matches it', () => {
    mockUseNewsDetail.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: buildNews({ id: 44, title: 'Завтра выходной', text: 'Завтра выходной', is_read: true }),
    })

    renderNewsDetail('/app/news/44')

    expect(screen.getAllByText('Завтра выходной')).toHaveLength(1)
  })

  it('has a back link to the full feed', () => {
    mockUseNewsDetail.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: buildNews({ id: 45, is_read: true }),
    })

    renderNewsDetail('/app/news/45')

    expect(screen.getByRole('link', { name: /К новостям/ })).toHaveAttribute('href', '/app/news')
  })
})
