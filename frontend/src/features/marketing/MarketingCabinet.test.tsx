import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { ContentItem, MarketingDashboard, MarketingMeta, MarketingReport, MarketingTask } from '@/types/marketing'
import type { MyStatus } from '@/types/staffAttendance'

vi.mock('@/api/marketing', () => ({
  marketingApi: {
    meta: vi.fn(), dashboard: vi.fn(), report: vi.fn(), content: vi.fn(), createContent: vi.fn(), updateContent: vi.fn(),
    deleteContent: vi.fn(), tasks: vi.fn(), createTask: vi.fn(), updateTask: vi.fn(), deleteTask: vi.fn(),
  },
}))

vi.mock('@/api/accounting', () => ({
  accountingApi: { mySalary: vi.fn(), downloadMySalaryPdf: vi.fn(), myPayoutPlan: vi.fn().mockResolvedValue({ results: [] }) },
}))

vi.mock('@/api/staffAttendance', () => ({
  staffAttendanceApi: { myStatus: vi.fn() },
}))

// Сам поток отметки (QR → геолокация → сервер) не меняется и проверяется в
// StaffAttendance.test; здесь важно, что кабинет открывает именно его.
vi.mock('@/features/staffAttendance/MarkFlow', () => ({
  MarkFlow: ({ action }: { action: string }) => <p>Поток отметки: {action}</p>,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 3, role: 'marketing', first_name: 'Аида', last_name: 'Маркетинг' }, status: 'authenticated', logout: vi.fn() }),
}))

import { accountingApi } from '@/api/accounting'
import { marketingApi } from '@/api/marketing'
import { MySalaryRedirect } from '@/app/router/MySalaryRedirect'
import { MySalaryPage } from '@/features/accounting/MySalaryPage'
import type { MySalary } from '@/types/accounting'
import { staffAttendanceApi } from '@/api/staffAttendance'

import { MarketingContentPlanPage } from './ContentPlanPage'
import { MarketingLayout } from './MarketingLayout'
import { MarketingOverviewPage } from './OverviewPage'
import { MarketingReportsPage } from './ReportsPage'
import { MarketingTasksPage } from './TasksPage'

const api = vi.mocked(marketingApi)
const attendance = vi.mocked(staffAttendanceApi)

const meta: MarketingMeta = {
  channels: [{ value: 'instagram', label: 'Instagram' }, { value: 'tiktok', label: 'TikTok' }],
  formats: [{ value: 'post', label: 'Пост' }, { value: 'reels', label: 'Reels / короткое видео' }],
  content_statuses: [
    { value: 'idea', label: 'Идея' }, { value: 'preparing', label: 'Подготовка' }, { value: 'review', label: 'Согласование' },
    { value: 'scheduled', label: 'Запланировано' }, { value: 'published', label: 'Опубликовано' },
  ],
  task_statuses: [{ value: 'todo', label: 'К выполнению' }, { value: 'in_progress', label: 'В работе' }, { value: 'done', label: 'Выполнено' }],
  priorities: [{ value: 'low', label: 'Низкий' }, { value: 'medium', label: 'Средний' }, { value: 'high', label: 'Высокий' }],
  team: [{ id: 3, full_name: 'Аида Маркетинг' }, { id: 4, full_name: 'Бермет Контент' }],
  me: 3,
  today: '2026-10-21',
}

const task: MarketingTask = {
  id: 10, title: 'Снять видео с урока', description: '', due_date: '2026-10-20', priority: 'high', priority_label: 'Высокий',
  status: 'in_progress', status_label: 'В работе', is_overdue: true, responsible: 3, responsible_info: { id: 3, full_name: 'Аида Маркетинг' },
  completed_at: null, created_by_info: { id: 3, full_name: 'Аида Маркетинг' }, created_at: '2026-10-01T10:00:00+06:00',
  updated_at: '2026-10-01T10:00:00+06:00', can_delete: true,
}

const post: ContentItem = {
  id: 20, title: 'Открытый урок по робототехнике', channel: 'instagram', channel_label: 'Instagram', format: 'reels',
  format_label: 'Reels / короткое видео', publish_date: '2026-10-23', publish_time: '18:30:00', status: 'scheduled',
  status_label: 'Запланировано', responsible: 4, responsible_info: { id: 4, full_name: 'Бермет Контент' }, description: '', post_url: '',
  published_at: null, created_by_info: { id: 4, full_name: 'Бермет Контент' }, created_at: '2026-10-01T10:00:00+06:00',
  updated_at: '2026-10-01T10:00:00+06:00', can_delete: false,
}

