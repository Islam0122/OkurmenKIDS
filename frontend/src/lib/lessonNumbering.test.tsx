import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { lessonNo } from '@/features/studentPortal/ui'
import { translate } from '@/features/studentPortal/i18n'
import { renderWithProviders } from '@/test/testUtils'
import type { LessonNumbering } from '@/types/lessonNumbering'

import { lessonLabel } from './lessonNumbering'

vi.mock('@/api/academicProgress', () => ({
  academicProgressApi: { saveGroupNumbering: vi.fn().mockResolvedValue({}) },
}))

import { academicProgressApi } from '@/api/academicProgress'
import { GroupNumberingCard } from '@/features/academicProgress/ui'

/** What the server's numbering service sends for a position in a subject's sequence. */
function numbering(position: number, perMonth: number): LessonNumbering {
  const month = Math.floor((position - 1) / perMonth) + 1
  const lesson = ((position - 1) % perMonth) + 1
  return { number: position, month, lesson, per_month: perMonth, label: `${month} месяц · ${lesson} урок` }
}

describe('lesson labels', () => {
  it.each([
    [1, 12, '1 месяц · 1 урок'],
    [12, 12, '1 месяц · 12 урок'],
    [13, 12, '2 месяц · 1 урок'],
    [29, 12, '3 месяц · 5 урок'],
    [20, 20, '1 месяц · 20 урок'],
    [21, 20, '2 месяц · 1 урок'],
    [41, 20, '3 месяц · 1 урок'],
  ])('subject lesson %i with %i per month → %s', (position, perMonth, label) => {
    expect(lessonLabel(numbering(position, perMonth))).toBe(label)
  })

  it('Kyrgyz and English; nothing without numbering (the course-wide row is never shown)', () => {
    expect(lessonLabel(numbering(29, 12), null, 'ky')).toBe('3-ай · 5-сабак')
    expect(lessonLabel(numbering(29, 12), null, 'en')).toBe('Month 3 · Lesson 5')
    expect(lessonLabel(null, 85)).toBe('')
    expect(lessonLabel(undefined)).toBe('')
  })

  it('student portal: the same numbers in Russian and Kyrgyz', () => {
    const lesson = { lesson_number: 85, numbering: numbering(29, 12) }
    const ru = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate('ru', key, params)
    const ky = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate('ky', key, params)
    expect(lessonNo(ru, lesson)).toBe('3 месяц · 5 урок')
    expect(lessonNo(ky, lesson)).toBe('3-ай · 5-сабак')
    expect(lessonNo(ru, { lesson_number: 85, numbering: null })).toBe('')
    expect(lessonNo(ru, null)).toBe('')
  })
})

describe('GroupNumberingCard', () => {
  const settings = { lessons_per_month: 12, group_value: null, program_value: 12, default: 12, choices: [12, 20], frozen: [] }

  it('switches a group to 20 lessons per month, or back to its program', async () => {
    renderWithProviders(<GroupNumberingCard groupId={5} numbering={settings} canEdit />)
    expect(screen.getByRole('radio', { name: 'Как в программе (12)' })).toBeChecked()
    expect(screen.getByText(/13-й урок предмета — «2 месяц · 1 урок»/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: '20 занятий' }))
    await waitFor(() => expect(academicProgressApi.saveGroupNumbering).toHaveBeenCalledWith(5, 20))
  })

  it('read-only roles see the value; frozen ranges are listed per subject', () => {
    renderWithProviders(
      <GroupNumberingCard groupId={5} canEdit={false}
        numbering={{ ...settings, lessons_per_month: 20, group_value: 20, frozen: [{ subject: 'IT', first_lesson: 1, last_lesson: 36, first_month: 1, lessons_per_month: 12 }] }} />,
    )
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.getByText('20 занятий')).toBeInTheDocument()
    expect(screen.getByText(/IT: уроки 1–36 оставлены по 12/)).toBeInTheDocument()
  })
})
