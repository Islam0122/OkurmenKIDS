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
  },
  surveysApi: {},
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, first_name: 'Asel', last_name: 'K', role: 'assistant', username: 'a', email: 'a@a', is_active: true, is_verified: true }, logout: vi.fn() }),
}))

import { assistantApi } from '@/api/assistant'
import { AppLayout } from '@/app/layouts/AppLayout'

import { AssistantActionsProvider } from './actions/AssistantActions'
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
  weekdays: [],
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
    expect(screen.getAllByRole('link', { name: 'Добавить студента' }).length).toBeGreaterThan(0)
  })
})
