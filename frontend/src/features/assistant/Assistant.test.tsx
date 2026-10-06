import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { Options, StudentDetail, StudentRow } from '@/types/assistant'

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    options: vi.fn(),
    students: vi.fn(),
    student: vi.fn(),
    deactivate: vi.fn(),
    transfer: vi.fn(),
    bulk: vi.fn(),
    dashboard: vi.fn(),
    search: vi.fn(),
    createGroup: vi.fn(),
    control: vi.fn(),
    groupHomework: vi.fn(),
    monthlyReport: vi.fn(),
  },
  surveysApi: {},
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, first_name: 'Asel', last_name: 'K', role: 'assistant', username: 'a', email: 'a@a', is_active: true, is_verified: true }, logout: vi.fn() }),
}))

import { assistantApi } from '@/api/assistant'
import { AppLayout } from '@/app/layouts/AppLayout'

import { AssistantActionsProvider } from './actions/AssistantActions'
import { QuickGroupModal } from './actions/QuickGroupModal'
import { CommandPalette } from './layout/CommandPalette'
import { AssistantControlPage } from './pages/ControlPage'
import { AssistantMonthlyReportPage } from './pages/MonthlyReportPage'
import { GroupHomeworkTab } from './records/GroupRecordTabs'
import { AssistantStudentDetailPage } from './pages/StudentDetailPage'
import { AssistantStudentsPage } from './pages/StudentsPage'

const OPTIONS: Options = {
  courses: [{ id: 1, name: 'Python', count_lesson: 20, subjects: [{ id: 1, name: 'Python' }] }],
  teachers: [{ id: 1, name: 'Islam', subjects: [1] }],
  rooms: [],
  groups: [
    { id: 1, name: 'PRO-01', course: 'Python', status: 'active', students_count: 18, max_students: null },
    { id: 2, name: 'PRO-02', course: 'Python', status: 'active', students_count: 16, max_students: null },
  ],
  weekdays: [
    { code: 'mon', label: 'Понедельник', short: 'Пн' }, { code: 'wed', label: 'Среда', short: 'Ср' }, { code: 'fri', label: 'Пятница', short: 'Пт' },
  ],
  deactivation_reasons: [{ value: 'financial_issues', label: 'Финансовые проблемы' }, { value: 'other', label: 'Другая причина' }],
  group_statuses: [],
}

function row(overrides: Partial<StudentRow> = {}): StudentRow {
  return {
    id: 7, first_name: 'Islam', last_name: 'Duishobaev', full_name: 'Islam Duishobaev', phone: '', parent_phone: '',
    group: { id: 1, name: 'PRO-01' }, course: { id: 1, name: 'Python' }, status: 'active', status_display: 'Активен',
    enrollment_date: '2026-09-01', attendance_percent: 90, ...overrides,
  }
}

function detail(overrides: Partial<StudentDetail> = {}): StudentDetail {
  return {
    ...row(), created_at: '2026-09-01T10:00:00Z', teachers: ['Islam'], group_status: 'Активна', schedule: [],
    attendance: { attended: 9, marked: 10, records: [] }, homework: [], exams: [], scholarships: [], surveys: [], history: [],
    ...overrides,
  }
}

