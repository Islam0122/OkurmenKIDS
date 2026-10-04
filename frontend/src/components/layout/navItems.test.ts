import { describe, expect, it } from 'vitest'

import { canOpen, getMobilePrimaryNav, getNavItems } from './navItems'

const labels = (role: Parameters<typeof getNavItems>[0]) => getNavItems(role).map((item) => item.label)

describe('navigation by role', () => {
  it('gives a Team Lead the academy-wide sections', () => {
    expect(labels('team_lead')).toEqual([
      'Dashboard',
      'Тренеры',
      'Группы',
      'Студенты',
      'Сессии',
      'Посещаемость',
      'ДЗ',
      'Тесты',
      'KPI',
      'Контроль',
      'Аналитика',
      'Отчёты',
    ])
  })

  it('never shows a Team Lead trainer-only or management sections', () => {
    const team = labels('team_lead')
    for (const hidden of ['Мои отчёты', 'Стипендии', 'Новости', 'Users', 'Roles', 'Permissions', 'Settings']) {
      expect(team).not.toContain(hidden)
    }
    expect(canOpen('team_lead', '/app/scholarships')).toBe(false)
    expect(canOpen('team_lead', '/app/trainers/5')).toBe(true)
  })

  it('keeps the Trainer menu unchanged', () => {
    expect(labels('teacher')).toEqual([
      'Сегодня',
      'Расписание',
      'Мои группы',
      'Экзамены',
      'KPI',
      'Контроль',
      'Мои отчёты',
      'Стипендии',
      'Новости',
    ])
  })

  it('has five phone tabs for a Team Lead', () => {
    expect(getMobilePrimaryNav('team_lead').map((item) => item.to)).toEqual([
      '/app/dashboard',
      '/app/trainers',
      '/app/groups',
      '/app/analytics',
      '/app/profile',
    ])
  })
})
