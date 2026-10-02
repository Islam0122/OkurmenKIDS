import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LessonDetailPage } from '@/features/lessons/LessonDetailPage'
import { telegramShareUrl } from '@/features/lessons/ParentReportModal'
import { buildLesson, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { ParentLessonReport } from '@/types/academy'

vi.mock('@/api/lessons', () => ({
  lessonsApi: {
    get: vi.fn(),
    getAttendanceRoster: vi.fn(),
    list: vi.fn(),
    saveAttendance: vi.fn(),
    start: vi.fn(),
    complete: vi.fn(),
    cancel: vi.fn(),
    setHomeworkNotRequired: vi.fn(),
    parentReport: vi.fn(),
  },
}))
vi.mock('@/api/homework', () => ({
  homeworkApi: { list: vi.fn(), get: vi.fn(), getResultsRoster: vi.fn(), saveResults: vi.fn(), create: vi.fn() },
}))

import { homeworkApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'

const MESSAGE = [
  'Саламатсыздарбы, урматтуу ата-энелер! 🌟',
  '📚 Бүгүнкү сабакта окуучулар «Күчтүү жана коопсуз паролдор» темасын үйрөнүштү.',
  '👥 Сабакка катышкан окуучулар:\n• Бекнур Абдыбеков',
  '📚 Кийинки үй тапшырмасы:\n\nҮй тапшырмасы азырынча берилген жок.',
  '📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟',
].join('\n\n')

const TRAINER_MESSAGE = [
  'Саламатсыздарбы, урматтуу ата-энелер! 🌟',
  'Бүгүнкү сабакта «Күчтүү жана коопсуз паролдор» темасын өттүк. 📚',
  '👥 Сабакка катышкандар:\n• Бекнур Абдыбеков',
  '📚 Кийинки үй тапшырмасы:\nҮй тапшырмасы азырынча берилген жок.',
  'Рахмат! Кийинки сабакта жолугушабыз 🌟',
].join('\n\n')

function buildReport(overrides: Partial<ParentLessonReport> = {}): ParentLessonReport {
  return {
    lesson_id: 7,
    group: 'Kids 1',
    lesson_date: '2026-10-01',
    topic: 'Күчтүү жана коопсуз паролдор',
    present_students: ['Бекнур Абдыбеков'],
    absent_students: [],
    homework_checked: null,
    homework_not_completed: [],
    homework_partial: [],
    next_homework: null,
    warnings: [],
    message: MESSAGE,
    messages: { system: MESSAGE, trainer: TRAINER_MESSAGE },
    ...overrides,
  }
}

function renderLesson(status: 'scheduled' | 'in_progress' | 'completed' | 'cancelled') {
  vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status }))
  vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
  vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
  return renderWithProviders(
    <Routes>
      <Route path="/app/lessons/:id" element={<LessonDetailPage />} />
    </Routes>,
    { route: '/app/lessons/7' },
  )
}