describe('Assistant Workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(assistantApi.options).mockResolvedValue(OPTIONS)
  })

  it('sends an Assistant from /app to /assistant', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/app/*" element={<AppLayout />} />
        <Route path="/assistant" element={<p>Assistant home</p>} />
      </Routes>,
      { route: '/app/dashboard' },
    )
    expect(await screen.findByText('Assistant home')).toBeInTheDocument()
  })

  it('deactivates a student from the profile: reason → confirm, never a delete', async () => {
    vi.mocked(assistantApi.student).mockResolvedValue(detail())
    vi.mocked(assistantApi.deactivate).mockResolvedValue(detail({ status: 'withdrawn', status_display: 'Деактивирован' }))
    const user = userEvent.setup()
    renderWithProviders(
      <AssistantActionsProvider>
        <Routes><Route path="/assistant/students/:id" element={<AssistantStudentDetailPage />} /></Routes>
      </AssistantActionsProvider>,
      { route: '/assistant/students/7' },
    )

    await user.click(await screen.findByRole('button', { name: 'Деактивировать' }))
    const dialog = await screen.findByRole('dialog')
    const submit = within(dialog).getByRole('button', { name: 'Деактивировать' })
    expect(submit).toBeDisabled()
    await user.selectOptions(within(dialog).getByLabelText(/Причина/), 'financial_issues')
    await user.click(submit)

    await waitFor(() => expect(assistantApi.deactivate).toHaveBeenCalledWith(7, expect.objectContaining({ reason: 'financial_issues' })))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('«Другая причина» needs a comment before deactivating', async () => {
    vi.mocked(assistantApi.student).mockResolvedValue(detail())
    const user = userEvent.setup()
    renderWithProviders(
      <AssistantActionsProvider>
        <Routes><Route path="/assistant/students/:id" element={<AssistantStudentDetailPage />} /></Routes>
      </AssistantActionsProvider>,
      { route: '/assistant/students/7' },
    )
    await user.click(await screen.findByRole('button', { name: 'Деактивировать' }))
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText(/Причина/), 'other')
    expect(within(dialog).getByRole('button', { name: 'Деактивировать' })).toBeDisabled()
    await user.type(within(dialog).getByLabelText(/Комментарий/), 'Уехал')
    expect(within(dialog).getByRole('button', { name: 'Деактивировать' })).toBeEnabled()
  })

  it('selects students and runs one bulk transfer for all of them', async () => {
    vi.mocked(assistantApi.students).mockResolvedValue(paginated([row(), row({ id: 8, full_name: 'Aida K', first_name: 'Aida', last_name: 'K' })]))
    vi.mocked(assistantApi.bulk).mockResolvedValue({ done: 2, failed: 0, results: [
      { id: 7, name: 'Islam Duishobaev', ok: true }, { id: 8, name: 'Aida K', ok: true },
    ] })
    const user = userEvent.setup()
    renderWithProviders(<AssistantActionsProvider><AssistantStudentsPage /></AssistantActionsProvider>, { route: '/assistant/students' })

    await screen.findAllByText('Islam Duishobaev')
    await user.click(screen.getByLabelText('Выбрать всех на странице'))
    expect(screen.getByText('Выбрано: 2')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Перевести' }))
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText(/Группа/), '2')
    await user.click(within(dialog).getByRole('button', { name: 'Перевести студентов' }))

    await waitFor(() => expect(assistantApi.bulk).toHaveBeenCalledWith(expect.objectContaining({ action: 'transfer', students: [7, 8], group: 2 })))
    expect(await within(dialog).findAllByText('Готово')).toHaveLength(2)
  })

  it('shows an empty state with an add action when there are no students', async () => {
    vi.mocked(assistantApi.students).mockResolvedValue(paginated([]))
    renderWithProviders(<AssistantActionsProvider><AssistantStudentsPage /></AssistantActionsProvider>, { route: '/assistant/students' })
    expect(await screen.findByText('Студентов пока нет')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Студент' }).length).toBeGreaterThan(0)
  })

  it('global search finds a student and opens the profile', async () => {
    vi.mocked(assistantApi.search).mockResolvedValue({
      students: [{ id: 7, name: 'Islam Duishobaev', group: 'PRO-01', status: 'active', status_display: 'Активен' }],
      groups: [{ id: 1, name: 'PRO-01', course: 'Python', status: 'active', status_display: 'Активна' }],
      teachers: [], lessons: [],
    })
    const user = userEvent.setup()
    renderWithProviders(
      <AssistantActionsProvider>
        <Routes>
          <Route path="/assistant" element={<CommandPalette isOpen onClose={() => {}} />} />
          <Route path="/assistant/students/:id" element={<p>Student page</p>} />
        </Routes>
      </AssistantActionsProvider>,
      { route: '/assistant' },
    )
    expect(screen.getByRole('option', { name: /Создать группу/ })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Поиск'), 'islam')
    expect(await screen.findByRole('option', { name: /Islam Duishobaev/ })).toBeInTheDocument()
    expect(screen.getByText('Студенты')).toBeInTheDocument()
    await user.keyboard('{Enter}')
    expect(await screen.findByText('Student page')).toBeInTheDocument()
  })

  it('creates a group in fast mode with trainer, days and time', async () => {
    vi.mocked(assistantApi.students).mockResolvedValue(paginated([row({ id: 9, full_name: 'Aida K' })]))
    vi.mocked(assistantApi.createGroup).mockResolvedValue({ id: 5, name: 'PRO-05' } as never)
    const user = userEvent.setup()
    renderWithProviders(
      <AssistantActionsProvider>
        <Routes>
          <Route path="/assistant" element={<QuickGroupModal onClose={() => {}} />} />
          <Route path="/assistant/groups/:id" element={<p>Group page</p>} />
        </Routes>
      </AssistantActionsProvider>,
      { route: '/assistant' },
    )
    await user.type(await screen.findByLabelText(/Название группы/), 'PRO-05')
    await user.selectOptions(screen.getByLabelText(/Программа/), '1')
    await user.selectOptions(screen.getByLabelText(/Тренер/), '1')
    await user.click(screen.getByRole('button', { name: 'Пт' }))
    await user.click(await screen.findByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Создать группу' }))

    await waitFor(() => expect(assistantApi.createGroup).toHaveBeenCalledWith(expect.objectContaining({
      name: 'PRO-05', course: 1, students: [9],
      programs: [{ teacher: 1, subject: 1, slots: [
        { day: 'mon', start: '16:00', end: '17:30', room: null },
        { day: 'wed', start: '16:00', end: '17:30', room: null },
      ] }],
    })))
    expect(await screen.findByText('Group page')).toBeInTheDocument()
  })

  it('Контроль активности lists flagged students read only and filters by a KPI', async () => {
    const activity = {
      student_id: 7, name: 'Islam Duishobaev', group: { id: 1, name: 'PRO-01' }, attendance: 40, attended: 2, absent: 3, late: 0, excused: 0,
      marked: 5, lessons: 5, consecutive_absences: 3, homework: 20, homework_done: 1, homework_due: 5, homework_missed: 4, homework_pending: 0,
      consecutive_missed_homework: 4, last_attended: '2026-09-20', last_lesson: '2026-10-01', last_teacher: 'Islam', last_homework_done: null,
      last_homework_done_title: '', last_homework_given: '2026-10-01', last_activity: '2026-09-20', status: 'risk', status_label: 'В зоне риска', categories: ['risk', 'both'],
    }
    vi.mocked(assistantApi.control).mockResolvedValue({
      period: '30d', thresholds: { consecutive_absences: 3, consecutive_missed_homework: 3 },
      kpis: { not_attending: 1, no_homework: 1, both: 1, frequent_absence: 1, stale_homework: 1, low_activity: 1, risk: 1 },
      categories: [{ key: 'risk', label: 'В зоне риска', count: 1 }], students: [activity as never], total: 1,
    })
    const user = userEvent.setup()
    renderWithProviders(<AssistantActionsProvider><AssistantControlPage /></AssistantActionsProvider>, { route: '/assistant/control' })
    expect(await screen.findByText('Islam Duishobaev')).toBeInTheDocument()
    expect(screen.getAllByText('В зоне риска').length).toBeGreaterThan(0)
    expect(assistantApi.control).toHaveBeenCalledWith(expect.objectContaining({ period: '30d', sort: 'risk' }))
    await user.click(screen.getByRole('button', { name: /Не сдают ДЗ/ }))
    await waitFor(() => expect(assistantApi.control).toHaveBeenCalledWith(expect.objectContaining({ category: 'no_homework' })))
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('the ДЗ tab is read only: KPIs and a table, no edit controls', async () => {
    vi.mocked(assistantApi.groupHomework).mockResolvedValue({
      summary: { total: 1, complete: 0, missing: 1, review: 0, open: 0, average_percent: 50 },
      homeworks: [{
        id: 3, title: 'Циклы', lesson: { id: 4, number: 2, topic: 'Циклы', date: '2026-10-01' }, teacher: { id: 1, name: 'Islam' },
        deadline: '2026-10-03', issued: '2026-10-01', done: 1, pending: 0, checked: 1, expected: 2, not_done: 1, percent: 50, due: true,
        status: 'missing', status_display: 'Есть пропуски',
      }],
    })
    renderWithProviders(
      <AssistantActionsProvider><GroupHomeworkTab group={{ id: 1, name: 'PRO-01', programs: [{ teacher: { id: 1, name: 'Islam' } }], students: [] } as never} /></AssistantActionsProvider>,
      { route: '/assistant/groups/1?tab=homework' },
    )
    const table = await screen.findByRole('table')
    const row = within(table).getByText('Циклы').closest('tr')!
    expect(within(row).getByText('1/2')).toBeInTheDocument()
    expect(within(row).getByText('Есть пропуски')).toBeInTheDocument()
    for (const name of [/Редактировать/, /Удалить/, /Сохранить/, /Отметить/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('Месячный отчёт: one page, sections in order, no trainer report; «Сформировать» picks the month', async () => {
    const student = {
      student_id: 7, name: 'Islam Duishobaev', group: { id: 1, name: 'PRO-01' }, attendance: 30, attended: 3, marked: 10, absent: 7,
      consecutive_absences: 4, homework: 20, homework_done: 1, homework_due: 5, homework_missed: 4, consecutive_missed_homework: 4,
      last_activity: '2026-09-18', status: 'risk' as const, status_label: 'В зоне риска',
    }
    vi.mocked(assistantApi.monthlyReport).mockResolvedValue({
      year: 2026, month: 9, title: 'Сентябрь 2026', start: '2026-09-01', end: '2026-09-30', until: '2026-09-30', is_complete: true,
      generated_at: '2026-10-06T07:00:00Z',
      overview: { groups_total: 3, groups_active: 3, groups_inactive: 0, students_total: 32, students_active: 30, students_new: 4,
        students_deactivated: 1, attendance_percent: 87, homework_percent: 81, students_at_risk: 1 },
      attendance: { lessons: 33, marked: 968, attended: 842, absent: 126, excused: 0, percent: 87,
        groups: [{ group: { id: 1, name: 'PRO-01' }, students: 10, lessons: 12, attended: 100, absent: 6, marked: 106, percent: 94 }] },
      homework: { given: 12, due: 12, done: 39, not_done: 6, pending: 3, expected: 48, percent: 81,
        groups: [{ group: { id: 1, name: 'PRO-01' }, homeworks: 12, due: 12, done: 39, not_done: 6, pending: 3, expected: 48, percent: 81 }] },
      students: { attendance_attention: [student], homework_attention: [student], risk: [student], no_activity: [],
        activity: { analysed: 30, normal: 25, attention: 3, low: 2, risk: 1, no_data: 0, not_attending: 1, no_homework: 1, no_activity: 0 } },
      surveys: { surveys: 1, participants: 9, participation: 90, average: 4.7, low_ratings: 0, texts_total: 1,
        rows: [{ id: 1, title: 'Качество обучения', group: { id: 1, name: 'PRO-01' }, audience_display: 'Студенты', status_display: 'Опубликован',
          participants: 9, expected: 10, participation: 90, average: 4.7, ratings: 9, low_ratings: 0 }],
        quotes: [{ text: 'Больше практики', count: 2, survey: 'Качество обучения', question: 'Что улучшить?', date: '2026-09-10' }] },
      scholarships: { awards: 1, recipients: 1, total_amount: 4000, paid: 0, paid_amount: 0, groups: ['PRO-01'],
        rows: [{ id: 1, student: { id: 8, name: 'Aida K' }, group: 'PRO-01', title: 'Стипендия', amount: 4000, reason: '1 место в рейтинге',
          status: 'approved', status_display: 'Утверждена', payment_status: 'unpaid', payment_display: 'Не выдано', award_date: '2026-09-30' }] },
      conclusions: { good: ['Средняя посещаемость 87% — выше 85%.'], attention: ['В зоне риска: 1 студент.'] },
    })
    const user = userEvent.setup()
    renderWithProviders(<AssistantActionsProvider><AssistantMonthlyReportPage /></AssistantActionsProvider>, { route: '/assistant/reports?year=2026&month=9' })
    expect(await screen.findByRole('heading', { name: 'Сентябрь 2026' })).toBeInTheDocument()
    expect(assistantApi.monthlyReport).toHaveBeenCalledWith(2026, 9)
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(titles.slice(1)).toEqual([
      '1.Общая статистика', '2.Посещаемость', '3.Требуют внимания — посещаемость', '4.Домашние задания', '5.Требуют внимания — ДЗ',
      '6.В зоне риска', '7.Опросы', '8.Стипендии', '9.Активность студентов', '10.Итоги месяца',
    ])
    expect(screen.getByText('«Больше практики»')).toBeInTheDocument()
    expect(screen.getByText('Aida K')).toBeInTheDocument()
    expect(screen.queryByText(/KPI|Рейтинг тренеров|Эффективность/)).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Месяц'), '8')
    await user.click(screen.getByRole('button', { name: /Сформировать отчёт/ }))
    await waitFor(() => expect(assistantApi.monthlyReport).toHaveBeenCalledWith(2026, 8))
  })
})
