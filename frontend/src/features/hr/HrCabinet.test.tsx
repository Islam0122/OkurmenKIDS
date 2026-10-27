import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { Application, Candidate, DailyReport, HRDashboard, Interview, PeriodReport, RecruitmentMeta, Vacancy } from '@/types/hr'

vi.mock('@/api/hr', () => ({
  hrApi: { meta: vi.fn(), list: vi.fn(), employee: vi.fn(), create: vi.fn(), update: vi.fn(), setPassword: vi.fn(), setActive: vi.fn() },
  recruitmentApi: {
    meta: vi.fn(), dashboard: vi.fn(), reminders: vi.fn(), vacancies: vi.fn(), vacancy: vi.fn(), createVacancy: vi.fn(), updateVacancy: vi.fn(),
    setVacancyStatus: vi.fn(), candidates: vi.fn(), candidate: vi.fn(), updateCandidate: vi.fn(), notes: vi.fn(), addNote: vi.fn(),
    history: vi.fn(), mergeCandidate: vi.fn(), eraseCandidate: vi.fn(), applications: vi.fn(), board: vi.fn(), createApplication: vi.fn(),
    updateApplication: vi.fn(), changeStatus: vi.fn(), notDuplicate: vi.fn(), uploadResume: vi.fn(), openResume: vi.fn(), hire: vi.fn(),
    requestAccount: vi.fn(), interviews: vi.fn(), interview: vi.fn(), scheduleInterview: vi.fn(), updateInterview: vi.fn(),
    cancelInterview: vi.fn(), markNoShow: vi.fn(), recordResult: vi.fn(), daily: vi.fn(), monthly: vi.fn(), exportDaily: vi.fn(),
    exportMonthly: vi.fn(),
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: 'hr_manager', first_name: 'Айгуль', last_name: 'HR' }, status: 'authenticated', logout: vi.fn() }),
}))

import { recruitmentApi } from '@/api/hr'

import { HrCandidateCardPage } from './CandidateCardPage'
import { HrCandidatesPage } from './CandidatesPage'
import { HrDashboardPage } from './DashboardPage'
import { HrInterviewsPage } from './InterviewsPage'
import { HrReportsPage } from './ReportsPage'
import { HrVacanciesPage } from './VacanciesPage'
import { HrVacancyEditPage } from './VacancyEditPage'

const api = vi.mocked(recruitmentApi)

const meta: RecruitmentMeta = {
  application_statuses: [{ value: 'new', label: 'Новый отклик' }, { value: 'offer', label: 'Предложение о работе' }],
  sources: [{ value: 'job_site', label: 'Сайт поиска работы' }, { value: 'referral', label: 'Рекомендация' }],
  channels: [{ value: 'public', label: 'Отклик с сайта' }, { value: 'hr', label: 'Добавлен HR' }],
  vacancy_statuses: [{ value: 'draft', label: 'Черновик' }, { value: 'published', label: 'Опубликована' }],
  work_formats: [{ value: 'office', label: 'В офисе' }, { value: 'remote', label: 'Удалённо' }],
  employment_types: [{ value: 'full_time', label: 'Полная занятость' }],
  currencies: [{ value: 'KGS', label: 'сом' }],
  interview_statuses: [{ value: 'scheduled', label: 'Запланировано' }, { value: 'cancelled', label: 'Отменено' }],
  interview_formats: [{ value: 'in_person', label: 'Очно' }, { value: 'online', label: 'Онлайн' }],
  interview_results: [{ value: 'passed', label: 'Подходит' }, { value: 'failed', label: 'Не подходит' }],
  next_steps: [{ value: 'offer', label: 'Сделать предложение' }, { value: 'reject', label: 'Отказать' }],
  hire_roles: [{ value: 'sales_manager', label: 'Менеджер по продажам' }],
  requestable_roles: [{ value: 'accountant', label: 'Бухгалтер' }],
  people: [{ id: 1, full_name: 'Айгуль HR', role_label: 'HR-менеджер' }, { id: 5, full_name: 'Азамат РОП', role_label: 'РОП' }],
  resume_max_mb: 5,
  today: '2026-10-21',
}

