import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { TeamLeadReport, WorkLogEntry, WorklogOptions } from '@/types/worklog'

import { ReportPage } from './ReportPage'
import { WorklogPage } from './WorklogPage'

vi.mock('@/api/worklog', () => ({
  worklogApi: {
    options: vi.fn(), entries: vi.fn(), summary: vi.fn(), createEntry: vi.fn(), updateEntry: vi.fn(),
    deleteEntry: vi.fn(), reports: vi.fn(), report: vi.fn(), createReport: vi.fn(), updateReport: vi.fn(),
    deleteReport: vi.fn(), recalculate: vi.fn(),
  },
}))

vi.mock('@/api/lessons', () => ({ lessonsApi: { list: vi.fn() } }))

import { worklogApi } from '@/api/worklog'

const OPTIONS: WorklogOptions = {
  report_kinds: [
    {
      kind: 'meeting', label: 'Собрание команды', period: 'date', links: [], required_links: [], description: 'Встреча',
      statuses: [{ value: 'draft', label: 'Черновик' }, { value: 'submitted', label: 'Сдан' }],
      fields: [
        { key: 'participants', label: 'Участники', type: 'list', required: true },
        { key: 'discussed', label: 'Обсуждалось', type: 'list', required: true },
      ],
    },
    {
      kind: 'lesson_visit', label: 'Проверка занятия', period: 'date', links: ['lesson', 'group', 'teacher'],
      required_links: ['teacher'], description: 'Проверка',
      statuses: [{ value: 'draft', label: 'Черновик' }, { value: 'submitted', label: 'Сдан' }],
      fields: [{ key: 'overall', label: 'Оценка', type: 'score', required: true, help: '1 — плохо, 5 — отлично' }],
    },
  ],
  work_types: [
    { value: 'lesson_control', label: 'Контроль занятия' },
    { value: 'meeting', label: 'Собрание' },
  ],
  statuses: [
    { value: 'new', label: 'Новая' },
    { value: 'in_progress', label: 'В работе' },
    { value: 'done', label: 'Выполнено' },
    { value: 'overdue', label: 'Просрочено' },
  ],
  priorities: [
    { value: 'low', label: 'Низкий' },
    { value: 'medium', label: 'Средний' },
    { value: 'high', label: 'Высокий' },
    { value: 'critical', label: 'Критический' },
  ],
  groups: [{ id: 1, name: 'Python-12', status: 'active' }],
  teachers: [{ id: 4, name: 'Aizada', is_active: true }],
  students: [{ id: 9, name: 'Азамат', group: 1 }],
}

function entry(overrides: Partial<WorkLogEntry> = {}): WorkLogEntry {
  return {
    id: 1, entry_kind: 'log', date: '2026-10-04', time_from: '10:00:00', time_to: '11:30:00', work_type: 'lesson_control',
    group: 1, teacher: 4, student: null, with_whom: '', title: '', goal: '', description: 'Посетил занятие',
    result: 'Тренер не проверил ДЗ', problem: '', decision: '', next_action: 'Повторная проверка', responsible: 'Тренер',
    deadline: '2026-10-07', priority: 'medium', status: 'new', comment: '', report: null,
    created_at: '2026-10-04T10:00:00Z', updated_at: '2026-10-04T10:00:00Z', author: { id: 7, name: 'Нурлан' },
    group_detail: { id: 1, name: 'Python-12' }, teacher_detail: { id: 4, name: 'Aizada' }, student_detail: null,
    work_type_label: 'Контроль занятия', priority_label: 'Средний', effective_status: 'new', effective_status_label: 'Новая',
    is_overdue: false, summary: '', can_edit: true, ...overrides,
  }
}

function report(overrides: Partial<TeamLeadReport> = {}): TeamLeadReport {
  return {
    id: 5, kind: 'meeting', kind_label: 'Собрание команды', date: '2026-10-04', period_start: null, period_end: null,
    group: null, teacher: null, student: null, lesson: null, data: { participants: ['Айбек'], discussed: ['Экзамены'] },
    metrics: {}, metrics_calculated_at: null, status: 'submitted', status_label: 'Сдан', title: 'Собрание команды · 04.10.2026',
    author: { id: 7, name: 'Нурлан' }, group_detail: null, teacher_detail: null, student_detail: null, can_edit: true,
    created_at: '2026-10-04T10:00:00Z', updated_at: '2026-10-04T10:00:00Z', tasks: [], ...overrides,
  }
}

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

function badRequest(data: unknown) {
  return new AxiosError('Bad Request', '400', undefined, undefined, { status: 400, data } as AxiosResponse)
}

