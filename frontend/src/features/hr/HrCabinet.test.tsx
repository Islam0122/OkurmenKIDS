import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { Candidate, DailyReport, HRDashboard, Interview, MonthlyReport, RecruitmentMeta, Vacancy } from '@/types/hr'

vi.mock('@/api/hr', () => ({
  hrApi: { meta: vi.fn(), list: vi.fn(), employee: vi.fn(), create: vi.fn(), update: vi.fn(), setPassword: vi.fn(), setActive: vi.fn() },
  recruitmentApi: {
    meta: vi.fn(), dashboard: vi.fn(), vacancies: vi.fn(), createVacancy: vi.fn(), updateVacancy: vi.fn(), candidates: vi.fn(),
    candidate: vi.fn(), createCandidate: vi.fn(), updateCandidate: vi.fn(), changeStatus: vi.fn(), addNote: vi.fn(), history: vi.fn(),
    hire: vi.fn(), interviews: vi.fn(), interview: vi.fn(), scheduleInterview: vi.fn(), updateInterview: vi.fn(), cancelInterview: vi.fn(),
    recordResult: vi.fn(), daily: vi.fn(), monthly: vi.fn(), exportDaily: vi.fn(), exportMonthly: vi.fn(),
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: 'hr_manager', first_name: 'Айгуль', last_name: 'HR' }, status: 'authenticated', logout: vi.fn() }),
}))

import { hrApi, recruitmentApi } from '@/api/hr'

import { HrCandidateCardPage } from './CandidateCardPage'
import { HrCandidatesPage } from './CandidatesPage'
import { HrDashboardPage } from './DashboardPage'
import { HrInterviewsPage } from './InterviewsPage'
import { HrReportsPage } from './ReportsPage'
import { HrVacanciesPage } from './VacanciesPage'

const api = vi.mocked(recruitmentApi)
const employeesApi = vi.mocked(hrApi)

const meta: RecruitmentMeta = {
  candidate_statuses: [{ value: 'new', label: 'Новый кандидат' }, { value: 'offer', label: 'Предложение о работе' }],
  sources: [{ value: 'job_site', label: 'Сайт вакансий' }, { value: 'referral', label: 'Рекомендация' }],
  vacancy_statuses: [{ value: 'open', label: 'Открыта' }, { value: 'paused', label: 'Приостановлена' }, { value: 'closed', label: 'Закрыта' }],
  interview_statuses: [{ value: 'scheduled', label: 'Назначено' }, { value: 'completed', label: 'Проведено' }, { value: 'cancelled', label: 'Отменено' }],
  interview_formats: [{ value: 'in_person', label: 'Очно' }, { value: 'online', label: 'Онлайн' }, { value: 'phone', label: 'По телефону' }],
  interview_results: [{ value: 'passed', label: 'Успешно' }, { value: 'failed', label: 'Не прошёл' }],
  next_steps: [{ value: 'offer', label: 'Сделать предложение' }, { value: 'reject', label: 'Отказать' }],
  people: [{ id: 1, full_name: 'Айгуль HR', role_label: 'HR-менеджер' }, { id: 5, full_name: 'Азамат РОП', role_label: 'РОП' }],
  today: '2026-10-21',
}

const vacancy: Vacancy = {
  id: 3, title: 'Менеджер по продажам', description: '', department: 'Продажи', status: 'open', status_label: 'Открыта',
  responsible: 1, responsible_info: meta.people[0], candidates_count: 1, created_at: '2026-10-01T09:00:00+06:00', updated_at: '2026-10-01T09:00:00+06:00',
}

const candidate: Candidate = {
  id: 7, last_name: 'Асанов', first_name: 'Бакыт', middle_name: '', full_name: 'Асанов Бакыт', phone: '+996 555 123 456', email: 'b@mail.kg',
  vacancy: 3, vacancy_info: { id: 3, title: 'Менеджер по продажам', status: 'open' }, position: '', position_label: 'Менеджер по продажам',
  source: 'job_site', source_label: 'Сайт вакансий', source_details: '', added_on: '2026-10-20', responsible: 1, responsible_info: meta.people[0],
  notes: 'Опыт 3 года', status: 'interview_scheduled', status_label: 'Собеседование назначено', status_changed_at: '2026-10-20T12:00:00+06:00',
  hired_user_info: null, allowed_statuses: [{ value: 'rejected', label: 'Отказ' }, { value: 'withdrawn', label: 'Кандидат отказался' }],
  next_interview_at: '2026-10-22T15:00:00+06:00', created_at: '2026-10-20T09:00:00+06:00', updated_at: '2026-10-20T09:00:00+06:00',
}