const dashboard: MarketingDashboard = {
  today: '2026-10-21',
  period: { date_from: '2026-10-01', date_to: '2026-10-31' },
  tasks: { open: 5, in_progress: 2, overdue: 1, due_today: 0, mine_open: 3, done_in_period: 7 },
  content: { ideas: 4, in_work: 2, scheduled: 6, planned_in_period: 12, published_in_period: 8 },
  upcoming_tasks: [task],
  upcoming_content: [post],
}

const report: MarketingReport = {
  period: { kind: 'month', date_from: '2026-10-01', date_to: '2026-10-31' },
  today: '2026-10-21',
  tasks: { created: 9, completed: 7, completed_on_time: 6, completed_late: 1, overdue_now: 1, open_due_in_period: 2 },
  content: { planned: 12, prepared: 10, published: 8, plan_due: 9, plan_done: 8, plan_completion: 89 },
  series: [{ date_from: '2026-10-01', date_to: '2026-10-07', published: 3, planned: 3, tasks_completed: 2 }],
  by_channel: [{ channel: 'instagram', label: 'Instagram', planned: 8, published: 6 }],
  by_person: [{ id: 3, full_name: 'Аида Маркетинг', tasks_completed: 4, tasks_open: 2, content_planned: 6, content_published: 5 }],
}

const employee = { id: 3, full_name: 'Аида Маркетинг', username: 'aida', role: 'marketing' as const, role_label: 'Маркетинг', photo_url: null }
const myStatus = (over: Partial<MyStatus> = {}): MyStatus => ({
  employee, state: 'not_arrived', next_action: 'check_in', server_time: '2026-10-21T08:50:00+06:00', timezone: 'Asia/Bishkek',
  today: {
    key: '3:2026-10-21', employee, date: '2026-10-21', status: 'not_arrived', status_label: 'Ещё не пришёл', check_in: null, check_out: null,
    duration_seconds: null, late_minutes: 0, is_late: false, is_adjusted: false, expected_start: '2026-10-21T09:00:00+06:00',
    expected_end: '2026-10-21T18:00:00+06:00', sessions_count: 0, last_session_id: null, locations: [], sessions: [],
  },
  open_session: null, stale_session: null, access: { can_view_reports: false, can_adjust: false, can_manage: false },
  ...over,
})

const zero = { gross: '0.00', tax: '0.00', other_deductions: '0.00', net: '0.00' }
const NO_SALARY: MySalary = {
  employee_name: 'Аида Маркетинг', has_profile: false, profile: null,
  totals: { accrued: '0.00', deducted: '0.00', net: '0.00', paid: '0.00', due: '0.00', pending_approval: '0.00', estimated: '0.00', estimated_deductions: null, estimated_deductions_note: '' },
  deductions: [],
  earnings: {
    as_of: '2026-10-21', schedule: [], not_included: { ...zero, note: '', items: [] }, earned: zero, official: zero, paid: '0.00',
    company_owes: '0.00', earned_unpaid: '0.00', next_payment_date: null, difference: '0.00', difference_reasons: [], items: [], deductions: [],
  },
  next_planned_payment_date: null, estimates: [], last_payment: null,
  current_month: { year: 2026, month: 10, label: 'Октябрь 2026', accrued: '0.00', periods: [] },
  history: [], payments: [], filters: { year: null, month: null, period_type: null },
}

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue(meta)
  api.dashboard.mockResolvedValue(dashboard)
  api.report.mockResolvedValue(report)
  api.tasks.mockResolvedValue(page([task]))
  api.content.mockResolvedValue(page([post]))
  api.updateTask.mockResolvedValue({ ...task, status: 'done' })
  attendance.myStatus.mockResolvedValue(myStatus())
  vi.mocked(accountingApi.mySalary).mockResolvedValue(NO_SALARY)
})

