import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { createQueryClient } from '@/app/providers/AppProviders'
import { EnrollmentProvider } from '@/features/enrollment/EnrollmentProvider'
import { I18nProvider } from '@/i18n'
import { CourseView } from '@/pages/Courses/CourseDetailPage'
import type { CourseDetail, Lang } from '@/types/api'

vi.mock('@/services/endpoints', () => ({
  siteApi: {
    courses: vi.fn().mockResolvedValue({ results: [] }),
    settings: vi.fn().mockResolvedValue({ branches: [], contacts: {} }),
    lead: vi.fn(),
  },
}))

/** What GET /api/v1/public/site/courses/<slug>/?lang=… returns: `schedule` already in the visitor's language. */
const course = (schedule: string | null): CourseDetail => ({
  slug: 'python', title: 'Python', tagline: '', icon: 'python', cover: null, age_min: 10, age_max: 14, duration: null,
  schedule, lessons: 72, price: null, is_featured: false, body: '', outcomes: [], curriculum: [], subjects: [],
  project_category: null, updated_at: '2026-11-12T10:00:00Z', projects: [],
})

function renderCourse(data: CourseDetail, lang: Lang = 'ru') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <I18nProvider lang={lang}>
          <EnrollmentProvider><CourseView course={data} /></EnrollmentProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const scheduleValue = () => screen.getByText('Формат').closest('div')!.querySelector('dd')!

describe('Course page — «Формат занятий»', () => {
  it('keeps line breaks of a long multi-line format and gives it the full row', () => {
    const text = 'Пн, Ср, Пт — 18:00–19:30\nГруппы до 10 детей\n' + 'Подробности: '.repeat(12)
    renderCourse(course(text))
    const dd = scheduleValue()
    expect(dd.textContent).toBe(text)
    expect(dd).toHaveClass('whitespace-pre-line')
    expect(dd.parentElement).toHaveClass('col-span-full')
  })

  it('keeps a short format as a compact tile', () => {
    renderCourse(course('2 раза в неделю'))
    expect(scheduleValue().parentElement).not.toHaveClass('col-span-full')
  })

  it('shows the text of the visitor’s language as the API returns it', () => {
    renderCourse(course('Дш, Шр — 18:00\nТопто 10 бала'), 'ky')
    expect(scheduleValue().textContent).toBe('Дш, Шр — 18:00\nТопто 10 бала')
  })

  it('hides the tile when there is no format', () => {
    renderCourse(course(null))
    expect(screen.queryByText('Формат')).toBeNull()
  })
})