const interview: Interview = {
  id: 11, candidate: 7, candidate_info: { id: 7, full_name: 'Асанов Бакыт', status: 'interview_scheduled', status_label: 'Собеседование назначено' },
  vacancy: 3, vacancy_info: { id: 3, title: 'Менеджер по продажам' }, scheduled_at: '2026-10-22T15:00:00+06:00', duration_minutes: 60,
  format: 'online', format_label: 'Онлайн', location: '', meeting_url: 'https://meet.example.com/abc', interviewer: 5,
  interviewer_info: meta.people[1], notes: '', status: 'scheduled', status_label: 'Назначено', reschedule_count: 0, cancel_reason: '',
  cancelled_at: null, result: '', result_label: '', result_comment: '', next_step: '', next_step_label: '', next_step_date: null,
  completed_at: null, created_at: '2026-10-20T12:00:00+06:00',
}

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR', undefined, undefined, { status, data } as AxiosResponse)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue(meta)
  api.vacancies.mockResolvedValue({ count: 1, next: null, previous: null, results: [vacancy] })
  api.candidates.mockResolvedValue({ count: 1, next: null, previous: null, results: [candidate] })
  api.candidate.mockResolvedValue(candidate)
  api.history.mockResolvedValue([])
  api.interviews.mockResolvedValue([interview])
  employeesApi.meta.mockResolvedValue({ roles: [{ value: 'sales_manager', label: 'Менеджер по продажам' }], protected_roles: [] })
})

describe('главная HR', () => {
  it('показывает реальные показатели, ближайшие встречи и события', async () => {
    const data: HRDashboard = {
      period: { date_from: '2026-10-01', date_to: '2026-10-21' }, employees_active: 12, employees_new: 2, candidates_total: 9,
      candidates_in_progress: 6, candidates_by_status: {} as HRDashboard['candidates_by_status'], interviews_scheduled: 4, interviews_today: 1,
      awaiting_decision: 3, interview_passed: 2, offers: 1, hired: 2, rejected: 1, withdrawn: 0, vacancies_open: 5,
      upcoming_interviews: [{ id: 11, scheduled_at: '2026-10-22T15:00:00+06:00', duration_minutes: 60, status: 'scheduled', status_label: 'Назначено', format_label: 'Онлайн', candidate: { id: 7, full_name: 'Асанов Бакыт' }, interviewer: 'Азамат РОП', position: 'Менеджер по продажам' }],
      recent_activity: [{ id: 1, kind: 'candidate_created', kind_label: 'Добавлен кандидат', message: 'Менеджер по продажам', created_at: '2026-10-20T09:00:00+06:00', actor: 'Айгуль HR', candidate: { id: 7, full_name: 'Асанов Бакыт' }, employee: null, from_status: '', to_status: 'new' }],
    }
    api.dashboard.mockResolvedValue(data)
    renderWithProviders(<HrDashboardPage />)
    expect(await screen.findByText('Активные сотрудники')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('Открытые вакансии').closest('div')?.parentElement).toHaveTextContent('5')
    expect(screen.getByText('22.10.2026 15:00')).toBeInTheDocument()
    expect(screen.getByText('Добавлен кандидат')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Асанов Бакыт' })[0]).toHaveAttribute('href', '/hr/candidates/7')
  })
})

describe('кандидаты', () => {
  it('фильтры уходят на сервер, строка ведёт в карточку', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrCandidatesPage />)
    expect(await screen.findByRole('link', { name: 'Асанов Бакыт' })).toHaveAttribute('href', '/hr/candidates/7')
    await user.selectOptions(screen.getByLabelText('Источник'), 'referral')
    await user.click(screen.getByLabelText(/Только в работе/))
    await waitFor(() => expect(api.candidates).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'referral', active: 'true', page: 1 })))
  })

  it('проверяет обязательные поля и создаёт кандидата', async () => {
    const user = userEvent.setup()
    api.createCandidate.mockResolvedValue(candidate)
    renderWithProviders(<HrCandidatesPage />)
    await screen.findByRole('link', { name: 'Асанов Бакыт' })
    await user.click(screen.getByRole('button', { name: /Новый кандидат/ }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Укажите фамилию, имя, телефон или email, вакансию или должность.')
    expect(api.createCandidate).not.toHaveBeenCalled()
    await user.type(within(dialog).getByLabelText('Фамилия *'), 'Бекова')
    await user.type(within(dialog).getByLabelText('Имя *'), 'Айым')
    await user.type(within(dialog).getByLabelText('Email'), 'a@mail.kg')
    await user.selectOptions(within(dialog).getByLabelText('Вакансия'), '3')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.createCandidate).toHaveBeenCalledWith(expect.objectContaining({
      last_name: 'Бекова', first_name: 'Айым', email: 'a@mail.kg', vacancy: 3, source: 'job_site', added_on: '2026-10-21', responsible: 1,
    })))
  })
})

