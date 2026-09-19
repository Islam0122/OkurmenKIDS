import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { NewsWidget } from '@/features/news/NewsWidget'
import { buildNews, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

const mockUseNewsList = vi.fn()
vi.mock('@/hooks/useNews', () => ({
  useNewsList: () => mockUseNewsList(),
}))

describe('NewsWidget', () => {
  it('renders the latest news items with a link to the full feed', () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      data: paginated([buildNews({ id: 1, title: 'Завтра занятий нет' })]),
    })

    renderWithProviders(<NewsWidget />, { route: '/app/dashboard' })

    expect(screen.getByText('Завтра занятий нет')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Все →' })).toHaveAttribute('href', '/app/news')
  })

  it('shows the empty state when there is no active news', () => {
    mockUseNewsList.mockReturnValue({ isPending: false, data: paginated([]) })

    renderWithProviders(<NewsWidget />, { route: '/app/dashboard' })

    expect(screen.getByText('Новостей пока нет')).toBeInTheDocument()
  })
})