const vacancy: Vacancy = {
  id: 3, title: 'Менеджер по продажам', slug: 'menedzher-po-prodazham', department: 'Продажи', summary: '', description: 'Описание',
  responsibilities: 'Звонки', requirements: 'Опыт', nice_to_have: '', conditions: '', selection_stages: '', location: 'Бишкек',
  work_format: 'office', employment_type: 'full_time', salary_min: null, salary_max: null, salary_currency: 'KGS', show_salary: false,
  closes_on: null, responsible: 1, status: 'draft', status_label: 'Черновик', work_format_label: 'В офисе',
  employment_type_label: 'Полная занятость', responsible_info: meta.people[0], published_at: null, closed_at: null, archived_at: null,
  applications_count: 1, active_count: 1, new_count: 1, allowed_statuses: [{ value: 'published', label: 'Опубликована' }, { value: 'closed', label: 'Закрыта' }],
  missing_for_publishing: [], is_accepting: false, created_at: '2026-10-01T09:00:00+06:00', updated_at: '2026-10-01T09:00:00+06:00',
}

const application: Application = {
  id: 21, number: '2026-K7QM3D', candidate: 7, candidate_info: { id: 7, full_name: 'Асанов Бакыт', phone: '+996 555 123 456', email: 'b@mail.kg', erased: false },
  vacancy: 3, vacancy_info: { id: 3, title: 'Менеджер по продажам', status: 'published', status_label: 'Опубликована', slug: 'menedzher-po-prodazham' },
  position: '', position_label: 'Менеджер по продажам', channel: 'public', channel_label: 'Отклик с сайта', source: 'company_site',
  source_label: 'Сайт вакансий компании', source_details: '', applied_on: '2026-10-20', responsible: 1, responsible_info: meta.people[0],
  status: 'interview_scheduled', status_label: 'Собеседование назначено', status_changed_at: '2026-10-20T12:00:00+06:00',
  cover_letter: 'Хочу работать у вас', submitted_data: { full_name: 'Асанов Бакыт', city: 'Бишкек' }, has_resume: true, resume_name: 'cv.pdf',
  resume_size: 120_000, consent_at: '2026-10-20T09:00:00+06:00', consent_version: '2026-10', needs_duplicate_review: false, hired_user_info: null,
  allowed_statuses: [{ value: 'rejected', label: 'Отказ компании' }, { value: 'withdrawn', label: 'Кандидат отказался' }],
  next_interview_at: '2026-10-22T15:00:00+06:00', pending_account_request: null, created_at: '2026-10-20T09:00:00+06:00', updated_at: '2026-10-20T09:00:00+06:00',
}

const candidate: Candidate = {
  id: 7, last_name: 'Асанов', first_name: 'Бакыт', middle_name: '', full_name: 'Асанов Бакыт', phone: '+996 555 123 456', email: 'b@mail.kg',
  city: 'Бишкек', experience: '3 года в продажах', education: '', skills: '', portfolio_url: '', merged_into: null, merged_into_info: null,
  erased_at: null, applications: [application], possible_duplicates: [], created_at: '2026-10-20T09:00:00+06:00', updated_at: '2026-10-20T09:00:00+06:00',
}

