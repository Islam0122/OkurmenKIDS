import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { User } from '@/types/auth'

import { PORTAL_APPS, PORTAL_SERVICES, resolveCard, resolveService } from './config'
import { PortalPage } from './PortalPage'

const mockUseAuth = vi.fn()
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

function user(role: User['role']): User {
  return { id: 1, username: 'aibek', email: '', first_name: 'Aibek', last_name: 'Asanov', role, is_verified: true, is_active: true }
}

function LoginProbe() {
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } } | null)?.from
  return <div>Login page, back to {from?.pathname}</div>
}

function renderPortal() {
  return renderWithProviders(
    <Routes>
      <Route path="/portal" element={<PortalPage />} />
      <Route path="/login" element={<LoginProbe />} />
      <Route path="/schedule" element={<div>Schedule site</div>} />
    </Routes>,
    { route: '/portal' },
  )
}

// Every role of `UserRole` (types/auth.ts) — the feedback card must not depend on it.
const ROLES: User['role'][] = [
  'admin', 'teacher', 'team_lead', 'assistant', 'accountant', 'director',
  'dop', 'rop', 'operations_director', 'hr_manager', 'sales_manager', 'marketing',
]

const card = (id: string) => document.querySelector(`[data-app="${id}"]`)
const service = (id: string) => document.querySelector(`[data-service="${id}"]`)

