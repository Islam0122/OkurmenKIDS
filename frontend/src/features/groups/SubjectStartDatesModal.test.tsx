import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, AxiosHeaders } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SubjectStartDatesModal } from '@/features/groups/SubjectStartDatesModal'
import { buildGroup } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { SubjectStartOverview, SubjectStartRow } from '@/types/academy'

vi.mock('@/api/groups', () => ({
  groupsApi: { list: vi.fn(), subjectStartDates: vi.fn(), saveSubjectStartDate: vi.fn() },
}))
vi.mock('@/api/assistant', () => ({
  assistantApi: { subjectStartDates: vi.fn(), saveSubjectStartDate: vi.fn() },
}))

import { assistantApi } from '@/api/assistant'
import { groupsApi } from '@/api/groups'

function row(name: string, id: number, overrides: Partial<SubjectStartRow> = {}): SubjectStartRow {
  return {
    subject: { id, name },
    start_date: '2026-10-10',
    is_custom: true,
    status: 'in_progress',
    status_display: 'Идёт обучение',
    lessons_total: 4,
    lessons_open: 4,
    first_lesson_date: '2026-10-10',
    updated_by: null,
    updated_at: null,
    ...overrides,
  }
}

function overview(subjects: SubjectStartRow[], saved?: SubjectStartOverview['saved']): SubjectStartOverview {
  return {
    group: { id: 7, name: 'Prog SOFT 1', course: 'Prog SOFT', status: 'active', start_date: '2026-10-05', end_date: null },
    today: '2026-10-11',
    subjects,
    saved,
  }
}

const IT = row('IT', 1)
const ENGLISH = row('English', 2, { start_date: '2026-10-12', status: 'not_started', status_display: 'Не начался' })

describe('SubjectStartDatesModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(groupsApi.subjectStartDates).mockResolvedValue(overview([ENGLISH, IT]))
  })

  it('shows every subject with its own date and status', async () => {
    renderWithProviders(<SubjectStartDatesModal isOpen onClose={vi.fn()} groupId={7} />)

    const rows = await screen.findAllByTestId('subject-start-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('English')).toBeInTheDocument()
    expect(within(rows[0]).getByText('12.10.2026')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Не начался')).toBeInTheDocument()
    expect(within(rows[1]).getByText('10.10.2026')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Идёт обучение')).toBeInTheDocument()
    expect(groupsApi.subjectStartDates).toHaveBeenCalledWith(7)
  })

  it('saves the date of one subject only and reports moved lessons', async () => {
    const user = userEvent.setup()
    const saved = overview([{ ...ENGLISH, start_date: '2026-10-19' }, IT], {
      subject: 2, previous_start_date: '2026-10-12', start_date: '2026-10-19', moved: 4,
    })
    vi.mocked(groupsApi.saveSubjectStartDate).mockImplementation(async () => {
      // The server now has the new date — the refetch after saving sees it too.
      vi.mocked(groupsApi.subjectStartDates).mockResolvedValue(saved)
      return saved
    })
    renderWithProviders(<SubjectStartDatesModal isOpen onClose={vi.fn()} groupId={7} />)

    await user.click(await screen.findByRole('button', { name: 'Изменить дату старта: English' }))
    // Only one row is edited at a time.
    expect(screen.getByRole('button', { name: 'Изменить дату старта: IT' })).toBeDisabled()
    const input = screen.getByLabelText('Дата старта: English')
    expect(input).toHaveAttribute('min', '2026-10-05')
    await user.clear(input)
    await user.type(input, '2026-10-19')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(groupsApi.saveSubjectStartDate).toHaveBeenCalledWith(7, 2, '2026-10-19'))
    expect(groupsApi.saveSubjectStartDate).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('«English»: старт 19.10.2026 · перенесено занятий: 4')).toBeInTheDocument()
    const englishRow = (await screen.findAllByTestId('subject-start-row'))[0]
    await waitFor(() => expect(within(englishRow).getByText('19.10.2026')).toBeInTheDocument())
  })

  it('shows the backend refusal and keeps the row in edit mode', async () => {
    const user = userEvent.setup()
    const refusal = new AxiosError('Bad Request', '400', undefined, undefined, {
      status: 400, statusText: 'Bad Request', headers: {}, config: { headers: new AxiosHeaders() },
      data: { start_date: ['Дата старта не может быть позже них.'] },
    })
    vi.mocked(groupsApi.saveSubjectStartDate).mockRejectedValue(refusal)
    renderWithProviders(<SubjectStartDatesModal isOpen onClose={vi.fn()} groupId={7} />)

    await user.click(await screen.findByRole('button', { name: 'Изменить дату старта: IT' }))
    const input = screen.getByLabelText('Дата старта: IT')
    await user.clear(input)
    await user.type(input, '2026-10-20')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Дата старта не может быть позже них.')
    expect(screen.getByLabelText('Дата старта: IT')).toBeInTheDocument()
  })

  it('lets the user pick a group first when opened without one', async () => {
    const user = userEvent.setup()
    vi.mocked(groupsApi.list).mockResolvedValue({ count: 1, next: null, previous: null, results: [buildGroup({ id: 7, name: 'Prog SOFT 1' })] })
    renderWithProviders(<SubjectStartDatesModal isOpen onClose={vi.fn()} />)

    expect(screen.getByText('Выберите группу, чтобы увидеть даты старта её предметов.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('option', { name: /Prog SOFT 1/ })).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText('Группа'), '7')
    expect(await screen.findAllByTestId('subject-start-row')).toHaveLength(2)
  })

  it('uses the Assistant Workspace API for the assistant', async () => {
    vi.mocked(assistantApi.subjectStartDates).mockResolvedValue(overview([IT]))
    renderWithProviders(<SubjectStartDatesModal isOpen onClose={vi.fn()} groupId={7} source="assistant" />)

    expect(await screen.findAllByTestId('subject-start-row')).toHaveLength(1)
    expect(assistantApi.subjectStartDates).toHaveBeenCalledWith(7)
    expect(groupsApi.subjectStartDates).not.toHaveBeenCalled()
  })
})