function renderCabinet(route = '/marketing') {
  return renderWithProviders(
    <Routes>
      <Route path="/my-salary" element={<MySalaryRedirect />} />
      <Route path="/marketing" element={<MarketingLayout />}>
        <Route index element={<MarketingOverviewPage />} />
        <Route path="tasks" element={<MarketingTasksPage />} />
        <Route path="my-salary" element={<MySalaryPage />} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('оболочка кабинета маркетинга', () => {
  it('пять разделов в меню и кнопка отметки прихода из существующего механизма', async () => {
    const user = userEvent.setup()
    renderCabinet()
    const [sidebar, bottom] = screen.getAllByRole('navigation', { name: 'Разделы кабинета маркетинга' })
    const links = (nav: HTMLElement) => within(nav).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])
    expect(links(sidebar)).toEqual([
      ['Обзор', '/marketing'], ['Контент-план', '/marketing/content'], ['Задачи', '/marketing/tasks'],
      ['Отчёты', '/marketing/reports'], ['Моя зарплата', '/marketing/my-salary'],
    ])
    // Нижняя панель телефона: те же адреса, короткие подписи.
    expect(links(bottom)).toEqual([
      ['Обзор', '/marketing'], ['План', '/marketing/content'], ['Задачи', '/marketing/tasks'],
      ['Отчёты', '/marketing/reports'], ['Зарплата', '/marketing/my-salary'],
    ])
    await user.click(await screen.findByRole('button', { name: 'Отметить приход' }))
    const dialog = await screen.findByRole('dialog', { name: 'Отметить приход' })
    expect(within(dialog).getByText('Поток отметки: check_in')).toBeInTheDocument()
  })

  it('на работе — показывает время прихода и следующей отметкой предлагает уход', async () => {
    attendance.myStatus.mockResolvedValue(myStatus({
      state: 'at_work', next_action: 'check_out',
      today: { ...myStatus().today, status: 'at_work', check_in: '2026-10-21T08:55:00+06:00' },
    }))
    renderCabinet()
    const button = await screen.findByRole('button', { name: 'Отметить уход' })
    expect(button).toHaveTextContent('08:55')
  })
})

describe('моя зарплата', () => {
  it('та же страница зарплаты: без начислений — пустое состояние, запрос без id сотрудника', async () => {
    renderCabinet('/marketing/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
    expect(screen.getByText('Начислений пока нет')).toBeInTheDocument()
    expect(screen.getByText('Зарплатный профиль ещё не настроен бухгалтерией.')).toBeInTheDocument()
    expect(accountingApi.mySalary).toHaveBeenCalledWith({})
  })

  it('короткий адрес /my-salary ведёт маркетолога в его кабинет', async () => {
    renderCabinet('/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
    expect(screen.getAllByRole('navigation', { name: 'Разделы кабинета маркетинга' })).toHaveLength(2)
  })
})

describe('обзор', () => {
  it('приветствие, сводка из API, ближайшие задачи и публикации', async () => {
    renderCabinet()
    expect(await screen.findByRole('heading', { name: /Аида!/ })).toBeInTheDocument()
    expect(screen.getByText('Среда, 21 октября 2026')).toBeInTheDocument()
    expect(screen.getByText('У вас 3 открытые задачи, просрочено в отделе: 1.')).toBeInTheDocument()
    expect(screen.getByText('Из 12 в плане месяца')).toBeInTheDocument()
    expect(screen.getByText('Снять видео с урока')).toBeInTheDocument()
    expect(screen.getByText('Открытый урок по робототехнике')).toBeInTheDocument()
    expect(screen.getByText(/Просрочено: вт, 20 окт/)).toBeInTheDocument()
  })

  it('быстро отмечает задачу выполненной', async () => {
    const user = userEvent.setup()
    renderCabinet()
    await user.click(await screen.findByRole('button', { name: 'Отметить выполненной: Снять видео с урока' }))
    await waitFor(() => expect(api.updateTask).toHaveBeenCalledWith(10, { status: 'done' }))
  })

  it('ошибка загрузки — сообщение сервера и повтор', async () => {
    api.dashboard.mockRejectedValue(new AxiosError('fail', 'ERR', undefined, undefined, { status: 500, data: { detail: 'Сервер недоступен' } } as AxiosResponse))
    renderCabinet()
    expect(await screen.findByText('Сервер недоступен')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Повторить|Попробовать/ })).toBeInTheDocument()
  })
})