const interview: Interview = {
  id: 11, application: 21, application_info: { id: 21, number: '2026-K7QM3D', status: 'interview_scheduled', status_label: 'Собеседование назначено' },
  candidate: 7, candidate_info: { id: 7, full_name: 'Асанов Бакыт' }, vacancy: 3, vacancy_info: { id: 3, title: 'Менеджер по продажам' },
  scheduled_at: '2026-10-22T15:00:00+06:00', duration_minutes: 60, format: 'online', format_label: 'Онлайн', location: '',
  meeting_url: 'https://meet.example.com/abc', interviewer: 5, interviewer_info: meta.people[1], notes: '', status: 'scheduled',
  status_label: 'Запланировано', reschedule_count: 0, rescheduled_to: null, cancel_reason: '', cancelled_at: null, result: '', result_label: '',
  overall_rating: null, skills_rating: null, strengths: '', concerns: '', result_comment: '', next_step: '', next_step_label: '',
  next_step_date: null, completed_at: null, created_at: '2026-10-20T12:00:00+06:00',
}

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR', undefined, undefined, { status, data } as AxiosResponse)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue(meta)
  api.reminders.mockResolvedValue({ count: 0, results: [] })
  api.vacancies.mockResolvedValue({ count: 1, next: null, previous: null, results: [vacancy] })
  api.vacancy.mockResolvedValue(vacancy)
  api.applications.mockResolvedValue({ count: 1, next: null, previous: null, results: [application] })
  api.candidate.mockResolvedValue(candidate)
  api.history.mockResolvedValue([])
  api.notes.mockResolvedValue([])
  api.interviews.mockResolvedValue([interview])
})

