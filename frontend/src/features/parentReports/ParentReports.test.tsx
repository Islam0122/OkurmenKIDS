import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { ParentReportDetail, ParentReportPreview, ReportSnapshot } from '@/types/parentReports'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/parentReports', () => ({
  parentReportsApi: {
    preview: vi.fn(),
    generate: vi.fn(),
    list: vi.fn(),
    get: vi.fn(),
    regenerate: vi.fn(),
    updateText: vi.fn(),
    translatedText: vi.fn(),
    imageBlob: vi.fn(),
    download: vi.fn(),
  },
}))
vi.mock('@/api/groups', () => ({
  groupsApi: { list: vi.fn().mockResolvedValue({ count: 1, next: null, previous: null, results: [{ id: 5, name: 'PY-01' }] }) },
}))

import { parentReportsApi } from '@/api/parentReports'
import { ParentReportsSection } from './ParentReportsSection'

const comparison = {
  attendance_rate: { current: 66.7, previous: 75, change: -8.3, trend: 'down' as const },
  homework_rate: { current: 75, previous: 100, change: -25, trend: 'down' as const },
  average_score: { current: 7.5, previous: 7.5, change: 0, trend: 'stable' as const },
  test_average: { current: null, previous: null, change: null, trend: 'no_data' as const },
}

const snapshot: ReportSnapshot = {
  version: 1,
  generated_at: '2026-11-05T10:00:00Z',
  today: '2026-11-05',
  group: { id: 5, name: 'PY-01', course: 'Python для детей', trainers: ['Айбек'] },
  teacher_scope_id: 3,
  period: { key: 'last_month', start: '2026-10-01', end: '2026-10-31', monthly: true },
  comparison_period: { start: '2026-09-01', end: '2026-09-30' },
  group_stats: {
    active_students: 1, planned_lessons: 4, conducted_lessons: 3, cancelled_lessons: 1,
    attendance_rate: 66.7, attended: 2, attendance_marked: 3, absences: 1,
    homework_rate: 75, homework_done: 3, homework_due: 4, average_score: 7.5, scored_count: 2,
    test_average: null, tests_count: 0, excellent_count: 0, attention_count: 1,
    status_counts: { excellent: 0, good: 0, attention: 1, support: 0, no_data: 0 },
  },
  previous_group_stats: null,
  group_comparison: comparison,
  students: [{
    id: 11, name: 'Анна Алиева', first_name: 'Анна', last_name: 'Алиева', lessons_held: 3, attendance_marked: 3,
    attended: 2, absences: 1, attendance_rate: 66.7, homework_due: 4, homework_done: 3, homework_rate: 75,
    average_score: 7.5, scored_count: 2, tests_count: 0, test_average: null, tests: [], status: 'attention',
    previous: null, comparison,
  }],
}

const sections = {
  strengths: [{ key: 'homework_good', text: 'Большинство домашних заданий выполнено.' }],
  attention: [{ key: 'attendance_low', text: 'Необходимо обратить внимание на регулярность посещения занятий.' }],
  parents: [{ key: 'parents_attendance', text: 'Пожалуйста, помогите ребёнку не пропускать занятия.' }],
}

function buildReport(overrides: Partial<ParentReportDetail> = {}): ParentReportDetail {
  return {
    id: 42, group: 5, group_name: 'PY-01', course_name: 'Python для детей', report_type: 'group',
    report_type_display: 'Отчёт по группе', language: 'ru', language_display: 'Русский', output_format: 'both',
    output_format_display: 'Изображение и текст', period_key: 'last_month', start_date: '2026-10-01',
    end_date: '2026-10-31', compare_start_date: '2026-09-01', compare_end_date: '2026-09-30', status: 'ready',
    status_display: 'Готов', error: '', final_text: 'Уважаемые родители! 🌟', images: [{ id: 7, page: 1, student: null, student_name: '', width: 1600, height: 1100 }],
    students_count: 1, created_by_name: 'Айбек', created_at: '2026-11-05T10:00:00Z', regenerated_from: null,
    options: { include_table: true, include_group_stats: true, include_recommendations: true, include_comparison: true, student_ids: null },
    text: 'Уважаемые родители! 🌟', edited_text: '', student_texts: {}, edited_student_texts: {}, snapshot,
    recommendations: { group: sections, students: { 11: sections } },
    ...overrides,
  }
}

const preview: ParentReportPreview = {
  snapshot, text: 'Уважаемые родители! Предпросмотр', student_texts: {}, recommendations: { group: sections, students: {} },
}