describe('задачи', () => {
  it('фильтры уходят на сервер', async () => {
    const user = userEvent.setup()
    renderCabinet('/marketing/tasks')
    await screen.findByText('Снять видео с урока')
    expect(api.tasks).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'open', page: 1 }))
    await user.click(screen.getByRole('radio', { name: 'Просроченные' }))
    await waitFor(() => expect(api.tasks).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'overdue' })))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Срок' }), 'week')
    await user.click(screen.getByRole('button', { name: 'Только мои' }))
    await waitFor(() => expect(api.tasks).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'overdue', due: 'week', mine: '1' })))
  })

  it('создание: проверка названия и отправка формы', async () => {
    const user = userEvent.setup()
    api.createTask.mockResolvedValue({ ...task, id: 11 })
    renderCabinet('/marketing/tasks')
    await screen.findByText('Снять видео с урока')
    await user.click(screen.getByRole('button', { name: 'Новая задача' }))
    const dialog = await screen.findByRole('dialog', { name: 'Новая задача' })
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Укажите название задачи.')
    expect(api.createTask).not.toHaveBeenCalled()

    await user.type(within(dialog).getByLabelText(/Название/), 'Подготовить пост')
    await user.selectOptions(within(dialog).getByLabelText('Приоритет'), 'high')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.createTask).toHaveBeenCalledWith({
      title: 'Подготовить пост', description: '', due_date: null, priority: 'high', status: 'todo', responsible: 3,
    }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Новая задача' })).not.toBeInTheDocument())
  })
})

describe('контент-план', () => {
  it('календарь месяца и мобильная лента из одного запроса за видимые недели', async () => {
    renderWithProviders(<MarketingContentPlanPage />)
    expect(await screen.findAllByText(/Открытый урок по робототехнике/)).toHaveLength(2)
    expect(api.content).toHaveBeenCalledWith(expect.objectContaining({ date_from: '2026-09-28', date_to: '2026-11-01', page_size: 200 }))
    expect(screen.getByRole('heading', { name: 'Октябрь 2026' })).toBeInTheDocument()
  })

  it('«Запланировано» без даты не отправляется; со списком — без ограничения по датам', async () => {
    const user = userEvent.setup()
    renderWithProviders(<MarketingContentPlanPage />)
    await screen.findAllByText(/Открытый урок по робототехнике/)
    await user.click(screen.getByRole('button', { name: 'Новая публикация' }))
    const dialog = await screen.findByRole('dialog', { name: 'Новая публикация' })
    await user.type(within(dialog).getByLabelText(/Тема/), 'Отзыв родителей')
    await user.selectOptions(within(dialog).getByLabelText('Статус'), 'scheduled')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('нужна дата публикации')
    expect(api.createContent).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))

    await user.click(screen.getByRole('radio', { name: 'Список' }))
    await waitFor(() => expect(api.content).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 30 })))
    expect(api.content.mock.lastCall?.[0].date_from).toBeUndefined()
  })

  it('чужую публикацию можно править, но не удалить', async () => {
    const user = userEvent.setup()
    renderWithProviders(<MarketingContentPlanPage />)
    await user.click((await screen.findAllByText(/Открытый урок по робототехнике/))[0])
    const dialog = await screen.findByRole('dialog', { name: 'Публикация' })
    expect(within(dialog).getByLabelText(/Тема/)).toHaveValue('Открытый урок по робототехнике')
    expect(within(dialog).getByLabelText('Время')).toHaveValue('18:30')
    expect(within(dialog).queryByRole('button', { name: 'Удалить' })).not.toBeInTheDocument()
  })
})

describe('отчёты', () => {
  it('реальные показатели, переключение недели и без выдуманной аналитики заявок', async () => {
    const user = userEvent.setup()
    renderWithProviders(<MarketingReportsPage />)
    expect(await screen.findByText('89%')).toBeInTheDocument()
    expect(screen.getByText('Вышло 8 из 9 с наступившей датой')).toBeInTheDocument()
    expect(screen.getByText('В срок: 6, с опозданием: 1')).toBeInTheDocument()
    expect(screen.getAllByText('Аида Маркетинг').length).toBeGreaterThan(0)
    expect(screen.getByText(/Заявки и рекламные кампании в системе пока не ведутся/)).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(api.report).toHaveBeenLastCalledWith({ period: 'week', date: undefined }))
  })
})