describe('Рабочий журнал', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(worklogApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(worklogApi.summary).mockResolvedValue({ today: 2, open: 3, overdue: 1, due_today: 0 })
    vi.mocked(worklogApi.entries).mockResolvedValue(page([entry()]))
    vi.mocked(worklogApi.reports).mockResolvedValue(page([report()]))
  })

  it('shows the journal with the five answers and the overdue counter', async () => {
    renderWithProviders(<WorklogPage />, { route: '/app/worklog' })

    expect(await screen.findByText('Тренер не проверил ДЗ')).toBeInTheDocument()
    expect(screen.getByText('Посетил занятие')).toBeInTheDocument()
    expect(screen.getByText('Повторная проверка')).toBeInTheDocument()
    const overdue = screen.getAllByText('Просрочено').find((el) => el.tagName !== 'OPTION')
    expect(overdue?.closest('.card')).toHaveTextContent('1')
    expect(worklogApi.entries).toHaveBeenCalledWith(expect.objectContaining({ entry_kind: 'log', mine: '1' }))
  })

  it('shows the backend field errors of a record that misses an answer', async () => {
    vi.mocked(worklogApi.createEntry).mockRejectedValue(badRequest({ result: ['Какой результат получен?'] }))
    const user = userEvent.setup()
    renderWithProviders(<WorklogPage />, { route: '/app/worklog' })

    await user.click(await screen.findByRole('button', { name: 'Запись' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/Что сделано/), 'Проверил журнал')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))

    expect(await within(dialog).findByText('Какой результат получен?')).toBeInTheDocument()
    expect(worklogApi.createEntry).toHaveBeenCalledWith(
      expect.objectContaining({ entry_kind: 'log', description: 'Проверил журнал', group: null, status: 'new' }),
    )
  })

  it('lists tasks and never offers «Просрочено» as a status to pick', async () => {
    vi.mocked(worklogApi.entries).mockResolvedValue(
      page([entry({ entry_kind: 'task', title: 'Проверить журнал', effective_status: 'overdue', effective_status_label: 'Просрочено', is_overdue: true })]),
    )
    const user = userEvent.setup()
    renderWithProviders(<WorklogPage />, { route: '/app/worklog?tab=tasks' })

    expect(await screen.findByText('Проверить журнал')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Изменить' }))
    const status = within(await screen.findByRole('dialog')).getByLabelText('Статус')
    expect(within(status).queryByRole('option', { name: 'Просрочено' })).not.toBeInTheDocument()
  })

  it('opens a meeting report with its decisions and adds one as a task', async () => {
    vi.mocked(worklogApi.report).mockResolvedValue(report())
    vi.mocked(worklogApi.createEntry).mockResolvedValue(entry({ entry_kind: 'task', report: 5 }))
    const user = userEvent.setup()
    renderWithProviders(
      <Routes>
        <Route path="/app/worklog/reports/:id" element={<ReportPage />} />
      </Routes>,
      { route: '/app/worklog/reports/5' },
    )

    expect(await screen.findByText('Решений пока нет')).toBeInTheDocument()
    expect(screen.getByLabelText(/Участники/)).toHaveValue('Айбек')
    await user.click(screen.getByRole('button', { name: 'Добавить решение' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/Задача/), 'Подготовить экзамен')
    await user.type(within(dialog).getByLabelText(/Ответственный/), 'Айбек')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))

    await waitFor(() =>
      expect(worklogApi.createEntry).toHaveBeenCalledWith(
        expect.objectContaining({ entry_kind: 'task', report: 5, work_type: 'meeting', title: 'Подготовить экзамен' }),
      ),
    )
  })

  it('renders a new report form from its schema and maps data errors to fields', async () => {
    vi.mocked(worklogApi.createReport).mockRejectedValue(badRequest({ data: { overall: ['Обязательное поле.'] } }))
    const user = userEvent.setup()
    renderWithProviders(
      <Routes>
        <Route path="/app/worklog/reports/:id" element={<ReportPage />} />
      </Routes>,
      { route: '/app/worklog/reports/new?kind=lesson_visit' },
    )

    expect(await screen.findByRole('radiogroup')).toBeInTheDocument()
    expect(screen.getByLabelText('Занятие')).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Статус'), 'submitted')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await screen.findByText('Обязательное поле.')).toBeInTheDocument()
    expect(worklogApi.createReport).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'lesson_visit', status: 'submitted', lesson: null, teacher: null }),
    )
  })

  it('shows a report of another author read only', async () => {
    vi.mocked(worklogApi.report).mockResolvedValue(report({ can_edit: false, metrics: { quality: { meetings: 2 } } }))
    renderWithProviders(
      <Routes>
        <Route path="/app/worklog/reports/:id" element={<ReportPage />} />
      </Routes>,
      { route: '/app/worklog/reports/5' },
    )

    expect(await screen.findByText('Экзамены')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Пересчитать' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Добавить решение' })).not.toBeInTheDocument()
    expect(screen.getByText('Собраний')).toBeInTheDocument()
  })
})
