import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { lessonNo } from '@/features/studentPortal/ui'
import { translate } from '@/features/studentPortal/i18n'
import { renderWithProviders } from '@/test/testUtils'
import type { LessonNumbering } from '@/types/lessonNumbering'

import { lessonLabel, lessonLabelShort } from './lessonNumbering'

vi.mock('@/api/academicProgress', () => ({
  academicProgressApi: { saveGroupNumbering: vi.fn().mockResolvedValue({}) },
}))

import { academicProgressApi } from '@/api/academicProgress'
import { GroupNumberingCard } from '@/features/academicProgress/ui'

/** What the server sends (apps.academic_progress.numbering) for a global number. */
function numbering(n: number, perMonth: number): LessonNumbering {
  const month = Math.floor((n - 1) / perMonth) + 1
  const lesson = ((n - 1) % perMonth) + 1
  return { number: n, month, lesson, per_month: perMonth, label: `Месяц ${month} · Урок ${lesson}` }
}

describe('lesson labels', () => {
  it.each([
    [1, 12, 'Месяц 1 · Урок 1'],
    [12, 12, 'Месяц 1 · Урок 12'],
    [13, 12, 'Месяц 2 · Урок 1'],
    [25, 12, 'Месяц 3 · Урок 1'],
    [20, 20, 'Месяц 1 · Урок 20'],
    [21, 20, 'Месяц 2 · Урок 1'],
    [41, 20, 'Месяц 3 · Урок 1'],
  ])('global %i with %i per month → %s', (n, perMonth, label) => {
    expect(lessonLabel(numbering(n, perMonth))).toBe(label)
  })

  it('Kyrgyz, short form and the fallback without numbering', () => {
    expect(lessonLabel(numbering(13, 12), 13, 'ky')).toBe('2-ай · 1-сабак')
    expect(lessonLabelShort(numbering(21, 20))).toBe('М2 · У1')
    expect(lessonLabel(null, 14)).toBe('Занятие 14')
    expect(lessonLabel(undefined, null)).toBe('')
  })

  it('student portal: the same numbers in Russian and Kyrgyz', () => {
    const lesson = { lesson_number: 21, numbering: numbering(21, 20) }
    const ru = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate('ru', key, params)
    const ky = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate('ky', key, params)
    expect(lessonNo(ru, lesson)).toBe('Месяц 2 · Урок 1')
    expect(lessonNo(ky, lesson)).toBe('2-ай · 1-сабак')
    expect(lessonNo(ru, { lesson_number: 5, numbering: null })).toBe('Урок 5')
    expect(lessonNo(ru, null)).toBe('')
  })
})

describe('GroupNumberingCard', () => {
  const settings = { lessons_per_month: 12, group_value: null, program_value: 12, default: 12, choices: [12, 20], frozen: [] }

  it('switches a group to 20 lessons per month, or back to its program', async () => {
    renderWithProviders(<GroupNumberingCard groupId={5} numbering={settings} canEdit />)
    expect(screen.getByRole('radio', { name: 'Как в программе (12)' })).toBeChecked()
    expect(screen.getByText(/занятие №13 — «Месяц 2 · Урок 1»/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: '20 занятий' }))
    await waitFor(() => expect(academicProgressApi.saveGroupNumbering).toHaveBeenCalledWith(5, 20))
  })

  it('read-only roles see the value; frozen ranges are listed', () => {
    renderWithProviders(
      <GroupNumberingCard groupId={5} canEdit={false}
        numbering={{ ...settings, lessons_per_month: 20, group_value: 20, frozen: [{ subject: 'Python', first_lesson: 1, last_lesson: 36, first_month: 1, lessons_per_month: 12 }] }} />,
    )
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.getByText('20 занятий')).toBeInTheDocument()
    expect(screen.getByText(/Python: занятия №1–36 оставлены по 12/)).toBeInTheDocument()
  })
})
