import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

import { getNavItems } from './navItems'
import { Sidebar } from './Sidebar'
import { activeLink, teamLeadLinks, TEAM_LEAD_SECTIONS } from './teamLeadNav'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'team_lead' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

const EMOJI = /\p{Extended_Pictographic}/u

describe('Team Lead navigation config', () => {
  it('keeps every existing Team Lead page reachable — no page lost, no fake route', () => {
    const paths = new Set(teamLeadLinks().map((link) => link.to.split('?')[0]))
    for (const item of getNavItems('team_lead')) expect(paths, item.to).toContain(item.to)
    for (const path of paths) expect(getNavItems('team_lead').some((item) => item.to === path) || path === '/app/profile', path).toBe(true)
  })

  it('is Russian, without emoji, in the Team Lead order', () => {
    expect(TEAM_LEAD_SECTIONS.map((s) => s.label)).toEqual(['Главная', 'Расписание', 'Аналитика', 'Группы', 'Тренеры', 'Студенты', 'Тесты', 'KPI', 'Отчёты'])
    for (const label of [...TEAM_LEAD_SECTIONS.map((s) => s.label), ...teamLeadLinks().map((l) => l.label)]) {
      expect(label).not.toMatch(EMOJI)
      expect(label.replace('KPI', '')).not.toMatch(/[A-Za-z]/)
    }
  })

  it('lights up exactly one link, query parameters included', () => {
    expect(activeLink('/app/analytics', '')).toBe('/app/analytics')
    expect(activeLink('/app/analytics', '?tab=groups')).toBe('/app/analytics?tab=groups')
    expect(activeLink('/app/analytics', '?tab=tests')).toBe('/app/analytics?tab=tests')
    expect(activeLink('/app/groups/12', '')).toBe('/app/groups')
    expect(activeLink('/app/groups', '?status=completed')).toBe('/app/groups?status=completed')
    expect(activeLink('/app/worklog', '?tab=reports&kind=weekly')).toBe('/app/worklog?tab=reports&kind=weekly')
    expect(activeLink('/app/worklog/reports/3', '')).toBe('/app/worklog')
    expect(activeLink('/app/unknown', '')).toBeNull()
  })
})

describe('Team Lead sidebar', () => {
  beforeEach(() => window.localStorage.clear())

  it('opens the section of the current page, toggles sections and marks the active page', () => {
    renderWithProviders(<Sidebar />, { route: '/app/analytics?tab=groups' })
    const nav = screen.getByRole('navigation', { name: 'Основная навигация' })
    expect(within(nav).getByRole('link', { name: 'По группам' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).queryByRole('link', { name: 'Все тренеры' })).not.toBeInTheDocument()

    fireEvent.click(within(nav).getByRole('button', { name: 'Тренеры' }))
    expect(within(nav).getByRole('link', { name: 'Все тренеры' })).toHaveAttribute('href', '/app/trainers')
    fireEvent.click(within(nav).getByRole('button', { name: 'Тренеры' }))
    expect(within(nav).queryByRole('link', { name: 'Все тренеры' })).not.toBeInTheDocument()
  })

  it('collapses to icons with names as tooltips, and remembers it', () => {
    renderWithProviders(<Sidebar />, { route: '/app/dashboard' })
    fireEvent.click(screen.getByRole('button', { name: 'Свернуть меню' }))
    const tests = screen.getByRole('link', { name: 'Тесты' })
    expect(tests).toHaveAttribute('title', 'Тесты')
    expect(tests).toHaveAttribute('href', '/app/tests')
    expect(screen.queryByText('Главная')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('okurmen.sidebar.collapsed')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'Развернуть меню' }))
    expect(screen.getByText('Главная')).toBeInTheDocument()
  })
})
