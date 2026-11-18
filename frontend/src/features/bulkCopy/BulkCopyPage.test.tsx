import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { BulkPreview } from '@/types/bulkCopy'

vi.mock('@/api/bulkCopy', () => ({
  bulkCopyApi: { options: vi.fn(), preview: vi.fn(), apply: vi.fn(), history: vi.fn(), undo: vi.fn() },
  newOperationId: vi.fn(() => '22222222-2222-4222-8222-222222222222'),
}))

import { bulkCopyApi } from '@/api/bulkCopy'
import { BulkCopyPage } from './BulkCopyPage'

const lesson = (id: number, date: string, topic: string) => ({ id, date, start: '10:00', topic, lesson_number: id, status: 'completed', teacher: null })

function preview(overwrite = 0, map: { source: number; target: number }[] | null = null): BulkPreview {
  const pairs = (map ?? [{ source: 1, target: 11 }, { source: 2, target: 12 }]).map((p, index) => ({
    index, ...p, valid: p.target !== 1, problem: p.target === 1 ? 'Целевое занятие не входит в выбранные группу, предмет и период.' : null,
    homework_pairs: 1, homework_problem: null,
  }))
  return {
    fingerprint: 'fp-bulk',
    summary: { students_matched: 2, students_unmatched: 1, students_without_source: 0, students_not_selected: 0, pairs: pairs.length,
      invalid_pairs: pairs.filter((p) => !p.valid).length, homework_problems: 0, to_copy: 3 + overwrite, create: 3, overwrite,
      unchanged: 0, skip_existing: overwrite ? 0 : 1, empty: 1, existing_target: 1, invalid_records: 0, attendance: 3, homework_results: overwrite, billing_lessons: 2 },
    source_lessons: [lesson(1, '2026-11-02', 'Функции'), lesson(2, '2026-11-04', 'Циклы')],
    target_lessons: [lesson(11, '2026-11-03', 'Команда'), lesson(12, '2026-11-05', 'Эссе')],
    pairs,
    students: [{ id: 1, name: 'Асанов Айбек', group: 'A', status: 'matched' }, { id: 2, name: 'Беков Бекзат', group: 'A', status: 'matched' },
      { id: 9, name: 'Чужой Нурлан', group: 'B', status: 'not_in_target_group' }],
    records: [{ kind: 'attendance', student: 1, pair: 0, homework: null, action: 'create', problem: null,
      source: { status: 'present', excuse_reason: '', comment: '' }, target: null, after: { status: 'present', excuse_reason: '', comment: '' } }],
  }
}

async function fill() {
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Группа', { selector: '#src-group' }), '1')
  await waitFor(() => expect(screen.getByLabelText('Предмет', { selector: '#src-subject' })).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('Предмет', { selector: '#src-subject' }), '1')
  await user.click(screen.getByRole('button', { name: 'Та же группа' }))
  await waitFor(() => expect(screen.getByLabelText('Предмет', { selector: '#tgt-subject' })).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('Предмет', { selector: '#tgt-subject' }), '2')
  return user
}

describe('BulkCopyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(bulkCopyApi.options).mockImplementation(async (group) => ({
      groups: [{ id: 1, name: 'Prog SOFT 1', status: 'active' }],
      subjects: group ? [{ id: 1, name: 'IT' }, { id: 2, name: 'Soft Skills' }] : [],
    }))
    vi.mocked(bulkCopyApi.history).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(bulkCopyApi.preview).mockImplementation(async (p) => preview(p.conflict === 'overwrite' ? 1 : 0, p.lesson_map))
    vi.mocked(bulkCopyApi.apply).mockResolvedValue({
      id: 3, operation_id: 'x', status: 'applied', status_label: 'Применено', source: { group: 'A', subject: 'IT', start: '', end: '' },
      target: { group: 'A', subject: 'Soft', start: '', end: '' }, categories: ['attendance'], copied: 3, overwritten: 0, skipped: 2,
      skipped_details: {}, error: '', created_by: 'Admin', created_at: '2026-11-18T10:00:00Z', finished_at: null, reverted_by: null,
      reverted_at: null, revert_details: {}, can_undo: true,
    })
  })

  it('starts from the server mapping, then sends the explicit mapping the admin edits', async () => {
    renderWithProviders(<BulkCopyPage />)
    const user = await fill()
    await screen.findByText('Сопоставление занятий')
    expect(bulkCopyApi.preview).toHaveBeenCalledWith(expect.objectContaining({ lesson_map: null, categories: ['attendance', 'homework', 'scores'] }))
    await waitFor(() => expect(bulkCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({
      lesson_map: [{ source: 1, target: 11 }, { source: 2, target: 12 }] })))
    await user.selectOptions(screen.getByLabelText(/Целевое занятие для .*Циклы/), '')
    await waitFor(() => expect(bulkCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({ lesson_map: [{ source: 1, target: 11 }] })))
    expect(screen.getByText(/пересчитает списания уроков в биллинге/)).toBeInTheDocument()
    expect(screen.getByText('Чужой Нурлан')).toBeInTheDocument()
  })

  it('requires the overwrite acknowledgement and sends fingerprint + operation id', async () => {
    renderWithProviders(<BulkCopyPage />)
    const user = await fill()
    await user.click(screen.getByRole('radio', { name: 'Перезаписать' }))
    await user.click(await screen.findByRole('button', { name: /Скопировать 4/ }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Скопировать' })
    expect(confirm).toBeDisabled()
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(confirm)
    await waitFor(() => expect(bulkCopyApi.apply).toHaveBeenCalledWith(expect.objectContaining({
      fingerprint: 'fp-bulk', operation_id: '22222222-2222-4222-8222-222222222222', confirm_overwrite: true, conflict: 'overwrite',
    })))
  })

  it('switches the copied categories with the data presets', async () => {
    renderWithProviders(<BulkCopyPage />)
    const user = await fill()
    await user.click(screen.getByRole('radio', { name: 'Посещаемость' }))
    await waitFor(() => expect(bulkCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({ categories: ['attendance'] })))
    await user.click(screen.getByRole('radio', { name: 'Оценки' }))
    await waitFor(() => expect(bulkCopyApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({ categories: ['scores'] })))
  })
})