describe('карточка кандидата', () => {
  function renderCard() {
    return renderWithProviders(<Routes><Route path="/hr/candidates/:id" element={<HrCandidateCardPage />} /></Routes>, { route: '/hr/candidates/7' })
  }

  it('показывает данные, собеседования и меняет этап только на допустимый', async () => {
    const user = userEvent.setup()
    api.changeStatus.mockResolvedValue({ ...candidate, status: 'rejected', status_label: 'Отказ' })
    renderCard()
    expect(await screen.findByRole('heading', { name: 'Асанов Бакыт' })).toBeInTheDocument()
    expect(screen.getByText('+996 555 123 456')).toBeInTheDocument()
    expect(await screen.findByText('22.10.2026 15:00')).toBeInTheDocument()
    expect(api.interviews).toHaveBeenCalledWith({ candidate: 7 })
    await user.click(screen.getByRole('button', { name: /Сменить этап/ }))
    const select = screen.getByLabelText('Новый этап *')
    expect(within(select).queryByRole('option', { name: 'Принят на работу' })).not.toBeInTheDocument()
    await user.selectOptions(select, 'rejected')
    expect(screen.getByText(/собеседования кандидата будут отменены/)).toBeInTheDocument()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Сменить этап' }))
    await waitFor(() => expect(api.changeStatus).toHaveBeenCalledWith(7, 'rejected', ''))
  })

  it('принимает на работу кандидата с предложением', async () => {
    const user = userEvent.setup()
    api.candidate.mockResolvedValue({ ...candidate, status: 'offer', status_label: 'Предложение о работе', allowed_statuses: [] })
    api.hire.mockResolvedValue({ ...candidate, status: 'hired', status_label: 'Принят на работу' })
    renderCard()
    await user.click(await screen.findByRole('button', { name: /Принять на работу/ }))
    expect(screen.queryByRole('button', { name: /Назначить собеседование/ })).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Логин *'), 'bakyt')
    await user.selectOptions(screen.getByLabelText('Должность *'), 'sales_manager')
    await user.type(screen.getByLabelText('Пароль *'), 'Str0ngPassw0rd!')
    await user.type(screen.getByLabelText('Повторите пароль *'), 'Str0ngPassw0rd!')
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Принять на работу' }))
    await waitFor(() => expect(api.hire).toHaveBeenCalledWith(7, {
      username: 'bakyt', email: 'b@mail.kg', first_name: 'Бакыт', last_name: 'Асанов', role: 'sales_manager',
      password: 'Str0ngPassw0rd!', password_confirm: 'Str0ngPassw0rd!',
    }))
  })

  it('добавляет запись в историю взаимодействия', async () => {
    const user = userEvent.setup()
    api.addNote.mockResolvedValue({ id: 1, kind: 'candidate_note', kind_label: 'Взаимодействие с кандидатом', message: 'Позвонил', created_at: '2026-10-21T10:00:00+06:00', actor: 'Айгуль HR', candidate: null, employee: null, from_status: '', to_status: '' })
    renderCard()
    await user.type(await screen.findByLabelText('Новая запись'), 'Позвонил')
    await user.click(screen.getByRole('button', { name: 'Добавить запись' }))
    await waitFor(() => expect(api.addNote).toHaveBeenCalledWith(7, 'Позвонил'))
  })
})