describe('главная HR', () => {
  it('показывает показатели из API, отклики, встречи и напоминания', async () => {
    const data: HRDashboard = {
      period: { date_from: '2026-10-01', date_to: '2026-10-21' }, employees_active: 12, employees_new: 2, vacancies_open: 5,
      vacancies_paused: 1, vacancies_draft: 2, vacancies_closed: 3, applications_total: 9, applications_in_progress: 6, applications_today: 2,
      applications_new: 4, screening: 2, shortlisted: 1, applications_by_status: {} as HRDashboard['applications_by_status'],
      interviews_today: 1, interviews_upcoming: 4, awaiting_decision: 3, offers: 1, hired: 2, hired_in_period: 1, rejected: 1,
      withdrawn: 0, duplicates_to_review: 1, account_requests_pending: 0,
      recent_applications: [{ id: 21, number: '2026-K7QM3D', candidate: { id: 7, full_name: 'Асанов Бакыт' }, status: 'new', status_label: 'Новый отклик', position: 'Менеджер по продажам', source_label: 'Сайт', channel: 'public', applied_on: '2026-10-20', created_at: '2026-10-20T09:00:00+06:00', needs_duplicate_review: true }],
      upcoming_interviews: [{ id: 11, scheduled_at: '2026-10-22T15:00:00+06:00', duration_minutes: 60, status: 'scheduled', status_label: 'Запланировано', format_label: 'Онлайн', candidate: { id: 7, full_name: 'Асанов Бакыт' }, application: 21, interviewer: 'Азамат РОП', position: 'Менеджер по продажам' }],
      recent_activity: [],
    }
    api.dashboard.mockResolvedValue(data)
    api.reminders.mockResolvedValue({ count: 1, results: [{ kind: 'interview_result', level: 'warning', at: '2026-10-20T15:00:00+06:00', title: 'Зафиксируйте итог собеседования: Асанов Бакыт', candidate: 7, application: 21, interview: 10 }] })
    renderWithProviders(<HrDashboardPage />)
    expect(await screen.findByText('Новые отклики')).toBeInTheDocument()
    expect(screen.getByText('Открытые вакансии').closest('div')?.parentElement).toHaveTextContent('5')
    expect(screen.getByText('Проверить дубли')).toBeInTheDocument()
    expect(screen.getByText('22.10.2026 15:00')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Асанов Бакыт' })[0]).toHaveAttribute('href', '/hr/candidates/7?application=21')
    expect(await screen.findByRole('link', { name: /Зафиксируйте итог собеседования/ })).toHaveAttribute('href', '/hr/candidates/7?application=21')
  })
})

describe('кандидаты', () => {
  it('фильтры уходят на сервер, строка ведёт в карточку отклика', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrCandidatesPage />)
    expect(await screen.findByRole('link', { name: 'Асанов Бакыт' })).toHaveAttribute('href', '/hr/candidates/7?application=21')
    await user.selectOptions(screen.getByLabelText('Источник'), 'referral')
    await user.click(screen.getByLabelText(/Только в работе/))
    await user.type(screen.getByLabelText('Дата отклика с'), '2026-10-01')
    await waitFor(() => expect(api.applications).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'referral', active: 'true', date_from: '2026-10-01', page: 1 })))
  })

  it('доска этапов: перевод только в допустимый этап', async () => {
    const user = userEvent.setup()
    api.board.mockResolvedValue({ columns: [
      { status: 'interview_scheduled', label: 'Собеседование назначено', count: 1, items: [application] },
      { status: 'rejected', label: 'Отказ компании', count: 0, items: [] },
    ] })
    api.changeStatus.mockResolvedValue({ ...application, status: 'rejected' })
    renderWithProviders(<HrCandidatesPage />, { route: '/hr/candidates?view=board' })
    const select = await screen.findByLabelText('Перевести «Асанов Бакыт» в этап')
    expect(within(select).queryByRole('option', { name: 'Принят на работу' })).not.toBeInTheDocument()
    await user.selectOptions(select, 'rejected')
    await waitFor(() => expect(api.changeStatus).toHaveBeenCalledWith(21, 'rejected', ''))
  })

  it('проверяет поля, предупреждает о совпадении контактов и добавляет отклик существующему', async () => {
    const user = userEvent.setup()
    api.createApplication
      .mockRejectedValueOnce(axiosError(409, { code: 'possible_duplicates', detail: 'Есть', matches: [{ id: 7, full_name: 'Асанов Бакыт', email: 'b@mail.kg', phone: '+996 555 123 456', same_email: false, same_phone: true, applications: 1 }] }))
      .mockResolvedValueOnce(application)
    renderWithProviders(<HrCandidatesPage />)
    await screen.findByRole('link', { name: 'Асанов Бакыт' })
    await user.click(screen.getByRole('button', { name: /Добавить кандидата/ }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Добавить' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Укажите имя, телефон или email, вакансию или должность.')
    expect(api.createApplication).not.toHaveBeenCalled()
    await user.type(within(dialog).getByLabelText('Имя *'), 'Бакыт')
    await user.type(within(dialog).getByLabelText('Телефон'), '0555 123 456')
    await user.type(within(dialog).getByLabelText('Должность'), 'SMM')
    await user.click(within(dialog).getByRole('button', { name: 'Добавить' }))
    expect(await within(dialog).findByText('Кандидат с такими контактами уже есть')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Это он — добавить отклик' }))
    await waitFor(() => expect(api.createApplication).toHaveBeenLastCalledWith(expect.objectContaining({ candidate: 7, position: 'SMM', applied_on: '2026-10-21', responsible: 1 }), null))
  })
})

