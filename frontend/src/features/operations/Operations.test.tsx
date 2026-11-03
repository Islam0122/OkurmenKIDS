import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { AttendanceRow, AttendanceSchedule, Dashboard, MyTasks, OpsMeta, StaffAttendanceResponse, TaskDetail, TaskListItem, TasksMeta, TrainersResponse } from '@/types/operations'

vi.mock('@/api/operations', () => ({
  operationsApi: { meta: vi.fn(), dashboard: vi.fn(), trainers: vi.fn(), attendance: vi.fn(), attendancePermissions: vi.fn(), createAttendancePermission: vi.fn(), cancelAttendancePermission: vi.fn() },
  tasksApi: { meta: vi.fn(), my: vi.fn(), get: vi.fn(), act: vi.fn(), list: vi.fn() },
  notificationsApi: { unreadCount: vi.fn().mockResolvedValue({ count: 2 }), list: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }) },
  workReportsApi: {},
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: 'operations_director', first_name: 'Олег', last_name: 'Директор' }, status: 'authenticated', logout: vi.fn() }),
}))

import { operationsApi, tasksApi } from '@/api/operations'

import { MyTasksPage } from '../tasks/MyTasksPage'
import { TaskDetailPage } from '../tasks/TaskDetailPage'
import { OperationsAttendancePage } from './ControlPages'
import { OperationsDashboardPage } from './DashboardPage'
import { OPERATIONS_NAV, OperationsLayout } from './OperationsLayout'
import { OperationsTrainersPage } from './TrainersPage'

const ops = vi.mocked(operationsApi)
const tasks = vi.mocked(tasksApi)

const person = { id: 5, full_name: 'Айжан Тренер', role: 'teacher', role_label: 'Тренер', department: 'academy' as const }
const meta: OpsMeta = {
  periods: [], departments: [{ value: 'academy', label: 'Академия' }, { value: 'sales', label: 'Отдел продаж' }],
  roles: [], employees: [person], subjects: [{ id: 1, name: 'Python' }], groups: [], metrics: [], kpi_periods: [],
  issue_kinds: [], issue_statuses: [], priorities: [], report_kinds: [], employee_report_kinds: [], can_view_finance: true, today: '2026-10-31',
}

const empty = { expected: 0, submitted: 0, missing: 0, pending: 0, rate: null }
const attendance = { counts: { present: 3, late: 1, absent: 0, not_arrived: 2 }, expected_days: 4, attended_days: 4, attendance_rate: 100, punctuality_rate: 75, worked_hours: 20, late_minutes: 12 }

const dashboard: Dashboard = {
  filters: { period: 'today', label: 'Сегодня', start: '2026-10-31', end: '2026-10-31' },
  metrics: {
    total_employees: 14, active_employees: 12, tasks_completed: 7, tasks_in_progress: 3, tasks_overdue: 2, pending_reviews: 4,
    attendance_rate: 92.5, reports_submitted: 5, reports_expected: 6, kpi: { targets: 0, measured: 0, below_target: 0, achievement: null }, overall_performance: 81.2,
  },
  previous: { tasks_completed: 5, attendance_rate: 90, label: '30.10 — 30.10' },
  departments: [{ key: 'academy', label: 'Академия', employees: 8, tasks: { open: 4, overdue: 2, review: 1, completed: 5, completion_rate: 70 }, attendance_rate: 95, reports: empty, open_issues: 3, performance: 82.5 }],
  today_tasks: [{ id: 11, title: 'Проверить журналы', department: 'academy', department_label: 'Академия', assignee: { id: 5, full_name: 'Айжан Тренер', role_label: 'Тренер' }, priority: 'high', priority_label: 'Высокий', status: 'pending', deadline: '2026-10-31T18:00:00+06:00' }],
  overdue_tasks: [], overdue_total: 2,
  attendance: { ...attendance, today: attendance },
  reports: { expected: 6, submitted: 5, missing: 1, pending: 0, rate: 83.3 },
  attention: { total: 3, critical: 1, by_kind: {}, top: [{ id: 9, title: 'Журнал не заполнен: Айжан', priority: 'high', kind: 'journal_not_filled', kind_label: 'Журнал не заполнен', department_label: 'Академия', responsible: null, detected_at: '2026-10-31T09:00:00+06:00' }] },
  students: { active_students: 120, active_groups: 10, problem_students: 6, risk: 2, frequent_absence: 3 },
  activity: [],
}

