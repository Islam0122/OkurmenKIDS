import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LessonDetailPage } from '@/features/lessons/LessonDetailPage'
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

  async function openReport(status: 'in_progress' | 'completed' = 'completed') {
    const user = userEvent.setup()
    renderLesson(status)
    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))
    await screen.findByTestId('parent-report-preview')
    return user
  }

  it('offers three report authors, «Система» by default, and only edit + copy actions', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    await openReport()

    expect(screen.getByRole('heading', { name: 'Мини-отчёт родителям' })).toBeInTheDocument()
    const group = screen.getByRole('radiogroup', { name: 'Автор отчёта' })
    const authors = within(group).getAllByRole('radio')
    expect(authors.map((radio) => radio.textContent)).toEqual([
      'СистемаАвтоматически сформированный отчёт',
      'ТренерОтчёт от имени тренера',
      'Свой вариантМожно изменить текст вручную',
    ])
    expect(authors.map((radio) => radio.getAttribute('aria-checked'))).toEqual(['true', 'false', 'false'])
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(MESSAGE)
    // The system text can't be changed by accident: no textarea until «Редактировать».
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Редактировать' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Копировать' })).toBeInTheDocument()
  })

  it('uses the project\'s Lucide icons for the title, authors and buttons — no emoji', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    const user = await openReport()

    const hasIcon = (element: HTMLElement, name: string) =>
      expect(element.querySelector(`svg.lucide-${name}`), `${element.textContent} → ${name}`).not.toBeNull()
    hasIcon(screen.getByRole('heading', { name: 'Мини-отчёт родителям' }), 'message-square')
    const [system, trainer, custom] = within(screen.getByRole('radiogroup', { name: 'Автор отчёта' })).getAllByRole('radio')
    hasIcon(system, 'bot')
    hasIcon(trainer, 'user-round')
    hasIcon(custom, 'pen-line')
    hasIcon(screen.getByRole('button', { name: 'Редактировать' }), 'pen-line')
    hasIcon(screen.getByRole('button', { name: 'Копировать' }), 'copy')

    const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u
    const chrome = [
      screen.getByRole('heading', { name: 'Мини-отчёт родителям' }),
      screen.getByRole('radiogroup', { name: 'Автор отчёта' }),
      screen.getByRole('button', { name: 'Редактировать' }),
      screen.getByRole('button', { name: 'Копировать' }),
    ]
    chrome.forEach((element) => expect(element.textContent).not.toMatch(emoji))

    await user.click(screen.getByRole('button', { name: 'Копировать' }))
    expect(await screen.findByText('Отчёт скопирован')).toBeInTheDocument()
    hasIcon(screen.getByRole('button', { name: 'Копировать' }), 'copy')
  })

  it('has no Telegram in the dialog at all — not even hidden', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = await openReport()

    for (const author of ['Система', 'Тренер', 'Свой вариант']) {
      await user.click(screen.getByRole('radio', { name: new RegExp(author) }))
      const dialog = screen.getByRole('dialog')
      expect(dialog.textContent).not.toMatch(/telegram/i)
      expect(dialog.querySelector('a[href*="t.me"]')).toBeNull()
      expect(within(dialog).queryByRole('link')).not.toBeInTheDocument()
    }
  })

  it('«Тренер» switches the preview to the trainer text', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = await openReport()

    await user.click(screen.getByRole('radio', { name: /Тренер/ }))
    expect(screen.getByRole('radio', { name: /Тренер/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /Система/ })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(TRAINER_MESSAGE)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('copies the selected text and confirms «Отчёт скопирован»', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    const user = await openReport()

    await user.click(screen.getByRole('radio', { name: /Тренер/ }))
    await user.click(screen.getByRole('button', { name: 'Копировать' }))

    expect(writeText).toHaveBeenCalledWith(TRAINER_MESSAGE)
    expect(await screen.findByText('Отчёт скопирован')).toBeInTheDocument()
  })

  it('«Свой вариант» opens the textarea; «Сохранить» keeps the edit, copy sends it to the clipboard', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    const user = await openReport('in_progress')

    await user.click(screen.getByRole('radio', { name: /Свой вариант/ }))
    expect(screen.queryByTestId('parent-report-preview')).not.toBeInTheDocument()
    const textarea = screen.getByRole('textbox', { name: 'Текст отчёта' })
    expect(textarea).toHaveValue(MESSAGE)
    expect(screen.getByText(`Символов: ${MESSAGE.length}`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Копировать' })).toBeInTheDocument()

    await user.type(textarea, '\nP.S. Эртең 10:00дө.')
    const edited = `${MESSAGE}\nP.S. Эртең 10:00дө.`
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(edited)
    await user.click(screen.getByRole('button', { name: 'Копировать' }))
    expect(writeText).toHaveBeenCalledWith(edited)

    // A look at the automatic text and back keeps the edit.
    await user.click(screen.getByRole('radio', { name: /Система/ }))
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(MESSAGE)
    await user.click(screen.getByRole('radio', { name: /Свой вариант/ }))
    expect(screen.getByRole('textbox', { name: 'Текст отчёта' })).toHaveValue(edited)

    // Only GETs the report: editing the message never writes to the LMS.
    expect(lessonsApi.parentReport).toHaveBeenCalledTimes(1)
  })

  it('«Редактировать» starts «Свой вариант» from the text on screen', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = await openReport()

    await user.click(screen.getByRole('radio', { name: /Тренер/ }))
    await user.click(screen.getByRole('button', { name: 'Редактировать' }))

    expect(screen.getByRole('radio', { name: /Свой вариант/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('textbox', { name: 'Текст отчёта' })).toHaveValue(TRAINER_MESSAGE)
  })

  it('disables copy for an empty custom text', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = await openReport()

    await user.click(screen.getByRole('radio', { name: /Свой вариант/ }))
    await user.clear(screen.getByRole('textbox', { name: 'Текст отчёта' }))

    expect(screen.getByRole('button', { name: 'Копировать' })).toBeDisabled()
    expect(screen.getByText('Символов: 0')).toBeInTheDocument()
  })
})