describe('карточка кандидата', () => {
  function renderCard(route = '/hr/candidates/7') {
    return renderWithProviders(<Routes><Route path="/hr/candidates/:id" element={<HrCandidateCardPage />} /></Routes>, { route })
  }

  it('показывает профиль, отклик, резюме и собеседования; меняет этап только на допустимый', async () => {
    const user = userEvent.setup()
    api.changeStatus.mockResolvedValue({ ...application, status: 'rejected', status_label: 'Отказ компании' })
    renderCard()
    expect(await screen.findByRole('heading', { name: 'Асанов Бакыт' })).toBeInTheDocument()
    expect(screen.getByText('+996 555 123 456 · b@mail.kg · Бишкек')).toBeInTheDocument()
    expect(screen.getByText('Хочу работать у вас')).toBeInTheDocument()
    expect(screen.getByText(/cv\.pdf/)).toBeInTheDocument()
    expect(await screen.findByText('22.10.2026 15:00')).toBeInTheDocument()
    expect(api.interviews).toHaveBeenCalledWith({ application: 21 })
    await user.click(screen.getByRole('button', { name: /Открыть/ }))
    expect(api.openResume).toHaveBeenCalledWith(21, true)
    await user.click(screen.getByRole('button', { name: /Сменить этап/ }))
    const select = screen.getByLabelText('Новый этап *')
    expect(within(select).queryByRole('option', { name: 'Принят на работу' })).not.toBeInTheDocument()
    await user.selectOptions(select, 'rejected')
    expect(screen.getByText(/собеседования по этому отклику будут отменены/)).toBeInTheDocument()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Сменить этап' }))
    await waitFor(() => expect(api.changeStatus).toHaveBeenCalledWith(21, 'rejected', ''))
  })

  it('принимает на работу только после подтверждения', async () => {
    const user = userEvent.setup()
    api.candidate.mockResolvedValue({ ...candidate, applications: [{ ...application, status: 'offer', status_label: 'Предложение о работе', allowed_statuses: [] }] })
    api.hire.mockResolvedValue({ ...application, status: 'hired', status_label: 'Принят на работу' })
    renderCard()
    await user.click(await screen.findByRole('button', { name: /Принять на работу/ }))
    expect(screen.queryByRole('button', { name: /Назначить собеседование/ })).not.toBeInTheDocument()
    const form = screen.getByRole('dialog')
    await user.selectOptions(within(form).getByLabelText('Должность *'), 'sales_manager')
    await user.type(within(form).getByLabelText('Логин *'), 'bakyt')
    await user.type(within(form).getByLabelText('Пароль *'), 'Str0ngPassw0rd!')
    await user.type(within(form).getByLabelText('Повторите пароль *'), 'Str0ngPassw0rd!')
    await user.click(within(form).getByRole('button', { name: 'Принять на работу' }))
    expect(api.hire).not.toHaveBeenCalled()
    expect(await screen.findByText('Создать учётную запись сотрудника?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Создать и принять' }))
    await waitFor(() => expect(api.hire).toHaveBeenCalledWith(21, {
      username: 'bakyt', email: 'b@mail.kg', first_name: 'Бакыт', last_name: 'Асанов', role: 'sales_manager',
      password: 'Str0ngPassw0rd!', password_confirm: 'Str0ngPassw0rd!',
    }))
  })

  it('для роли вне полномочий HR отправляет запрос администратору без пароля', async () => {
    const user = userEvent.setup()
    api.candidate.mockResolvedValue({ ...candidate, applications: [{ ...application, status: 'offer', status_label: 'Предложение о работе', allowed_statuses: [] }] })
    api.requestAccount.mockResolvedValue({ id: 1, application: 21, candidate: { id: 7, full_name: 'Асанов Бакыт' }, role: 'accountant', role_label: 'Бухгалтер', username: 'bakyt', email: 'b@mail.kg', status: 'pending', status_label: 'Ожидает', created_at: '' })
    renderCard()
    await user.click(await screen.findByRole('button', { name: /Принять на работу/ }))
    const form = screen.getByRole('dialog')
    await user.selectOptions(within(form).getByLabelText('Должность *'), 'accountant')
    expect(within(form).queryByLabelText('Пароль *')).not.toBeInTheDocument()
    await user.type(within(form).getByLabelText('Логин *'), 'bakyt')
    await user.click(within(form).getByRole('button', { name: 'Отправить запрос' }))
    await user.click(await screen.findByRole('button', { name: 'Отправить' }))
    await waitFor(() => expect(api.requestAccount).toHaveBeenCalledWith(21, expect.objectContaining({ role: 'accountant', username: 'bakyt' })))
    expect(api.hire).not.toHaveBeenCalled()
  })

  it('внутренняя заметка привязывается к выбранному отклику', async () => {
    const user = userEvent.setup()
    api.addNote.mockResolvedValue({ id: 1, candidate: 7, application: 21, application_number: '2026-K7QM3D', text: 'Позвонил', author_info: null, created_at: '2026-10-21T10:00:00+06:00' })
    renderCard('/hr/candidates/7?application=21')
    await user.type(await screen.findByLabelText('Новая заметка'), 'Позвонил')
    await user.click(screen.getByRole('button', { name: 'Добавить заметку' }))
    await waitFor(() => expect(api.addNote).toHaveBeenCalledWith(7, 'Позвонил', 21))
  })

  it('возможный дубль: объединение только после подтверждения', async () => {
    const user = userEvent.setup()
    api.candidate.mockResolvedValue({ ...candidate, possible_duplicates: [{ id: 9, full_name: 'Асанов Б.', email: '', phone: '+996 555 123 456', same_email: false, same_phone: true, applications: 2 }] })
    api.mergeCandidate.mockRejectedValue(axiosError(409, { detail: 'нельзя' }))
    renderCard()
    await user.click(await screen.findByRole('button', { name: 'Объединить с этой записью' }))
    expect(api.mergeCandidate).not.toHaveBeenCalled()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Объединить' }))
    await waitFor(() => expect(api.mergeCandidate).toHaveBeenCalledWith(7, 9))
  })
})