function task(over: Partial<TaskDetail> = {}): TaskDetail {
  return {
    id: 21, title: 'Сдать отчёт по группе', department: 'academy', department_label: 'Академия', assignee: person, created_by: { ...person, id: 1, full_name: 'Олег Директор' },
    priority: 'medium', priority_label: 'Средний', category: 'general', category_label: 'Общая', status: 'review', stored_status: 'review', status_label: 'На проверке',
    start_date: null, deadline: null, requires_approval: true, occurrence_date: null, is_recurring: false, checklist_total: 0, checklist_done: 0, completed_at: null,
    created_at: '2026-10-30T10:00:00+06:00', updated_at: '2026-10-30T10:00:00+06:00', description: 'Описание', reviewer: { ...person, id: 1, full_name: 'Олег Директор' },
    checklist: [], comments: [], attachments: [], history: [{ id: 1, actor: null, action: 'created', action_label: 'Создана', from_status: '', to_status: 'pending', changes: {}, comment: '', created_at: '2026-10-30T10:00:00+06:00' }],
    reviews: [], actions: ['approve', 'reject'], started_at: null, submitted_at: null, cancelled_at: null, ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  ops.meta.mockResolvedValue(meta)
})

describe('кабинет операционного директора', () => {
  it('в боковом меню все 14 разделов ТЗ', () => {
    expect(OPERATIONS_NAV).toHaveLength(14)
    renderWithProviders(<Routes><Route path="/operations" element={<OperationsLayout />}><Route index element={<p>Главная</p>} /></Route></Routes>, { route: '/operations' })
    const nav = screen.getAllByRole('navigation', { name: 'Разделы кабинета операционного директора' })[0]
    for (const label of ['Dashboard', 'Тренеры', 'РОП', 'Посещаемость сотрудников', 'Ежедневный контроль', 'KPI и аналитика', 'Проблемы', 'Настройки']) {
      expect(within(nav).getByText(label)).toBeInTheDocument()
    }
  })

  it('дашборд показывает цифры сервера, а не заготовки', async () => {
    ops.dashboard.mockResolvedValue(dashboard)
    renderWithProviders(<OperationsDashboardPage />, { route: '/operations?period=today' })
    expect(await screen.findByText('92,5%')).toBeInTheDocument()
    expect(screen.getByText('Задач выполнено').parentElement).toHaveTextContent('7')
    expect(screen.getByText('5 / 6')).toBeInTheDocument()
    expect(screen.getByText('цели KPI не заданы')).toBeInTheDocument()
    expect(screen.getByText('Журнал не заполнен: Айжан')).toBeInTheDocument()
    expect(ops.dashboard).toHaveBeenCalledWith(expect.objectContaining({ period: 'today' }))
  })

  it('фильтр периода уходит в запрос', async () => {
    ops.dashboard.mockResolvedValue(dashboard)
    renderWithProviders(<OperationsDashboardPage />, { route: '/operations' })
    await screen.findByText('92,5%')
    await userEvent.click(screen.getByRole('radio', { name: 'Месяц' }))
    await waitFor(() => expect(ops.dashboard).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'this_month' })))
  })

  it('тренеры: предупреждения из Контроля занятий', async () => {
    const response: TrainersResponse = {
      filters: dashboard.filters,
      summary: { trainers: 1, with_warnings: 1, average_kpi: 64, warnings: { journal_not_filled: 1 } },
      warning_labels: { journal_not_filled: 'Журнал не заполнен', kpi_below_target: 'KPI ниже цели' },
      trainers: [{
        id: 3, user_id: 5, name: 'Айжан Тренер', photo: null, position: 'Тренер', subjects: ['Python'], groups: [{ id: 1, name: 'Python 1', kpi: 64 }], students: 12, is_active: true,
        kpi: 64, kpi_level: 'low', kpi_target: 80, kpi_achievement: 80, attendance_rate: 70, homework_rate: 60,
        journal: { status: 'problem', status_label: 'Проблема', lessons_due: 4, lessons_closed: 2, not_closed: 2, upcoming: 1, attendance_missing: 2, homework_awaiting_review: 1, homework_missing: 0, homework_checked: 1, grades_missing: 0, last_activity_at: null, completion: 50, issues: [] },
        reports: empty, tasks: { open: 1, overdue: 0, review: 0, completed: 2 },
        warnings: [{ key: 'journal_not_filled', label: 'Журнал не заполнен' }, { key: 'kpi_below_target', label: 'KPI ниже цели' }],
      }],
    }
    ops.trainers.mockResolvedValue(response)
    renderWithProviders(<OperationsTrainersPage />, { route: '/operations/trainers' })
    const row = (await screen.findAllByText('Айжан Тренер'))[0].closest('tr') as HTMLElement
    expect(within(row).getByText('KPI ниже цели')).toBeInTheDocument()
    expect(within(row).getByText('цель 80%')).toBeInTheDocument()
  })
})

