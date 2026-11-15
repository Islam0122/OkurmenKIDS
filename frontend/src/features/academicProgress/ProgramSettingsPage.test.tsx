import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { ProgramDetail } from '@/types/academicProgress'

vi.mock('@/api/academicProgress', () => ({
  academicProgressApi: { meta: vi.fn(), programs: vi.fn(), program: vi.fn(), saveProgram: vi.fn(), group: vi.fn(), confirmHistory: vi.fn() },
}))

import { academicProgressApi } from '@/api/academicProgress'

import { ProgramSettingsPage } from './ProgramSettingsPage'

const api = vi.mocked(academicProgressApi)
const SUBJECTS = [{ id: 1, name: 'NEXT' }, { id: 2, name: 'ENGLISH' }, { id: 3, name: 'React' }]
const DETAIL: ProgramDetail = {
  course: { id: 7, name: 'NEXT', count_lesson: 72, subjects: SUBJECTS.slice(0, 2) },
  configured: false, can_edit: true, settings: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue({ subjects: SUBJECTS, can_edit: true, presets: [12, 20] })
  api.programs.mockResolvedValue([{
    id: 7, name: 'NEXT', configured: false, lessons_per_month: null, duration_months: null, main_subject: null, extra_subjects: [],
    total_lessons: null, groups: 3, groups_need_setup: 3, can_edit: true,
  }])
  api.program.mockResolvedValue(DETAIL)
  api.saveProgram.mockResolvedValue({ ...DETAIL, configured: true })
})

describe('Настройки учебной программы', () => {
  it('sets 20 lessons a month, subjects and a month of its own', async () => {
    renderWithProviders(<ProgramSettingsPage />)
    const row = (await screen.findByText('NEXT')).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Не настроено')
    await userEvent.click(within(row).getByRole('button', { name: 'Настроить' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('radio', { name: '20 занятий' }))
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Основной предмет' }), '1')
    await userEvent.click(within(dialog).getByRole('button', { name: 'ENGLISH' }))
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Предмет 3-го месяца' }), '3')
    await userEvent.type(within(dialog).getByRole('spinbutton', { name: 'План 3-го месяца' }), '12')
    expect(within(dialog).getByText('112')).toBeInTheDocument()  // 5 × 20 + 12
    await userEvent.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.saveProgram).toHaveBeenCalledWith(7, {
      lessons_per_month: 20, duration_months: 6, main_subject: 1, extra_subjects: [2], count_mode: 'main',
      months: [{ number: 3, subject: 3, planned_lessons: 12 }],
    }))
  })

  it('only 12 or 20 lessons per educational month', async () => {
    renderWithProviders(<ProgramSettingsPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Настроить' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('radio').map((r) => r.textContent).slice(0, 3)).toEqual(['12 занятий', '20 занятий', expect.any(String)])
    expect(within(dialog).queryByRole('radio', { name: 'Другое' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('spinbutton', { name: 'Своё количество занятий' })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('radio', { name: '20 занятий' }))
    expect(within(dialog).getByText(/занятие №21 — «Месяц 2 · Урок 1»/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.saveProgram).toHaveBeenCalledWith(7, expect.objectContaining({ lessons_per_month: 20 })))
  })

  it('a value saved earlier (not 12 / 20) is shown and kept until changed', async () => {
    api.program.mockResolvedValue({
      ...DETAIL, configured: true,
      settings: {
        lessons_per_month: 16, duration_months: 6, main_subject: null, extra_subjects: [], count_mode: 'main', months: [],
        blocks: [], total_lessons: 96, updated_at: null, updated_by: null,
      },
    } as ProgramDetail)
    renderWithProviders(<ProgramSettingsPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Настроить' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('radio', { name: '16 (прежнее)' })).toBeChecked()
  })

  it('view-only for roles that may not edit', async () => {
    api.program.mockResolvedValue({ ...DETAIL, can_edit: false })
    renderWithProviders(<ProgramSettingsPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Настроить' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument()
  })
})