describe('OKURMEN DIGITAL portal', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mockUseAuth.mockReturnValue({ user: null, status: 'guest', logout: vi.fn() })
  })

  it('shows all seven applications to a guest, with a login button', () => {
    renderPortal()
    expect(screen.getByRole('heading', { name: /welcome to okurmenkids digital/i })).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Academy applications' })).getAllByRole('listitem')).toHaveLength(7)
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login')
  })

  it('opens the known external applications in a new tab', () => {
    renderPortal()
    expect(card('training')).toHaveAttribute('href', 'https://training.okurmenkids.com/')
    expect(card('training')).toHaveAttribute('target', '_blank')
    expect(card('training')).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('routes internal applications through React Router', async () => {
    renderPortal()
    expect(card('schedule')).toHaveAttribute('href', '/schedule')
    expect(card('programs')).toHaveAttribute('href', '/portal/programs')
    // «Итоги месяца» is a route of this same build, not an old deployment.
    expect(card('performance')).toHaveAttribute('href', '/monthly-performance')
    expect(card('performance')).not.toHaveAttribute('target')
    expect(card('leaderboard')).toHaveAttribute('href', '/leaderboard')
    expect(card('news')).toHaveAttribute('href', '/news')
    await userEvent.click(card('schedule') as HTMLElement)
    expect(screen.getByText('Schedule site')).toBeInTheDocument()
  })

  it('sends a guest to the login page for protected apps and remembers the app', async () => {
    renderPortal()
    await userEvent.click(card('lms') as HTMLElement)
    expect(screen.getByText('Login page, back to /app/dashboard')).toBeInTheDocument()
  })

  it('opens an app with its number key', async () => {
    renderPortal()
    await userEvent.keyboard('3')
    expect(screen.getByText('Schedule site')).toBeInTheDocument()
  })

  it('shows the profile and opens protected apps directly when signed in', () => {
    mockUseAuth.mockReturnValue({ user: user('teacher'), status: 'authenticated', logout: vi.fn() })
    renderPortal()
    expect(screen.getAllByText('Aibek Asanov').length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument()
    expect(card('lms')).toHaveAttribute('href', '/app/dashboard')
    expect(card('news')).toHaveAttribute('href', '/news')
  })

  it('sends roles without the LMS to their own cabinet; public news stays open to everyone', () => {
    mockUseAuth.mockReturnValue({ user: user('accountant'), status: 'authenticated', logout: vi.fn() })
    renderPortal()
    expect(card('news')).toHaveAttribute('href', '/news')
    expect(document.querySelectorAll('[data-app]')).toHaveLength(7)
    expect(card('lms')).toHaveAttribute('href', '/accounting')
  })

  it('opens public News for a guest without the login page', () => {
    renderPortal()
    expect(card('news')).toHaveAttribute('href', '/news')
    expect(card('news')?.getAttribute('aria-label')).not.toContain('sign in required')
  })

  it('switches the language and remembers it', async () => {
    renderPortal()
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'ru')
    expect(screen.getByRole('heading', { name: /добро пожаловать в okurmenkids digital/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Войти' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('ru')
    expect(window.localStorage.getItem('okurmen-digital:lang')).toBe('ru')

    await userEvent.selectOptions(screen.getByLabelText('Язык'), 'kg')
    expect(screen.getByRole('link', { name: 'Кирүү' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('ky')
  })

  it('opens About from the header and closes it with Escape, returning focus', async () => {
    renderPortal()
    const about = screen.getAllByRole('button', { name: 'About' })[0]
    await userEvent.click(about)
    const dialog = screen.getByRole('dialog', { name: 'About OkurmenKids Digital' })
    expect(within(dialog).getByText('15.09.2026')).toBeInTheDocument()
    expect(within(dialog).getAllByText('Islam Duishobaev').length).toBeGreaterThan(0)
    expect(within(dialog).getByText('PostgreSQL')).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Our Mission' })).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(about).toHaveFocus()
  })

  it('opens Help and closes it by clicking outside; number keys do nothing while it is open', async () => {
    renderPortal()
    await userEvent.click(screen.getAllByRole('button', { name: 'Help' })[0])
    expect(screen.getByRole('dialog', { name: 'Help' })).toBeInTheDocument()
    await userEvent.keyboard('3')
    expect(screen.queryByText('Schedule site')).not.toBeInTheDocument()

    await userEvent.click(screen.getByTestId('modal-backdrop'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('opens Privacy from the footer and closes it with the close button', async () => {
    renderPortal()
    await userEvent.click(screen.getByRole('button', { name: 'Privacy' }))
    const dialog = screen.getByRole('dialog', { name: 'Privacy' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('shows the four «More from Okurmen» services without inventing URLs', () => {
    renderPortal()
    expect(screen.getByRole('heading', { name: 'More from Okurmen' })).toBeInTheDocument()
    // Student Projects: the public gallery of this build — never the login page.
    expect(service('projects')).toHaveAttribute('href', '/projects')
    expect(service('projects')).not.toHaveAttribute('target')
    // Careers: the public careers site of this build, in a new tab.
    expect(service('careers')).toHaveAttribute('href', '/careers')
    expect(service('careers')).toHaveAttribute('target', '_blank')
    // Our website: the public website on its production domain, in a new tab.
    expect(service('website')).toHaveAttribute('href', 'https://okurmenkids.com/')
    expect(service('website')).toHaveAttribute('target', '_blank')
    expect(service('website')).toHaveAttribute('rel', 'noopener noreferrer')
    // Feedback: the public website's testimonials page (published reviews only), in a new tab.
    expect(service('feedback')).toHaveAttribute('href', 'https://okurmenkids.com/testimonials')
    expect(service('feedback')).toHaveAttribute('target', '_blank')
    expect(service('feedback')).toHaveAttribute('rel', 'noopener noreferrer')
    expect(service('feedback')).not.toHaveAttribute('aria-disabled')
  })

  it('opens the public gallery and the public testimonials for a signed-in admin', () => {
    mockUseAuth.mockReturnValue({ user: user('admin'), status: 'authenticated', logout: vi.fn() })
    renderPortal()
    expect(service('projects')).toHaveAttribute('href', '/projects')
    expect(service('feedback')).toHaveAttribute('href', 'https://okurmenkids.com/testimonials')
    expect(service('feedback')).toHaveAttribute('target', '_blank')
  })

  it('sends every role — and guests — to the same public testimonials page', () => {
    const feedback = PORTAL_SERVICES.find((item) => item.id === 'feedback')!
    const expected = { kind: 'open', href: 'https://okurmenkids.com/testimonials', external: true }
    for (const role of ROLES) {
      expect(resolveService(feedback, user(role))).toEqual(expected)
    }
    expect(resolveService(feedback, null)).toEqual(expected)
  })

  it('lets VITE_PORTAL_FEEDBACK_URL override the testimonials destination', async () => {
    vi.stubEnv('VITE_PORTAL_FEEDBACK_URL', 'https://example.org/reviews')
    vi.resetModules()
    try {
      const { PORTAL_SERVICES: services } = await import('./config')
      expect(services.find((item) => item.id === 'feedback')!.href).toBe('https://example.org/reviews')
    } finally {
      vi.unstubAllEnvs()
      vi.resetModules()
    }
  })

  it('shows Student Projects to every role, signed in or not', () => {
    const projects = PORTAL_SERVICES.find((item) => item.id === 'projects')!
    for (const role of ['accountant', 'teacher', 'operations_director'] as const) {
      expect(resolveService(projects, user(role))).toEqual({ kind: 'open', href: '/projects', external: false })
    }
    expect(resolveService(projects, null)).toEqual({ kind: 'open', href: '/projects', external: false })
  })

  it('carries the OKURMENKIDS DIGITAL brand in the header, footer, About and the document title', async () => {
    renderPortal()
    expect(screen.getAllByText('OKURMENKIDS', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('DIGITAL')[0]).toHaveClass('text-pd-green')
    expect(screen.getAllByText('ОБРАЗОВАТЕЛЬНАЯ ЭКОСИСТЕМА').length).toBeGreaterThan(0)
    expect(screen.getByText('© 2026 OkurmenKids Digital. All rights reserved.')).toBeInTheDocument()
    expect(screen.getByText('Created by Islam Duishobaev.')).toBeInTheDocument()
    expect(document.title).toBe('OkurmenKids Digital — Образовательная экосистема')

    await userEvent.click(screen.getAllByRole('button', { name: 'About' })[0])
    const dialog = screen.getByRole('dialog', { name: 'About OkurmenKids Digital' })
    expect(within(dialog).getByText('© 2026 OkurmenKids Digital. All rights reserved.')).toBeInTheDocument()
    expect(within(dialog).getByText('ОБРАЗОВАТЕЛЬНАЯ ЭКОСИСТЕМА')).toBeInTheDocument()
  })

  it('treats an unconfigured destination as unavailable instead of inventing a URL', () => {
    const app = { ...PORTAL_APPS[0], href: null }
    expect(resolveCard(app, null)).toEqual({ kind: 'unavailable' })
  })
})
