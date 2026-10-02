import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
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
  'Бүгүнкү сабакта окуучулар «Күчтүү жана коопсуз паролдор» темасын үйрөнүштү. 📚',
  '👥 Сабакка катышкан окуучулар:\n• Бекнур Абдыбеков',
  '📝 Кийинки үй тапшырмасы:',
  'Үй тапшырмасы азырынча берилген жок.',
  '📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟',
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

  it('lets the trainer edit, copy and send the edited text to Telegram', async () => {
    vi.mocked(lessonsApi.parentReport).mockResolvedValue(buildReport())
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    renderLesson('in_progress')

    await user.click(await screen.findByRole('button', { name: 'Сформировать отчёт родителям' }))
    await screen.findByTestId('parent-report-preview')

    await user.click(screen.getByRole('button', { name: 'Редактировать' }))
    const textarea = screen.getByRole('textbox', { name: 'Текст отчёта' })
    await user.type(textarea, '\nP.S. Эртең 10:00дө.')
    await user.click(screen.getByRole('button', { name: 'Готово' }))

    const edited = `${MESSAGE}\nP.S. Эртең 10:00дө.`
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(edited)

    await user.click(screen.getByRole('button', { name: 'Копировать' }))
    expect(writeText).toHaveBeenCalledWith(edited)
    expect(await screen.findByText('Текст скопирован')).toBeInTheDocument()

    const send = screen.getByRole('link', { name: 'Отправить в Telegram' })
    expect(send).toHaveAttribute('href', telegramShareUrl(edited))
    expect(send).toHaveAttribute('target', '_blank')

    await user.click(screen.getByRole('button', { name: 'Сбросить правки' }))
    expect(screen.getByTestId('parent-report-preview').textContent).toBe(MESSAGE)
  })

  it('builds the Telegram share link from the whole message', () => {
    expect(telegramShareUrl('Салам 🌟\n• Бекнур')).toBe(
      `https://t.me/share/url?url=${encodeURIComponent('Салам 🌟\n• Бекнур')}`,
    )
  })
})
