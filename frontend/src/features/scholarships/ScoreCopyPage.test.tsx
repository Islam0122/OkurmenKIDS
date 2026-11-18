import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { ScoreCopyOperation, ScoreCopyPreview, ScoreCopyRow } from '@/types/scoreCopy'

vi.mock('@/api/scoreCopy', () => ({
  scoreCopyApi: { options: vi.fn(), preview: vi.fn(), apply: vi.fn(), history: vi.fn(), undo: vi.fn() },
  newOperationId: vi.fn(() => '11111111-1111-4111-8111-111111111111'),
}))

import { scoreCopyApi } from '@/api/scoreCopy'
import { ScoreCopyPage } from './ScoreCopyPage'

const PERIOD = { id: 7, title: 'Стипендия', period_start: '2026-09-01', period_end: '2026-09-30', status: 'draft' as const, is_draft: true }
const v = (p: number) => ({ progress: p, participation: p, discipline: p, understanding: p, score: p * 20 })

function row(id: number, name: string, action: ScoreCopyRow['action'], extra: Partial<ScoreCopyRow> = {}): ScoreCopyRow {
  return {
    student_id: id, student_name: name, action, reason: 'причина', source: v(4), source_teacher: { id: 1, name: 'IT Trainer' },
    target: null, target_teacher: { id: 2, name: 'Soft Trainer' }, target_teachers: [{ id: 2, name: 'Soft Trainer' }],
    after: action === 'create' || action === 'overwrite' ? v(4) : null, ...extra,
  }
}

function preview(overwrite = 0): ScoreCopyPreview {
  return {
    fingerprint: 'fp-1',
    summary: { students: 4, matched: 3, copyable: 1 + overwrite, create: 1, overwrite, unchanged: 0, skip_existing: overwrite ? 0 : 1,
      empty: 1, existing_target: 1, unmatched: 1, not_selected: 0 },
    rows: [
      row(10, 'Асанов Айбек', 'create'),
      row(11, 'Беков Бекзат', overwrite ? 'overwrite' : 'skip_existing', { target: v(1) }),
      row(12, 'Чынгызов Чынгыз', 'unmatched_no_target', { target_teacher: null, after: null }),
      row(13, 'Данова Дана', 'skip_empty', { source: null }),
    ],
    source_teachers: [{ id: 1, name: 'IT Trainer' }], target_teachers: [{ id: 2, name: 'Soft Trainer' }], target_period_is_draft: true,
  }
}

const OPERATION: ScoreCopyOperation = {
  id: 5, operation_id: '11111111-1111-4111-8111-111111111111', status: 'applied', status_label: 'Применено',
  group: { id: 1, name: 'Prog SOFT 1' }, source_subject: { id: 1, name: 'IT' }, target_subject: { id: 2, name: 'Soft Skills' },
  source_period: PERIOD, target_period: PERIOD, options: {}, copied: 1, overwritten: 0, skipped: 3, skipped_details: {},
  created_by: 'Admin', created_at: '2026-11-18T10:00:00Z', reverted_by: null, reverted_at: null, revert_details: {}, can_undo: true,
}

async function fillForm() {
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Группа'), '1')
  await waitFor(() => expect(screen.getByLabelText('Предмет-источник')).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('Предмет-источник'), '1')
  await user.selectOptions(screen.getByLabelText('Целевой предмет'), '2')
  await user.selectOptions(screen.getByLabelText('Период-источник'), '7') // prefills the target period
  return user
}

describe('ScoreCopyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(scoreCopyApi.options).mockImplementation(async (group) => ({
      groups: [{ id: 1, name: 'Prog SOFT 1', status: 'active' }],
      periods: [PERIOD],
      subjects: group ? [{ id: 1, name: 'IT' }, { id: 2, name: 'Soft Skills' }] : [],
    }))
    vi.mocked(scoreCopyApi.history).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(scoreCopyApi.preview).mockImplementation(async (params) => preview(params.conflict === 'overwrite' ? 1 : 0))
    vi.mocked(scoreCopyApi.apply).mockResolvedValue(OPERATION)
  })

  it('shows the server preview with every required count before anything is written', async () => {
    renderWithProviders(<ScoreCopyPage />)
    await fillForm()
    const region = await screen.findByRole('region', { name: 'Предпросмотр' })
    expect(within(region).getByText('Сопоставлено студентов')).toBeInTheDocument()
    expect(within(region).getByText('Будет перезаписано')).toBeInTheDocument()
    expect(within(region).getAllByText('Чынгызов Чынгыз').length).toBeGreaterThan(0)
    expect(within(region).getAllByText('Не сопоставлено').length).toBeGreaterThan(0)
    expect(scoreCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({
      group: 1, source_subject: 1, target_subject: 2, source_period: 7, target_period: 7, mode: 'all', conflict: 'preserve',
    }))
    expect(scoreCopyApi.apply).not.toHaveBeenCalled()
  })

  it('applies with the preview fingerprint and an operation id after confirmation', async () => {
    renderWithProviders(<ScoreCopyPage />)
    const user = await fillForm()
    await user.click(await screen.findByRole('button', { name: /Скопировать 1/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Скопировать' }))
    await waitFor(() => expect(scoreCopyApi.apply).toHaveBeenCalledWith(expect.objectContaining({
      fingerprint: 'fp-1', operation_id: '11111111-1111-4111-8111-111111111111', confirm_overwrite: false,
    })))
    expect(await screen.findByText('Оценки скопированы')).toBeInTheDocument()
  })

  it('requires an explicit acknowledgement before overwriting', async () => {
    renderWithProviders(<ScoreCopyPage />)
    const user = await fillForm()
    await user.click(screen.getByRole('radio', { name: 'Перезаписать' }))
    await user.click(await screen.findByRole('button', { name: /Скопировать 2/ }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Скопировать' })
    expect(confirm).toBeDisabled()
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(confirm)
    await waitFor(() => expect(scoreCopyApi.apply).toHaveBeenCalledWith(expect.objectContaining({ conflict: 'overwrite', confirm_overwrite: true })))
  })

  it('copies only the ticked students in «Выбранные» mode', async () => {
    renderWithProviders(<ScoreCopyPage />)
    const user = await fillForm()
    await user.click(screen.getByRole('radio', { name: 'Выбранные' }))
    expect(await screen.findByText('Отметьте хотя бы одного студента.')).toBeInTheDocument()
    await user.click(screen.getAllByRole('checkbox', { name: 'Выбрать: Асанов Айбек' })[0])
    await waitFor(() => expect(scoreCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({ mode: 'selected', student_ids: [10] })))
  })

  it('undoes an operation from the history', async () => {
    vi.mocked(scoreCopyApi.history).mockResolvedValue({ count: 1, next: null, previous: null, results: [OPERATION] })
    vi.mocked(scoreCopyApi.undo).mockResolvedValue({ ...OPERATION, status: 'reverted', can_undo: false })
    renderWithProviders(<ScoreCopyPage />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Отменить' }))
    await user.click(await screen.findByRole('button', { name: 'Отменить копирование' }))
    await waitFor(() => expect(scoreCopyApi.undo).toHaveBeenCalledWith(5))
  })
})
