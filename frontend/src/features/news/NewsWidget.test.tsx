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
  it('renders the latest news items linking to their own detail page, and "Все →" to the full feed', () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      data: paginated([buildNews({ id: 1, title: 'Завтра занятий нет' })]),
    })

    renderWithProviders(<NewsWidget />, { route: '/app/dashboard' })

    expect(screen.getByRole('link', { name: /Завтра занятий нет/ })).toHaveAttribute('href', '/app/news/1')
    expect(screen.getByRole('link', { name: 'Все →' })).toHaveAttribute('href', '/app/news')
  })

  it('shows at most 3 items even when more are available', () => {
    mockUseNewsList.mockReturnValue({
      isPending: false,
      data: paginated([1, 2, 3, 4, 5].map((id) => buildNews({ id, title: `Новость ${id}` }))),
    })

    renderWithProviders(<NewsWidget />, { route: '/app/dashboard' })

    expect(screen.getAllByRole('link').filter((link) => link.textContent?.includes('Новость'))).toHaveLength(3)
  })

  it('shows the compact empty state when there is no active news', () => {
    mockUseNewsList.mockReturnValue({ isPending: false, data: paginated([]) })

    renderWithProviders(<NewsWidget />, { route: '/app/dashboard' })

    expect(screen.getByText('Новостей пока нет')).toBeInTheDocument()
  })
})