describe('календарь собеседований', () => {
  it('неделя: запрашивает период и показывает встречу со ссылкой на отклик', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrInterviewsPage />)
    await waitFor(() => expect(api.interviews).toHaveBeenCalledWith(expect.objectContaining({ date_from: '2026-10-19', date_to: '2026-10-25' })))
    await user.click((await screen.findAllByRole('button', { name: /Асанов Бакыт/ }))[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('link', { name: 'Асанов Бакыт' })).toHaveAttribute('href', '/hr/candidates/7?application=21')
    expect(within(dialog).getByText('Азамат РОП · РОП')).toBeInTheDocument()
  })

  it('день и месяц меняют период, фильтры уходят на сервер', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrInterviewsPage />)
    await screen.findAllByRole('button', { name: /Асанов Бакыт/ })
    await user.click(screen.getByRole('radio', { name: 'Месяц' }))
    await waitFor(() => expect(api.interviews).toHaveBeenLastCalledWith(expect.objectContaining({ date_from: '2026-09-28', date_to: '2026-11-01' })))
    await user.click(screen.getByRole('radio', { name: 'День' }))
    await waitFor(() => expect(api.interviews).toHaveBeenLastCalledWith(expect.objectContaining({ date_from: '2026-10-21', date_to: '2026-10-21' })))
    await user.selectOptions(screen.getByLabelText('Интервьюер'), '5')
    await user.selectOptions(screen.getByLabelText('Статус'), 'cancelled')
    await waitFor(() => expect(api.interviews).toHaveBeenLastCalledWith(expect.objectContaining({ interviewer: '5', status: 'cancelled' })))
  })

  it('предупреждает о дубле и назначает только после подтверждения', async () => {
    const user = userEvent.setup()
    api.scheduleInterview
      .mockRejectedValueOnce(axiosError(409, { code: 'interview_conflict', detail: 'дубль', conflicts: [{ type: 'candidate', interview_id: 11, scheduled_at: '2026-10-22T15:00:00+06:00', message: 'У кандидата уже есть собеседование на близкое время.' }] }))
      .mockResolvedValueOnce(interview)
    api.applications.mockResolvedValue({ count: 1, next: null, previous: null, results: [{ ...application, status: 'shortlisted' }] })
    renderWithProviders(<HrInterviewsPage />)
    await screen.findAllByRole('button', { name: /Асанов Бакыт/ })
    await user.click(screen.getByRole('button', { name: /Назначить собеседование/ }))
    const dialog = screen.getByRole('dialog')
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /Асанов Бакыт/ })).toBeInTheDocument())
    await user.selectOptions(within(dialog).getByLabelText('Кандидат *'), '21')
    await user.type(within(dialog).getByLabelText('Дата и время *'), '2026-10-22T16:00')
    await user.selectOptions(within(dialog).getByLabelText('Интервьюер *'), '5')
    await user.type(within(dialog).getByLabelText('Место проведения *'), 'Офис, каб. 3')
    await user.click(within(dialog).getByRole('button', { name: 'Назначить' }))
    expect(await within(dialog).findByText(/уже есть собеседование на близкое время/)).toBeInTheDocument()
    expect(api.scheduleInterview).toHaveBeenLastCalledWith(expect.objectContaining({ confirm: false, application: 21, scheduled_at: '2026-10-22T16:00' }))
    await user.click(within(dialog).getByRole('button', { name: 'Всё равно назначить' }))
    await waitFor(() => expect(api.scheduleInterview).toHaveBeenLastCalledWith(expect.objectContaining({ confirm: true })))
  })

  it('результат требует оценок', async () => {
    const user = userEvent.setup()
    const past = { ...interview, scheduled_at: '2026-10-01T15:00:00+06:00' }
    api.interviews.mockResolvedValue([past])
    api.recordResult.mockResolvedValue({ ...past, status: 'completed' })
    renderWithProviders(<Routes><Route path="/hr/candidates/:id" element={<HrCandidateCardPage />} /></Routes>, { route: '/hr/candidates/7' })
    await user.click(await screen.findByRole('button', { name: /01\.10\.2026 15:00/ }))
    await user.click(screen.getByRole('button', { name: /Зафиксировать результат/ }))
    const dialog = screen.getByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText('Решение *'), 'passed')
    await user.selectOptions(within(dialog).getByLabelText('Следующий шаг *'), 'offer')
    await user.click(within(dialog).getByRole('button', { name: 'Зафиксировать' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Поставьте оценки')
    await user.click(within(dialog).getByRole('radio', { name: 'Общая оценка: 4 из 5' }))
    await user.click(within(dialog).getByRole('radio', { name: 'Профессиональные навыки: 5 из 5' }))
    await user.click(within(dialog).getByRole('button', { name: 'Зафиксировать' }))
    await waitFor(() => expect(api.recordResult).toHaveBeenCalledWith(11, expect.objectContaining({ overall_rating: 4, skills_rating: 5, result: 'passed', next_step: 'offer' })))
  })
})

