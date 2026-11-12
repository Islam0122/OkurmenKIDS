import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { createQueryClient } from '@/app/providers/AppProviders'
import { EnrollmentProvider } from '@/features/enrollment/EnrollmentProvider'
import { I18nProvider } from '@/i18n'
import { AboutPage } from '@/pages/About/AboutPage'
import { PROGRAMS, programTarget } from '@/pages/About/programs'
import type { CourseCard, Lang } from '@/types/api'

const { photo, page } = vi.hoisted(() => ({
  photo: (n: number) => ({ url: `/media/p${n}.webp`, thumb: `/media/p${n}-t.webp`, width: 1200, height: 900, caption: '' }),
  page: <T,>(results: T[], extra = {}) => ({ count: results.length, page: 1, page_size: 12, num_pages: 1, results, counts: {}, ...extra }),
}))

vi.mock('@/services/endpoints', () => ({
  siteApi: {
    settings: vi.fn().mockResolvedValue({
      hero: { title: '', subtitle: '', image: null, primary_cta: { label: '', url: '' }, secondary_cta: { label: '', url: '' } },
      intro_video: null,
      about: { story: '', mission: '', vision: '' },
      contacts: { phone: '+996504677725', whatsapp: null, telegram: null, instagram: null, facebook: null, youtube: null, tiktok: null, email: null, working_hours: null },
      branches: [{ id: 1, name: 'Окурмен Кидс', address: '​Улица Орозбекова, 136', phone: '', working_hours: 'Пн–Вс, 10:00–20:00', map_url: null, latitude: null, longitude: null }],
      stats: [{ value: '5000+', label: 'Учеников' }, { value: '4', label: 'Лет опыта' }],
      sections: [], banners: [], seo: { title: null, description: null, image: null },
    }),
    courses: vi.fn().mockResolvedValue({ results: [] }),
    team: vi.fn().mockResolvedValue({
      results: [
        { id: 1, slug: 'director', name: 'Директор Академии', position: 'Директор', group: 'administration', specialization: null, bio: '', experience_years: null, photo: null },
        { id: 2, slug: 'python-trainer', name: 'Тренер Python', position: 'Python-тренер', group: 'it_trainers', specialization: 'Python, FastAPI', bio: 'Био', experience_years: 4, photo: null },
      ],
    }),
    testimonials: vi.fn().mockResolvedValue(page([
      { id: 7, author_name: 'Айгуль', author_role: 'parent', course: null, text: 'Спасибо академии!', language: 'ru', rating: 5, photo: null, video_embed: null, kind: 'text', is_featured: false },
    ], { average_rating: 5 })),
    events: vi.fn().mockResolvedValue(page([])),
    achievements: vi.fn().mockResolvedValue(page([
      { slug: 'vypusk', title: 'Выпуск групп', category: 'other', cover: photo(1), date: null, excerpt: '', is_featured: false, photo_count: 1, recipient: null },
      { slug: 'turnir', title: 'Футбольный турнир', category: 'other', cover: photo(2), date: null, excerpt: '', is_featured: false, photo_count: 1, recipient: null },
    ])),
    achievement: vi.fn((slug: string) => Promise.resolve({
      slug, title: slug === 'vypusk' ? 'Выпуск групп' : 'Футбольный турнир',
      photos: [{ ...photo(slug === 'vypusk' ? 5 : 6), caption: slug === 'vypusk' ? 'Вручение сертификатов' : '' }],
    })),
    lead: vi.fn(),
  },
  newsApi: {
    list: vi.fn().mockResolvedValue(page([
      { slug: 'ololo', title: 'Экскурсия в Ololo', category: 'events', cover: photo(3), excerpt: '', published_at: '2026-11-01', photo_count: 1 },
      { slug: 'nabor', title: 'Открыт набор', category: 'announcements', cover: photo(4), excerpt: '', published_at: '2026-11-02', photo_count: 1 },
    ])),
  },
  projectsApi: { list: vi.fn().mockResolvedValue(page([], { counts: { all: 6, 'html-css': 3, javascript: 3, react: 0, python: 0, other: 3 } })) },
}))

function renderAbout(lang: Lang = 'ru') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[lang === 'ru' ? '/about' : `/${lang}/about`]}>
        <I18nProvider lang={lang}>
          <EnrollmentProvider><AboutPage /></EnrollmentProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const course = (slug: string, title: string) => ({ slug, title }) as CourseCard
const program = (id: string) => PROGRAMS.find((p) => p.id === id)!