describe('календарь собеседований', () => {
  it('неделя: запрашивает период и показывает встречу; событие открывает карточку со ссылкой на кандидата', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrInterviewsPage />)
    await waitFor(() => expect(api.interviews).toHaveBeenCalledWith(expect.objectContaining({ date_from: '2026-10-19', date_to: '2026-10-25' })))
    await user.click((await screen.findAllByRole('button', { name: /Асанов Бакыт/ }))[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('link', { name: 'Асанов Бакыт' })).toHaveAttribute('href', '/hr/candidates/7')
    expect(within(dialog).getByText('Азамат РОП · РОП')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /Зафиксировать результат/ })).toBeInTheDocument()
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
    renderWithProviders(<HrInterviewsPage />)
    await screen.findAllByRole('button', { name: /Асанов Бакыт/ })
    await user.click(screen.getByRole('button', { name: /Назначить собеседование/ }))
    const dialog = screen.getByRole('dialog')
    await user.selectOptions(await within(dialog).findByLabelText('Кандидат *'), '7')
    await user.type(within(dialog).getByLabelText('Дата и время *'), '2026-10-22T16:00')
    await user.selectOptions(within(dialog).getByLabelText('Интервьюер *'), '5')
    await user.type(within(dialog).getByLabelText('Место проведения *'), 'Офис, каб. 3')
    await user.click(within(dialog).getByRole('button', { name: 'Назначить' }))
    expect(await within(dialog).findByText(/уже есть собеседование на близкое время/)).toBeInTheDocument()
    expect(api.scheduleInterview).toHaveBeenLastCalledWith(expect.objectContaining({ confirm: false, candidate: 7, scheduled_at: '2026-10-22T16:00' }))
    await user.click(within(dialog).getByRole('button', { name: 'Всё равно назначить' }))
    await waitFor(() => expect(api.scheduleInterview).toHaveBeenLastCalledWith(expect.objectContaining({ confirm: true })))
  })
})

describe('вакансии', () => {
  it('создаёт вакансию с ответственным', async () => {
    const user = userEvent.setup()
    api.createVacancy.mockResolvedValue(vacancy)
    renderWithProviders(<HrVacanciesPage />)
    expect(await screen.findByText('Менеджер по продажам')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Новая вакансия/ }))
    await user.type(screen.getByLabelText('Название *'), 'SMM-специалист')
    await user.selectOptions(screen.getByLabelText('Ответственный'), '1')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.createVacancy).toHaveBeenCalledWith({ title: 'SMM-специалист', department: '', description: '', status: 'open', responsible: 1 }))
  })
})

describe('отчёты', () => {
  const daily: DailyReport = {
    date: '2026-10-21', new_candidates: 2, new_candidates_list: [], interviews_planned: 3, interviews_list: [], interviews_conducted: 1,
    interviews_rescheduled: 1, interviews_cancelled: 1, awaiting_decision_now: 2, decisions: 3, offers: 1, hired: 1, rejected: 1, withdrawn: 0,
  }
  const monthly: MonthlyReport = {
    month: '2026-10', new_candidates: 9, interviews_conducted: 5, interviews_cancelled: 1, interviews_rescheduled: 2, hired: 2, rejected: 3,
    withdrawn: 1, offers: 3, by_stage: [], funnel: [{ status: 'new', status_label: 'Новый кандидат', count: 9, conversion_percent: null }, { status: 'contacted', status_label: 'Первичный контакт', count: 6, conversion_percent: 66.7 }],
    by_vacancy: [{ label: 'Менеджер по продажам', count: 6 }], by_source: [{ label: 'Рекомендация', count: 4 }], stage_durations: [], average_days_to_hire: 12.5,
  }

  it('день и месяц, фильтры и экспорт CSV', async () => {
    const user = userEvent.setup()
    api.daily.mockResolvedValue(daily)
    api.monthly.mockResolvedValue(monthly)
    api.exportMonthly.mockResolvedValue()
    renderWithProviders(<HrReportsPage />)
    expect(await screen.findByText('Принятые решения')).toBeInTheDocument()
    expect(api.daily).toHaveBeenLastCalledWith({ date: '2026-10-21' })
    await user.click(screen.getByRole('tab', { name: 'Месяц' }))
    expect(await screen.findByText('66,7%')).toBeInTheDocument()
    expect(screen.getByText('Недостаточно истории переходов за месяц.')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Источник'), 'referral')
    await waitFor(() => expect(api.monthly).toHaveBeenLastCalledWith({ month: '2026-10', source: 'referral' }))
    await user.click(screen.getByRole('button', { name: /Экспорт CSV/ }))
    expect(api.exportMonthly).toHaveBeenCalledWith({ month: '2026-10', source: 'referral' })
  })
})