describe('вакансии', () => {
  it('статусы меняются через подтверждение', async () => {
    const user = userEvent.setup()
    api.setVacancyStatus.mockResolvedValue({ ...vacancy, status: 'published' })
    renderWithProviders(<HrVacanciesPage />)
    expect(await screen.findByRole('link', { name: 'Менеджер по продажам' })).toHaveAttribute('href', '/hr/vacancies/3')
    await user.click(screen.getByRole('button', { name: 'Статус «Менеджер по продажам»' }))
    await user.click(screen.getByRole('menuitem', { name: /Опубликовать/ }))
    expect(api.setVacancyStatus).not.toHaveBeenCalled()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Опубликовать' }))
    await waitFor(() => expect(api.setVacancyStatus).toHaveBeenCalledWith(3, 'published'))
  })

  it('новая вакансия сохраняется черновиком со всеми полями', async () => {
    const user = userEvent.setup()
    api.createVacancy.mockResolvedValue(vacancy)
    renderWithProviders(<Routes><Route path="/hr/vacancies/:id" element={<HrVacancyEditPage />} /></Routes>, { route: '/hr/vacancies/new' })
    await user.click(await screen.findByRole('button', { name: 'Сохранить черновик' }))
    expect(screen.getByText('Укажите название.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Название *'), 'SMM-специалист')
    await user.type(screen.getByLabelText('От'), '50000')
    await user.type(screen.getByLabelText('До'), '40000')
    await user.click(screen.getByRole('button', { name: 'Сохранить черновик' }))
    expect(screen.getByText('«До» должно быть не меньше «от».')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('До'))
    await user.type(screen.getByLabelText('До'), '70000')
    await user.type(screen.getByLabelText('Обязанности'), 'Контент{enter}Аналитика')
    await user.click(screen.getByRole('button', { name: 'Сохранить черновик' }))
    await waitFor(() => expect(api.createVacancy).toHaveBeenCalledWith(expect.objectContaining({
      title: 'SMM-специалист', salary_min: 50000, salary_max: 70000, responsibilities: 'Контент\nАналитика', work_format: 'office', closes_on: null,
    })))
    expect(api.setVacancyStatus).not.toHaveBeenCalled()
  })
})