describe('About page — program links', () => {
  it('links to a published course page first', () => {
    expect(programTarget(program('python'), [course('python-start', 'Python Start')], {})).toEqual({ kind: 'course', to: '/courses/python-start' })
    expect(programTarget(program('fastapi'), [course('python-backend', 'Python + FastAPI')], {})).toEqual({ kind: 'course', to: '/courses/python-backend' })
    // A FastAPI course is not taken for the Python card, a React course not for HTML/CSS/JS.
    expect(programTarget(program('python'), [course('python-backend', 'Python + FastAPI')], {})).toEqual({ kind: 'enroll' })
    expect(programTarget(program('html'), [course('react', 'React')], {})).toEqual({ kind: 'enroll' })
  })

  it('falls back to real student projects, then to the enrollment form — never to an invented page', () => {
    expect(programTarget(program('html'), [], { 'html-css': 3 })).toEqual({ kind: 'projects', to: '/projects?category=html-css' })
    expect(programTarget(program('react'), [], { react: 0 })).toEqual({ kind: 'enroll' })
    for (const id of ['fastapi', 'vibe', 'literacy']) expect(programTarget(program(id), [], { 'html-css': 3 })).toEqual({ kind: 'enroll' })
  })
})

describe('About page', () => {
  it('renders the hero, CMS stats and the six programs with real destinations', async () => {
    renderAbout()
    expect(screen.getByRole('heading', { level: 1, name: 'Мы учим детей создавать технологии, а не просто пользоваться ими.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Познакомиться с академией/ })).toHaveAttribute('href', '#approach')
    expect(screen.getByRole('link', { name: 'Посмотреть проекты учеников' })).toHaveAttribute('href', '/projects')
    expect((await screen.findAllByText('5000+')).length).toBeGreaterThan(0)

    const programs = (await screen.findByRole('heading', { name: 'Чему учатся дети' })).closest('section')!
    expect(within(programs).getAllByRole('listitem')).toHaveLength(6)
    expect(await within(programs).findByRole('link', { name: /HTML, CSS и JavaScript — Смотреть проекты/ })).toHaveAttribute('href', '/projects?category=html-css')
    // No published course pages and no React/Python projects → the enrollment form, not a dead link.
    expect(within(programs).getAllByRole('button', { name: /Узнать подробнее/ })).toHaveLength(5)
    expect(within(programs).queryByRole('link', { name: /\/courses\// })).toBeNull()
  })

  it('shows only CMS trainers, published testimonials and real photos', async () => {
    renderAbout()
    const trainers = (await screen.findByRole('heading', { name: 'Тренеры академии' })).closest('section')!
    expect(within(trainers).getByRole('link', { name: /Тренер Python/ })).toHaveAttribute('href', '/team/python-trainer')
    expect(within(trainers).queryByText('Директор Академии')).toBeNull()

    expect(await screen.findByText('Спасибо академии!')).toBeInTheDocument()
    expect(screen.getByText(/Средняя оценка 5 из 5 · отзывов: 1/)).toBeInTheDocument()

    // Hero = the first real photo; the gallery holds the other covers and album photos (caption or title as alt).
    expect(await screen.findByRole('img', { name: 'Выпуск групп' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'Вручение сертификатов' })).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'Футбольный турнир' })).toHaveLength(2)
    // Event news covers are academy photos; announcement covers (often illustrations) are not used.
    expect(screen.getByRole('img', { name: 'Экскурсия в Ololo' })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Открыт набор' })).toBeNull()
  })

  it('answers the FAQ from CMS data (branch, hours, phone) without stray characters', async () => {
    renderAbout()
    expect(await screen.findByText('В филиале «Окурмен Кидс»: Улица Орозбекова, 136. Часы работы: Пн–Вс, 10:00–20:00.')).toBeInTheDocument()
    expect(screen.getByText(/Можно также позвонить: \+996504677725/)).toBeInTheDocument()
    expect(screen.getAllByRole('group')).toHaveLength(6)
    expect(screen.getByRole('button', { name: /Записать ребёнка на пробное занятие/ })).toBeInTheDocument()
  })

  it('works in Kyrgyz with localized links', async () => {
    renderAbout('ky')
    expect(screen.getByRole('heading', { level: 1, name: 'Биз балдарды технологияны жөн гана колдонууга эмес, аны түзүүгө үйрөтөбүз.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Окуучулардын долбоорлорун көрүү' })).toHaveAttribute('href', '/ky/projects')
    expect(await screen.findByRole('heading', { name: 'Балдар эмнени үйрөнөт' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Тренер Python/ })).toHaveAttribute('href', '/ky/team/python-trainer')
  })
})