describe('Мини-отчёт родителям', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each(['scheduled', 'cancelled'] as const)('is not offered for a %s lesson', async (status) => {
    renderLesson(status)
    await waitFor(() => expect(lessonsApi.get).toHaveBeenCalled())
    await screen.findByText('О занятии')
    expect(screen.queryByRole('button', { name: 'Сформировать отчёт родителям' })).not.toBeInTheDocument()
  })

  it('shows the backend-built preview with the trainer-only warnings', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(
      buildReport({ warnings: ['Посещаемость не отмечена у 1 студент(ов): Йасин Ибрахимов.'] }),
    )
    const user = userEvent.setup()
    renderLesson('completed')

    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))

    const preview = await screen.findByTestId('parent-report-preview')
    expect(preview.textContent).toBe(MESSAGE)
    expect(lessonsApi.parentReport).toHaveBeenCalledWith(7)
    expect(screen.getByText('Проверьте перед отправкой')).toBeInTheDocument()
    expect(screen.getByText(/Йасин Ибрахимов/)).toBeInTheDocument()
    expect(preview.textContent).not.toContain('Посещаемость не отмечена у 1')
  })

  it('switches between the system and the trainer text, «Системный» by default', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = userEvent.setup()
    renderLesson('completed')

    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))
    await screen.findByTestId('parent-report-preview')

    const group = screen.getByRole('radiogroup', { name: 'Тип отчёта' })
    expect(within(group).getAllByRole('radio').map((radio) => radio.textContent)).toEqual([
      '🤖 Системный',
      '👨‍🏫 От тренера',
      '✏️ Свой вариант',
    ])
    expect(screen.getByRole('radio', { name: '🤖 Системный' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(MESSAGE)

    await user.click(screen.getByRole('radio', { name: '👨‍🏫 От тренера' }))
    expect(screen.getByRole('radio', { name: '👨‍🏫 От тренера' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: '🤖 Системный' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(TRAINER_MESSAGE)
    expect(screen.queryByRole('textbox', { name: 'Текст отчёта' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Отправить в Telegram' })).toHaveAttribute('href', telegramShareUrl(TRAINER_MESSAGE))
  })

  it('«Свой вариант» edits a copy of the system text, then copies and sends it', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    renderLesson('in_progress')

    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))
    await screen.findByTestId('parent-report-preview')

    await user.click(screen.getByRole('radio', { name: '✏️ Свой вариант' }))
    expect(screen.queryByTestId('parent-report-preview')).not.toBeInTheDocument()
    const textarea = screen.getByRole('textbox', { name: 'Текст отчёта' })
    expect(textarea).toHaveValue(MESSAGE)
    expect(screen.getByText(`Символов: ${MESSAGE.length}`)).toBeInTheDocument()

    await user.type(textarea, '\nP.S. Эртең 10:00дө.')
    const edited = `${MESSAGE}\nP.S. Эртең 10:00дө.`
    expect(textarea).toHaveValue(edited)
    expect(screen.getByText(`Символов: ${edited.length}`)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Копировать' }))
    expect(writeText).toHaveBeenCalledWith(edited)
    expect(await screen.findByText('Текст скопирован')).toBeInTheDocument()
    const send = screen.getByRole('link', { name: 'Отправить в Telegram' })
    expect(send).toHaveAttribute('href', telegramShareUrl(edited))
    expect(send).toHaveAttribute('target', '_blank')

    // The edit survives a look at another type, and the system text itself is untouched.
    await user.click(screen.getByRole('radio', { name: '🤖 Системный' }))
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(MESSAGE)
    await user.click(screen.getByRole('radio', { name: '✏️ Свой вариант' }))
    expect(screen.getByRole('textbox', { name: 'Текст отчёта' })).toHaveValue(edited)

    await user.click(screen.getByRole('button', { name: 'Вернуть системный текст' }))
    expect(screen.getByRole('textbox', { name: 'Текст отчёта' })).toHaveValue(MESSAGE)
    // Only GETs the report: editing the message never writes to the LMS.
    expect(lessonsApi.parentReport).toHaveBeenCalledTimes(1)
  })

  it('disables copy and Telegram for an empty custom text', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = userEvent.setup()
    renderLesson('completed')

    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))
    await screen.findByTestId('parent-report-preview')
    await user.click(screen.getByRole('radio', { name: '✏️ Свой вариант' }))
    await user.clear(screen.getByRole('textbox', { name: 'Текст отчёта' }))

    expect(screen.getByRole('button', { name: 'Копировать' })).toBeDisabled()
    // Without an href the anchor is no longer a link — it's disabled.
    const send = screen.getByText('Отправить в Telegram').closest('a')
    expect(send).toHaveAttribute('aria-disabled', 'true')
    expect(send).not.toHaveAttribute('href')
    expect(screen.getByText('Символов: 0')).toBeInTheDocument()
  })

  it('builds the Telegram share link from the whole message', () => {
    expect(telegramShareUrl('Салам 🌟\n• Бекнур')).toBe(
      `https://t.me/share/url?url=${encodeURIComponent('Салам 🌟\n• Бекнур')}`,
    )
  })
})