describe('отчёты', () => {
  const definitions = { new_applications: 'Новые отклики — по дате создания отклика.' }
  const daily: DailyReport = {
    date: '2026-10-21', new_applications: 2, new_by_vacancy: [{ label: 'Менеджер по продажам', count: 2 }], new_applications_list: [],
    passed_screening: 1, interviews_scheduled: 2, interviews_planned: 3, interviews_list: [], interviews_conducted: 1,
    interviews_rescheduled: 1, interviews_cancelled: 1, interviews_no_show: 0, awaiting_decision_now: 2, decisions: 3, offers: 1, hired: 1,
    rejected: 1, withdrawn: 0, definitions,
  }
  const monthly: PeriodReport = {
    month: '2026-10', date_from: '2026-10-01', date_to: '2026-10-31', new_applications: 9, interviews_conducted: 5, interviews_scheduled: 6,
    interviews_cancelled: 1, interviews_rescheduled: 2, interviews_no_show: 0, passed_screening: 5, hired: 2, rejected: 3, withdrawn: 1, offers: 3,
    by_stage: [], funnel: [{ status: 'new', status_label: 'Новый отклик', count: 9, conversion_percent: null }, { status: 'screening', status_label: 'Первичный просмотр', count: 6, conversion_percent: 66.7 }],
    by_vacancy: [{ label: 'Менеджер по продажам', applications: 6, interviews: 3, offers: 1, hired: 1, rejected: 2 }],
    by_source: [{ source: 'referral', label: 'Рекомендация', count: 4, enough_data: false, interview_percent: null, hired_percent: null }],
    stage_durations: [], average_days_to_hire: 12.5, vacancies_closed: 1, vacancy_days_to_close: 20, definitions,
  }

  it('день, месяц и период; фильтры и экспорт CSV', async () => {
    const user = userEvent.setup()
    api.daily.mockResolvedValue(daily)
    api.monthly.mockResolvedValue(monthly)
    api.exportMonthly.mockResolvedValue()
    renderWithProviders(<HrReportsPage />)
    expect(await screen.findByText('Прошли первичный отбор')).toBeInTheDocument()
    expect(api.daily).toHaveBeenLastCalledWith({ date: '2026-10-21' })
    await user.click(screen.getByRole('tab', { name: 'Месяц' }))
    expect(await screen.findByText('66,7%')).toBeInTheDocument()
    expect(screen.getByText('мало данных')).toBeInTheDocument()
    expect(screen.getByText('В среднем 20 дн. от публикации')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Ответственный'), '1')
    await waitFor(() => expect(api.monthly).toHaveBeenLastCalledWith({ month: '2026-10', responsible: '1' }))
    await user.click(screen.getByRole('button', { name: /Экспорт CSV/ }))
    expect(api.exportMonthly).toHaveBeenCalledWith({ month: '2026-10', responsible: '1' })
    await user.click(screen.getByRole('tab', { name: 'Период' }))
    await waitFor(() => expect(api.monthly).toHaveBeenLastCalledWith({ date_from: '2026-10-01', date_to: '2026-10-21', responsible: '1' }))
  })
})
