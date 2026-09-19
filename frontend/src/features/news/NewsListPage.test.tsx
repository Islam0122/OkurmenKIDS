import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NewsListPage } from '@/features/news/NewsListPage'
import { buildNews, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

const mockUseNewsList = vi.fn()
const mockMutate = vi.fn()
vi.mock('@/hooks/useNews', () => ({
  useNewsList: () => mockUseNewsList(),
  useMarkNewsRead: () => ({ mutate: mockMutate, isPending: false }),
}))

describe('NewsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows unread news as highlighted and marks it read on click', async () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: paginated([buildNews({ id: 7, title: 'В офисе не будет света', is_read: false })]),
    })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('Непрочитано')).toBeInTheDocument()

    await userEvent.click(screen.getByText('В офисе не будет света'))

    await waitFor(() => expect(mockMutate).toHaveBeenCalledWith(7))
  })

  it('shows read news with a checkmark and does not re-mark it', async () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: paginated([buildNews({ id: 8, title: 'Уже прочитано', is_read: true })]),
    })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('✓ Прочитано')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Уже прочитано'))
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('shows the empty state when there is no active news', () => {
    mockUseNewsList.mockReturnValue({ isPending: false, isError: false, refetch: vi.fn(), data: paginated([]) })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('Новостей пока нет')).toBeInTheDocument()
  })
})
