import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SubjectCyclesSection } from '@/features/accounting/SubjectCyclesSection'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, CourseCycle } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({ accountingApi: { cycles: vi.fn() } }))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  courses: [{ id: 1, name: 'Программатика' }], groups: [{ id: 5, name: 'Prog SOFT 1', course: 1, status: 'active' }],
  subjects: [{ id: 10, name: 'IT' }, { id: 11, name: 'English' }, { id: 12, name: 'Soft Skills' }],
  trainers: [{ id: 7, name: 'Тренер A' }, { id: 8, name: 'Тренер B' }],
} as unknown as AccountingOptions

function cycle(id: number, subject: string, done: number, trainer: string, extra: Partial<CourseCycle> = {}): CourseCycle {
  return {
    id, group: 5, group_name: 'Prog SOFT 1', course: 1, course_name: 'Программатика', subject: id, subject_name: subject,
    per_subject: true, number: 4, status: 'IN_PROGRESS', status_display: 'Идёт', required_lessons: 12, lessons_done: done,
    lessons_remaining: 12 - done, progress_percent: Math.round((done / 12) * 100), lessons_total: 36 + done,
    subject_plan_lessons: 48, invalidated_reason: '', start_date: '2026-10-01', completed_on: null, student_count: null,
    course_price: null, base_amount: null, trainers: [trainer], trainer_lessons: [{ teacher: id, name: trainer, lessons: done }],
    warnings: [], lessons_linked: 0, accruals: [], ...extra,
  }
}

const page = (results: CourseCycle[]) => ({ count: results.length, next: null, previous: null, results })

describe('SubjectCyclesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.cycles).mockResolvedValue(page([
      cycle(10, 'IT', 10, 'Тренер A'), cycle(11, 'English', 8, 'Тренер B'), cycle(12, 'Soft Skills', 6, 'Тренер C'),
    ]))
  })

  it('shows a separate progress bar per subject, without a merged group progress', async () => {
    renderWithProviders(<SubjectCyclesSection options={OPTIONS} />)
    const bars = await screen.findAllByRole('progressbar')
    expect(bars.map((b) => b.getAttribute('aria-valuenow'))).toEqual(['10', '8', '6'])
    expect(bars.map((b) => b.getAttribute('aria-label'))).toEqual([
      'IT: проведено 10 из 12', 'English: проведено 8 из 12', 'Soft Skills: проведено 6 из 12',
    ])
    expect(screen.getByText('10 / 12')).toBeInTheDocument()
    expect(screen.getByText('Тренер B (8)')).toBeInTheDocument()
    expect(screen.queryByText('24 / 12')).not.toBeInTheDocument() // нет ложного «общего» прогресса
    expect(screen.getByText('всего по предмету: 46 / 48 по плану')).toBeInTheDocument()
  })

  it('expands a group to show per-subject details', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SubjectCyclesSection options={OPTIONS} />)
    const toggle = await screen.findByRole('button', { name: /Prog SOFT 1/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Уроки по тренерам: Тренер A — 10 из 12')).toBeInTheDocument()
  })

  it('sends tab, subject, trainer and search filters to the server', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SubjectCyclesSection options={OPTIONS} />)
    await screen.findAllByRole('progressbar')
    expect(accountingApi.cycles).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'IN_PROGRESS', page: 1 }))
    await user.selectOptions(screen.getByLabelText('Предмет'), '11')
    await user.selectOptions(screen.getByLabelText('Тренер'), '8')
    await waitFor(() => expect(accountingApi.cycles).toHaveBeenLastCalledWith(
      expect.objectContaining({ subject: 11, trainer: 8 }),
    ))
    await user.type(screen.getByPlaceholderText('Поиск по названию группы'), 'Prog')
    await waitFor(() => expect(accountingApi.cycles).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'Prog' })))
    await user.click(screen.getByRole('tab', { name: 'Завершённые' }))
    await waitFor(() => expect(accountingApi.cycles).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'COMPLETED' })))
  })

  it('shows per-trainer shares of a completed subject cycle and an empty state', async () => {
    vi.mocked(accountingApi.cycles).mockResolvedValue(page([cycle(10, 'IT', 12, 'Тренер A', {
      status: 'COMPLETED', completed_on: '2026-10-12',
      trainer_lessons: [{ teacher: 7, name: 'Тренер A', lessons: 9 }, { teacher: 8, name: 'Тренер B', lessons: 3 }],
      accruals: [
        { id: 1, employee: 1, employee_name: 'Тренер A', percentage: '10.00', amount: '7500.00', lessons_taught: 9, share: '0.75',
          status: 'ACCRUED', status_display: 'Начислено', note: '', payroll: null, payroll_status: null, payroll_status_display: null,
          period_label: null, adjustment: null, review_reasons: [], planned_payment_date: '2026-10-15' },
      ],
    })]))
    const user = userEvent.setup()
    renderWithProviders(<SubjectCyclesSection options={OPTIONS} />)
    expect(await screen.findByText('Тренер A (9), Тренер B (3)')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Prog SOFT 1/ }))
    const details = screen.getByText(/10% × 9\/12 ур\./)
    expect(within(details).getByText(/7\s500\sсом/, { exact: false })).toBeTruthy()

    vi.mocked(accountingApi.cycles).mockResolvedValue(page([]))
    await user.click(screen.getByRole('tab', { name: 'Отменённые' }))
    expect(await screen.findByText('Отменённых циклов предметов нет')).toBeInTheDocument()
  })
})