describe('посещаемость сотрудников', () => {
  const off = { expected_start: null, expected_end: null, grace_minutes: null, late_after: null }
  function row(id: number, name: string, schedule: AttendanceSchedule, over: Partial<AttendanceRow> = {}): AttendanceRow {
    return {
      user: { ...person, id, full_name: name }, date: '2026-10-31', status: 'present', status_label: 'Присутствует',
      check_in: null, check_out: null, worked_minutes: 0, late_minutes: 0, expected_start: null, expected_end: null,
      schedule, location: null, geo_verified: false, distance_m: null, adjusted: false, ...over,
    }
  }
  const response: StaffAttendanceResponse = {
    filters: dashboard.filters, summary: attendance, departments: [], employees: [], statuses: [], leave_tracking: true,
    rows: [
      row(1, 'Айбек Вовремя', { kind: 'work', label: '10:00', expected_start: '10:00', expected_end: '19:00', grace_minutes: 10, late_after: '10:10', source: 'personal', source_label: 'Личный график' },
        { status: 'late', status_label: 'Опоздание', late_minutes: 15 }),
      row(2, 'Айдана Выходной', { kind: 'day_off', label: 'Выходной', ...off, source: 'personal', source_label: 'Личный график' }, { status: 'day_off', status_label: 'Выходной' }),
      row(3, 'Нурлан Отпуск', { kind: 'vacation', label: 'Отпуск', ...off, source: 'exception', source_label: 'Отпуск' }, { status: 'vacation', status_label: 'Отпуск' }),
      row(4, 'Бектур Больничный', { kind: 'sick_leave', label: 'Больничный', ...off, source: 'exception', source_label: 'Больничный' }, { status: 'sick_leave', status_label: 'Больничный' }),
      row(5, 'Салтанат Без графика', { kind: 'not_set', label: 'Не задано', ...off, source: null, source_label: '' }, { status: 'day_off', status_label: 'Выходной' }),
    ],
  }

  it('колонка «По графику» стоит между «Дата» и «Приход» и показывает данные сервера', async () => {
    ops.attendance.mockResolvedValue(response)
    renderWithProviders(<OperationsAttendancePage />, { route: '/operations/attendance?period=today' })
    await screen.findByText('Айбек Вовремя')
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers.slice(3, 6)).toEqual(['Дата', 'По графику', 'Приход'])
    const cell = (name: string) => within(screen.getByText(name).closest('tr') as HTMLElement).getAllByRole('cell')[4]
    expect(cell('Айбек Вовремя')).toHaveTextContent('10:00')
    expect(cell('Айбек Вовремя')).toHaveTextContent('льгота 10 мин · Личный график')
    expect(cell('Айдана Выходной')).toHaveTextContent('Выходной')
    expect(cell('Нурлан Отпуск')).toHaveTextContent('Отпуск')
    expect(cell('Бектур Больничный')).toHaveTextContent('Больничный')
    expect(cell('Салтанат Без графика')).toHaveTextContent('Не задано')
    expect(ops.attendance).toHaveBeenCalledWith(expect.objectContaining({ period: 'today' }))
    // Без права выдавать разрешения кнопки «Отпросился» нет.
    expect(screen.queryByRole('button', { name: 'Отпросился' })).not.toBeInTheDocument()
  })

  it('«Отпросился»: разрешённое опоздание из строки — запрос со временем офиса, детали в строке', async () => {
    const late = row(1, 'Айбек Вовремя', { kind: 'work', label: '10:30', expected_start: '10:30', expected_end: '19:00', grace_minutes: 10, late_after: '10:40', source: 'personal', source_label: 'Личный график', base_expected_start: '10:00', base_expected_end: '19:00' },
      { status: 'permitted_late', status_label: 'Разрешено опоздать', permissions: [{ id: 7, kind: 'late_arrival', kind_label: 'Опоздание', starts_at: '2026-10-31T10:00:00+06:00', ends_at: '2026-10-31T10:30:00+06:00', period_label: '31.10 10:00–10:30', reason: 'Врач', comment: '', approved_by: 'Олег Директор' }] })
    ops.attendance.mockResolvedValue({ ...response, rows: [late], can_manage_permissions: true })
    ops.createAttendancePermission.mockResolvedValue({} as never)
    renderWithProviders(<OperationsAttendancePage />, { route: '/operations/attendance?period=today' })
    const tr = (await screen.findByText('Айбек Вовремя')).closest('tr') as HTMLElement
    expect(within(tr).getByText('Разрешено опоздать')).toBeInTheDocument()
    expect(within(tr).getByText('Опоздание: 31.10 10:00–10:30 — Врач')).toBeInTheDocument()
    await userEvent.click(within(tr).getByRole('button', { name: /Отпросился: Айбек Вовремя/ }))
    const dialog = await screen.findByRole('dialog')
    const save = within(dialog).getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText('Придёт к'), '11:15')
    await userEvent.type(within(dialog).getByLabelText('Причина'), 'Пробки')
    await userEvent.click(save)
    await waitFor(() => expect(ops.createAttendancePermission).toHaveBeenCalled())
    expect(ops.createAttendancePermission.mock.calls[0][0]).toEqual({ user: 1, kind: 'late_arrival', starts_at: '2026-10-31T10:00', ends_at: '2026-10-31T11:15', reason: 'Пробки', comment: '' })
  })

  it('«Отпросился»: весь день и отмена из истории с причиной', async () => {
    ops.attendance.mockResolvedValue({ ...response, can_manage_permissions: true })
    ops.createAttendancePermission.mockResolvedValue({} as never)
    ops.cancelAttendancePermission.mockResolvedValue({} as never)
    ops.attendancePermissions.mockResolvedValue({
      filters: dashboard.filters, kinds: [], statuses: [], can_manage: true,
      results: [{ id: 9, kind: 'full_day', kind_label: 'Весь день', starts_at: '2026-10-30T00:00:00+06:00', ends_at: '2026-10-31T00:00:00+06:00', period_label: '30.10', reason: 'Свадьба', comment: '',
        user: { id: 3, full_name: 'Нурлан Отпуск', role_label: 'Ассистент', department: 'academy' }, status: 'approved', status_label: 'Утверждено', created_at: '2026-10-29T12:00:00+06:00', created_by: { id: 1, full_name: 'Олег Директор' },
        approved_at: '2026-10-29T12:00:00+06:00', approved_by: { id: 1, full_name: 'Олег Директор' }, cancelled_at: null, cancelled_by: null, cancel_reason: '' }],
    })
    renderWithProviders(<OperationsAttendancePage />, { route: '/operations/attendance?period=today' })
    await screen.findByText('Айбек Вовремя')
    await userEvent.click(screen.getAllByRole('button', { name: 'Отпросился' })[0])
    let dialog = await screen.findByRole('dialog')
    await userEvent.selectOptions(within(dialog).getByRole('combobox'), '5')
    await userEvent.click(within(dialog).getByRole('radio', { name: 'Весь день' }))
    await userEvent.type(within(dialog).getByLabelText('Причина'), 'Семейные обстоятельства')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(ops.createAttendancePermission).toHaveBeenCalled())
    expect(ops.createAttendancePermission.mock.calls[0][0]).toEqual({ user: 5, kind: 'full_day', starts_at: '2026-10-31T00:00', ends_at: '2026-10-31T23:59', reason: 'Семейные обстоятельства', comment: '' })

    await userEvent.click(screen.getByRole('radio', { name: 'Отпросился' }))
    const historyRow = (await screen.findByText('Нурлан Отпуск')).closest('tr') as HTMLElement
    expect(historyRow).toHaveTextContent('создал Олег Директор')
    await userEvent.click(within(historyRow).getByRole('button', { name: 'Отменить' }))
    dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Отменить разрешение' })
    expect(confirm).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText('Причина отмены'), 'Ошибка')
    await userEvent.click(confirm)
    await waitFor(() => expect(ops.cancelAttendancePermission).toHaveBeenCalledWith(9, 'Ошибка'))
  })
})