describe('ParentReportsSection', () => {
  beforeEach(() => {
    mockRole.role = 'teacher'
    vi.mocked(parentReportsApi.list).mockResolvedValue(paginated([]))
    vi.mocked(parentReportsApi.imageBlob).mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
    URL.createObjectURL = vi.fn(() => 'blob:report')
  })

  it('shows the empty history and the create button for a trainer', async () => {
    renderWithProviders(<ParentReportsSection groupId={5} />)
    expect(await screen.findByText('Отчётов пока нет')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать отчёт' })).toBeInTheDocument()
    expect(parentReportsApi.list).toHaveBeenCalledWith({ group: 5, page: 1 })
  })

  it('hides the create button for a team lead (read-only)', async () => {
    mockRole.role = 'team_lead'
    renderWithProviders(<ParentReportsSection groupId={5} />)
    await screen.findByText('Отчётов пока нет')
    expect(screen.queryByRole('button', { name: 'Создать отчёт' })).not.toBeInTheDocument()
  })

  it('generates a report with the chosen configuration and shows image + editable text', async () => {
    const user = userEvent.setup()
    vi.mocked(parentReportsApi.generate).mockResolvedValue(buildReport())
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    renderWithProviders(<ParentReportsSection groupId={5} />)
    await user.click(await screen.findByRole('button', { name: 'Создать отчёт' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('radio', { name: 'Прошлый месяц' }))
    await user.click(within(dialog).getByRole('radio', { name: 'Кыргызча' }))
    await user.click(within(dialog).getByRole('radio', { name: /Индивидуальные отчёты/ }))
    await user.click(within(dialog).getByRole('checkbox', { name: 'Сравнение с прошлым периодом' }))
    await user.click(within(dialog).getByRole('button', { name: 'Сгенерировать отчёт' }))

    await waitFor(() => expect(parentReportsApi.generate).toHaveBeenCalled())
    expect(parentReportsApi.generate).toHaveBeenCalledWith(5, {
      period: 'last_month', report_type: 'students', language: 'ky', output_format: 'both',
      include_table: true, include_group_stats: true, include_recommendations: true, include_comparison: false,
    })

    expect(await within(dialog).findByRole('img', { name: 'Отчёт, страница 1' })).toHaveAttribute('src', 'blob:report')
    const textbox = within(dialog).getByRole('textbox', { name: 'Текст для WhatsApp' })
    expect(textbox).toHaveValue('Уважаемые родители! 🌟')
    await user.clear(textbox)
    await user.type(textbox, 'Свой текст')
    await user.click(within(dialog).getByRole('button', { name: 'Скопировать текст' }))
    expect(writeText).toHaveBeenCalledWith('Свой текст')
    expect(within(dialog).getByRole('button', { name: 'Скачать PNG' })).toBeInTheDocument()
  })

  it('switches the WhatsApp text between Russian and Kyrgyz', async () => {
    const user = userEvent.setup()
    vi.mocked(parentReportsApi.generate).mockResolvedValue(buildReport())
    vi.mocked(parentReportsApi.translatedText).mockResolvedValue({ text: 'Саламатсыздарбы, урматтуу ата-энелер! 🌟' })
    renderWithProviders(<ParentReportsSection groupId={5} />)
    await user.click(await screen.findByRole('button', { name: 'Создать отчёт' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Сгенерировать отчёт' }))
    const languages = await within(dialog).findByRole('radiogroup', { name: 'Язык текста' })
    const textbox = within(dialog).getByRole('textbox', { name: 'Текст для WhatsApp' })
    expect(textbox).toHaveValue('Уважаемые родители! 🌟')
    await user.click(within(languages).getByRole('radio', { name: 'Кыргызча' }))
    await waitFor(() => expect(textbox).toHaveValue('Саламатсыздарбы, урматтуу ата-энелер! 🌟'))
    expect(parentReportsApi.translatedText).toHaveBeenCalledWith(42, { language: 'ky', student_id: undefined })
    await user.click(within(languages).getByRole('radio', { name: 'Русский' }))
    await waitFor(() => expect(textbox).toHaveValue('Уважаемые родители! 🌟'))
  })

  it('blocks a custom period whose start is after its end', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ParentReportsSection groupId={5} />)
    await user.click(await screen.findByRole('button', { name: 'Создать отчёт' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('radio', { name: 'Произвольный период' }))
    await user.type(within(dialog).getByLabelText('Дата начала'), '2026-10-20')
    await user.type(within(dialog).getByLabelText('Дата окончания'), '2026-10-01')
    expect(within(dialog).getByText('Дата начала не может быть позже даты окончания.')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Сгенерировать отчёт' })).toBeDisabled()
  })

  it('previews the calculated data with «Нет данных» for missing tests', async () => {
    const user = userEvent.setup()
    vi.mocked(parentReportsApi.preview).mockResolvedValue(preview)
    renderWithProviders(<ParentReportsSection groupId={5} />)
    await user.click(await screen.findByRole('button', { name: 'Создать отчёт' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Предпросмотр данных' }))
    const panel = await within(dialog).findByRole('region', { name: 'Предпросмотр' })
    expect(within(panel).getByText('Анна Алиева')).toBeInTheDocument()
    expect(within(panel).getAllByText('Нет данных').length).toBeGreaterThan(0)
    expect(within(panel).getByText('Необходимо обратить внимание на регулярность посещения занятий.')).toBeInTheDocument()
    expect(within(panel).getByText('Уважаемые родители! Предпросмотр')).toBeInTheDocument()
  })

  it('opens a report from the history', async () => {
    const user = userEvent.setup()
    vi.mocked(parentReportsApi.list).mockResolvedValue(paginated([buildReport({ status: 'partial', status_display: 'Готов без изображения', images: [], error: 'Нет браузера.' })]))
    vi.mocked(parentReportsApi.get).mockResolvedValue(buildReport({ status: 'partial', status_display: 'Готов без изображения', images: [], error: 'Нет браузера.' }))
    renderWithProviders(<ParentReportsSection groupId={5} />)
    await user.click(await screen.findByText('Готов без изображения'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Изображение не сформировано')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Перегенерировать' })).toBeInTheDocument()
    expect(within(dialog).getByRole('textbox', { name: 'Текст для WhatsApp' })).toHaveValue('Уважаемые родители! 🌟')
  })
})
