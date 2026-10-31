import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { Dashboard, MyTasks, OpsMeta, TaskDetail, TaskListItem, TasksMeta, TrainersResponse } from '@/types/operations'

vi.mock('@/api/operations', () => ({
  operationsApi: { meta: vi.fn(), dashboard: vi.fn(), trainers: vi.fn() },
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
