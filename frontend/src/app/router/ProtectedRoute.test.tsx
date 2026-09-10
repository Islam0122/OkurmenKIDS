import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProtectedRoute } from '@/app/router/ProtectedRoute'
import { renderWithProviders } from '@/test/testUtils'

const mockUseAuth = vi.fn()
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

function renderProtected() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<div>Login page</div>} />
      <Route path="/access-denied" element={<div>Access denied page</div>} />
      <Route element={<ProtectedRoute />}>
        <Route path="/app/dashboard" element={<div>Dashboard content</div>} />
      </Route>
    </Routes>,
    { route: '/app/dashboard' },
  )
}

describe('ProtectedRoute', () => {
  it('redirects an unauthenticated visitor to /login', () => {
    mockUseAuth.mockReturnValue({ status: 'guest' })
    renderProtected()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects an ineligible account (wrong role, unverified, or deactivated) to /access-denied instead of any app page', () => {
    mockUseAuth.mockReturnValue({ status: 'forbidden' })
    renderProtected()
    expect(screen.getByText('Access denied page')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('renders the protected content for an eligible teacher', () => {
    mockUseAuth.mockReturnValue({ status: 'authenticated' })
    renderProtected()
    expect(screen.getByText('Dashboard content')).toBeInTheDocument()
  })

  it('shows a loading state instead of any page while the session is being verified', () => {
    mockUseAuth.mockReturnValue({ status: 'loading' })
    renderProtected()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })
})