describe('задачи сотрудника', () => {
  it('«Мои задачи» показывает разделы с количеством', async () => {
    const item = { ...task(), status: 'overdue', status_label: 'Просрочена' } as TaskListItem
    const my = { today: [], overdue: [item], upcoming: [], in_progress: [], review: [], completed: [], to_review: [], counts: { to_review: 0 } } as MyTasks
    tasks.my.mockResolvedValue(my)
    tasks.meta.mockResolvedValue({ assignees: [], priorities: [], categories: [], departments: [], statuses: [], recurrence: [], can_assign_others: false, can_oversee: false, me: person } as TasksMeta)
    renderWithProviders(<MyTasksPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Просрочено · 1' }))
    expect(screen.getByText('Сдать отчёт по группе')).toBeInTheDocument()
  })

  it('вернуть задачу можно только с комментарием', async () => {
    tasks.get.mockResolvedValue(task())
    tasks.act.mockResolvedValue(task({ status: 'rejected', stored_status: 'rejected', actions: [] }))
    renderWithProviders(<Routes><Route path="/tasks/:id" element={<TaskDetailPage />} /></Routes>, { route: '/tasks/21' })
    const back = await screen.findByRole('button', { name: 'Вернуть на доработку' })
    expect(back).toBeDisabled()
    await userEvent.type(screen.getByPlaceholderText('Комментарий (обязателен при возврате)'), 'Нет фото')
    await userEvent.click(back)
    await waitFor(() => expect(tasks.act).toHaveBeenCalledWith(21, 'reject', 'Нет фото'))
  })

  it('кнопки действий — только те, что разрешил сервер', async () => {
    tasks.get.mockResolvedValue(task({ status: 'pending', stored_status: 'pending', status_label: 'Ожидает', actions: ['start', 'submit'] }))
    renderWithProviders(<Routes><Route path="/tasks/:id" element={<TaskDetailPage />} /></Routes>, { route: '/tasks/21' })
    expect(await screen.findByRole('button', { name: 'Взять в работу' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Подтвердить' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument()
  })
})
