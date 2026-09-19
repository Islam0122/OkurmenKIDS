import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { NewsBell } from '@/components/layout/NewsBell'
import { renderWithProviders } from '@/test/testUtils'

const mockUseUnreadNewsCount = vi.fn()
vi.mock('@/hooks/useNews', () => ({
  useUnreadNewsCount: () => mockUseUnreadNewsCount(),
}))

describe('NewsBell', () => {
  it('shows no badge when there is nothing unread', () => {
    mockUseUnreadNewsCount.mockReturnValue({ data: { count: 0 } })
    renderWithProviders(<NewsBell />)
    expect(screen.getByRole('link', { name: 'Новости' })).toBeInTheDocument()
  })

  it('shows the unread count as a badge', () => {
    mockUseUnreadNewsCount.mockReturnValue({ data: { count: 3 } })
    renderWithProviders(<NewsBell />)
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Новости — 3 непрочитано' })).toBeInTheDocument()
  })
})
