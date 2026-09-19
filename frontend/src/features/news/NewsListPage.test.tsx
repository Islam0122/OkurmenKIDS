import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NewsListPage } from '@/features/news/NewsListPage'
import { buildNews, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

const mockUseNewsList = vi.fn()
vi.mock('@/hooks/useNews', () => ({
  useNewsList: () => mockUseNewsList(),
}))

describe('NewsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows unread news as highlighted, linking through to its detail page', () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: paginated([buildNews({ id: 7, title: 'В офисе не будет света', is_read: false })]),
    })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('Новое')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /В офисе не будет света/ })).toHaveAttribute('href', '/app/news/7')
  })

  it('shows read news with a checkmark', () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: paginated([buildNews({ id: 8, title: 'Уже прочитано', is_read: true })]),
    })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('✓ Прочитано')).toBeInTheDocument()
  })

  it('filters down to unread items only', async () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: paginated([
        buildNews({ id: 1, title: 'Прочитанная новость', is_read: true }),
        buildNews({ id: 2, title: 'Непрочитанная новость', is_read: false }),
      ]),
    })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('Прочитанная новость')).toBeInTheDocument()
    expect(screen.getByText('Непрочитанная новость')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Непрочитанные · 1/ }))

    expect(screen.queryByText('Прочитанная новость')).not.toBeInTheDocument()
    expect(screen.getByText('Непрочитанная новость')).toBeInTheDocument()
  })

  it('shows the empty state when there is no active news', () => {
    mockUseNewsList.mockReturnValue({ isPending: false, isError: false, refetch: vi.fn(), data: paginated([]) })

    renderWithProviders(<NewsListPage />, { route: '/app/news' })

    expect(screen.getByText('Новостей пока нет')).toBeInTheDocument()
  })
})
