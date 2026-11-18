import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { PortalLesson, PortalMe, PortalStudent } from '@/types/studentPortal'

vi.mock('@/api/studentPortal', () => ({
  studentPortalApi: { me: vi.fn(), schedule: vi.fn() },
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 9, role: 'student_parent', username: 'aibek.asanov' }, logout: vi.fn() }),
}))

import { studentPortalApi } from '@/api/studentPortal'

import { StudentPortalLayout } from './StudentPortalLayout'
import { StudentSchedulePage } from './pages/SchedulePage'
import { isoDate } from './ui'

const student: PortalStudent = {
  id: 1, first_name: 'Айбек', last_name: 'Асанов', full_name: 'Айбек Асанов', photo: null, birth_date: null, status: 'active',
  group: { id: 1, name: 'Prog SOFT 1' }, course: { id: 1, name: 'Python' }, branch: null, enrollment_date: '2026-09-01',
}
const ME: PortalMe = { login: 'aibek.asanov', must_change_password: false, can_view_payments: true, students: [student] }

const today = isoDate(new Date())

function lesson(id: number, extra: Partial<PortalLesson>): PortalLesson {
  return {
    id, date: today, start: '00:00', end: '00:01', subject: { id: 1, name: 'Python' }, teacher: { id: 7, name: 'Islam Duishobaev' },
    group: { id: 1, name: 'Prog SOFT 1' }, course: null, room: { id: 1, name: '1' }, branch: null, topic: 'Функции', lesson_number: 85,
    numbering: { number: 29, month: 3, lesson: 5, per_month: 12, label: '3 месяц · 5 урок' },
    status: 'completed', cancellation_reason: '', attendance: 'present', ...extra,
  }
}

const TODAY_LESSONS = [
  lesson(1, {}),
  lesson(2, { start: '00:01', end: '00:02', topic: 'Циклы', numbering: null, attendance: 'absent' }),
  lesson(3, { start: '23:58', end: '23:59', subject: { id: 2, name: 'English' }, topic: 'Present Simple', status: 'scheduled', attendance: null, numbering: null }),
  lesson(4, { start: '23:59', end: null, subject: { id: 3, name: 'Soft Skills' }, topic: 'Команда', status: 'cancelled', attendance: null, cancellation_reason: 'Праздник', numbering: null }),
]

function renderSchedule() {
  return renderWithProviders(
    <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="schedule" element={<StudentSchedulePage />} /></Route></Routes>,
    { route: '/student/schedule' },
  )
}

describe('Student schedule page (redesign)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    // The real endpoint's shape: only lessons inside [start, end].
    vi.mocked(studentPortalApi.schedule).mockImplementation(async (_id, start, end) => ({
      start, end, lessons: today >= start && today <= end ? TODAY_LESSONS : [],
    }))
  })

  it('counts the statistics from the lessons the API returned', async () => {
    renderSchedule()
    expect(await screen.findByRole('heading', { name: 'Моё расписание' })).toBeInTheDocument()
    const statsBox = await screen.findByRole('region', { name: 'Итоги периода' })
    const value = (label: string) => within(statsBox).getByText(label).parentElement!.parentElement!.querySelector('p.text-\\[28px\\]')!.textContent
    expect(value('Всего уроков')).toBe('3') // the cancelled lesson is not counted…
    expect(within(statsBox).getByText(/Отменено: 1/)).toBeInTheDocument() // …but is mentioned
    expect(value('Проведено')).toBe('2')
    expect(value('Предстоит')).toBe('1')
    expect(value('Пропуски')).toBe('1') // attendance «absent»
  })

  it('shows today on a timeline with full lesson details and statuses', async () => {
    renderSchedule()
    const todayBox = await screen.findByRole('region', { name: 'Сегодняшние занятия' })
    await waitFor(() => expect(within(todayBox).getAllByRole('article')).toHaveLength(4))
    expect(within(todayBox).getByText('Урок 29 ·')).toBeInTheDocument()
    expect(within(todayBox).getByText('3 месяц · 5 урок')).toBeInTheDocument()
    expect(within(todayBox).getAllByText('Islam Duishobaev').length).toBeGreaterThan(0)
    expect(within(todayBox).getAllByText('Каб. 1').length).toBeGreaterThan(0)
    expect(within(todayBox).getAllByText('Проведено').length).toBe(1)
    expect(within(todayBox).getByText('Пропущено')).toBeInTheDocument()
    expect(within(todayBox).getByText('Запланировано')).toBeInTheDocument()
    expect(within(todayBox).getByText('Отменено')).toBeInTheDocument()
    expect(within(todayBox).getByText('Причина: Праздник')).toBeInTheDocument()
    expect(within(todayBox).getByLabelText(/^Сейчас \d\d:\d\d$/)).toBeInTheDocument()
  })

  it('navigates weeks and comes back with «Сегодня»', async () => {
    renderSchedule()
    await screen.findByRole('region', { name: 'Итоги периода' })
    const user = userEvent.setup()
    const todayBtn = screen.getByRole('button', { name: 'Сегодня' })
    expect(todayBtn).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Вперёд' }))
    expect(await screen.findByText('На этой неделе занятий нет')).toBeInTheDocument()
    const [, start, end] = vi.mocked(studentPortalApi.schedule).mock.lastCall!
    expect((new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86_400_000).toBe(6)
    expect(start > today).toBe(true)
    expect(screen.getAllByRole('button', { name: 'Сегодня' })).toHaveLength(2) // toolbar + the empty state's shortcut
    await user.click(screen.getAllByRole('button', { name: 'Сегодня' })[0])
    await waitFor(() => expect(screen.getByRole('button', { name: 'Сегодня' })).toBeDisabled())
    expect(screen.queryByText('На этой неделе занятий нет')).not.toBeInTheDocument()
  })

  it('switches to the month grid and offers the nearest day with lessons', async () => {
    renderSchedule()
    await screen.findByRole('region', { name: 'Итоги периода' })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Месяц' }))
    await waitFor(() => {
      const [, start, end] = vi.mocked(studentPortalApi.schedule).mock.lastCall!
      expect(new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()).toBeGreaterThan(20 * 86_400_000)
    })
    const now = new Date()
    const other = new Date(now.getFullYear(), now.getMonth(), now.getDate() === 1 ? 2 : 1)
    const [y, m, d] = isoDate(other).split('-')
    await user.click(await screen.findByRole('button', { name: `${d}.${m}.${y}: занятий — 0` }))
    expect(await screen.findByText('На этот день занятий нет')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ближайший день с уроками' }))
    // today's lessons now show both on the timeline and under the month grid
    await waitFor(() => expect(screen.getAllByText('Present Simple')).toHaveLength(2))
    expect(screen.queryByText('На этот день занятий нет')).not.toBeInTheDocument()
  })

  it('speaks Kyrgyz', async () => {
    window.localStorage.setItem('okk-student-portal-lang', 'ky')
    renderSchedule()
    expect(await screen.findByRole('heading', { name: 'Менин сабак тартибим' })).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Бүгүнкү сабактар' })).toBeInTheDocument()
  })
})
