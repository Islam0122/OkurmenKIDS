import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { createQueryClient } from '@/app/providers/AppProviders'
import { EnrollmentProvider } from '@/features/enrollment/EnrollmentProvider'
import { I18nProvider } from '@/i18n'
import { HomePage } from '@/pages/Home/HomePage'
import type { Lang } from '@/types/api'

const { home } = vi.hoisted(() => {
  const img = (n: number) => ({ url: `/media/x${n}.webp`, thumb: `/media/x${n}-t.webp`, width: 1200, height: 900, caption: '' })
  const project = (n: number) => ({
    key: `p${n}`, title: `Проект ${n}`, short_description: `Описание ${n}`, technologies: ['HTML', 'CSS'], categories: ['html-css'],
    date: '2026-11-11', student: n === 1 ? 'Батыр А.' : null, group: null, cover_url: `/media/projects/p${n}.png`,
    cover: n === 1 ? { url: '/media/projects/p1.png.large.webp', thumb: '/media/projects/p1.png.thumb.webp', width: 2400, height: 1500, caption: '' } : null,
  })
  const achievement = (n: number) => ({ slug: `a${n}`, title: `Достижение ${n}`, category: 'certificates', cover: img(n), date: '2026-09-26', excerpt: `Итог ${n}`, is_featured: false, photo_count: 1, recipient: null })
  const news = (n: number) => ({ slug: `n${n}`, title: `Новость ${n}`, category: 'events', cover: img(10 + n), excerpt: `Текст ${n}`, published_at: '2026-11-11', photo_count: 1 })
  return {
    home: {
      hero: { title: 'Будущее начинается с первой строки кода', subtitle: '', image: null, primary_cta: { label: '', url: '' }, secondary_cta: { label: '', url: '' } },
      intro_video: null,
      about: { story: '', mission: '', vision: '' },
      contacts: { phone: '+996504677725', whatsapp: null, telegram: null, instagram: null, facebook: null, youtube: null, tiktok: null, email: null, working_hours: null },
      branches: [],
      stats: [{ value: '5000+', label: 'Учеников' }, { value: '4', label: 'Лет опыта' }, { value: '95%', label: 'Доверие родителей' }],
      banners: [],
      seo: { title: null, description: null, image: null },
      sections: ['stats', 'courses', 'projects', 'achievements', 'news', 'events', 'cta'].map((key) => ({ key, title: '' })),
      courses: [],
      projects: [1, 2, 3, 4, 5, 6].map(project),
      achievements: [1, 2, 3, 4].map(achievement),
      news: [1, 2, 3, 4].map(news),
      events: [], team: [], testimonials: [],
    },
  }
})

vi.mock('@/services/endpoints', () => ({
  siteApi: {
    home: vi.fn().mockResolvedValue(home),
    courses: vi.fn().mockResolvedValue({ results: [] }),
    settings: vi.fn().mockResolvedValue({ branches: [], contacts: {} }),
    lead: vi.fn(),
  },
  projectsApi: { list: vi.fn().mockResolvedValue({ count: 6, page: 1, page_size: 1, num_pages: 6, results: [], counts: { all: 6, 'html-css': 6, react: 0, python: 0 } }) },
}))

function renderHome(lang: Lang = 'ru') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[lang === 'ru' ? '/' : `/${lang}`]}>
        <I18nProvider lang={lang}>
          <EnrollmentProvider><HomePage /></EnrollmentProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const section = async (heading: string) => (await screen.findByRole('heading', { name: heading })).closest('section')!

describe('Homepage', () => {
  it('renders the hero from the approved copy with the enrollment and programs actions', async () => {
    renderHome()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Будущее начинается с первой строки кода')
    expect(screen.getByText('IT-академия для детей 9–⁠15 лет')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Записать на пробное занятие/ })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Узнать о программах' })).toHaveAttribute('href', '#programs')
    expect(screen.getByRole('figure', { name: /Ноутбук с редактором кода/ })).toBeInTheDocument()
  })

  it('shows only the statistics entered in the CMS — no invented numbers', async () => {
    renderHome()
    const stats = await screen.findByRole('region', { name: 'Академия в цифрах' })
    expect(within(stats).getAllByRole('listitem')).toHaveLength(3)
    expect(within(stats).getByText('5000+')).toBeInTheDocument()
    expect(screen.queryByText('100+')).toBeNull()
  })

  it('shows the six programs; without published course pages they link to real projects or the enrollment form', async () => {
    renderHome()
    const programs = await section('Популярные курсы')
    expect(within(programs).getAllByRole('listitem')).toHaveLength(6)
    expect(await within(programs).findByRole('link', { name: 'Web Development — Подробнее' })).toHaveAttribute('href', '/projects?category=html-css')
    expect(within(programs).getAllByRole('button', { name: /— Подробнее/ })).toHaveLength(5)
    // No age label without a CMS course that states the ages.
    expect(within(programs).queryByText(/\d+–\d+ лет$/)).toBeNull()
  })

  it('limits projects, achievements and news to three real items and uses the WebP thumbnail for project covers', async () => {
    renderHome()
    const projects = await section('Реальные проекты наших студентов')
    expect(within(projects).getAllByRole('link', { name: /Проект \d/ })).toHaveLength(3)
    const cover = projects.querySelector('a[href="/projects/p1"] img')!
    expect(cover.getAttribute('src')).toContain('p1.png.thumb.webp')
    expect(projects.querySelector('a[href="/projects/p2"] img')!.getAttribute('src')).toContain('/media/projects/p2.png')
    expect(within(projects).getByRole('link', { name: /Все проекты/ })).toHaveAttribute('href', '/projects')

    const achievements = await section('Достижения академии')
    expect(within(achievements).getAllByRole('heading', { level: 3 })).toHaveLength(3)
    const news = await section('Последние новости')
    expect(within(news).getAllByText('Читать новость')).toHaveLength(3)
    expect(within(news).queryByText('Новость 4')).toBeNull()
  })

  it('closes with the rocket call to action that opens the existing enrollment form', async () => {
    renderHome()
    const cta = await section('Поможем ребёнку сделать первый шаг в IT')
    await userEvent.click(within(cta).getByRole('button', { name: /Записать ребёнка/ }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('works in Kyrgyz', async () => {
    renderHome('ky')
    expect(screen.getByText('9–⁠15 жаштагы балдар үчүн IT-академия')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Популярдуу курстар' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Web Development — Кененирээк' })).toHaveAttribute('href', '/ky/projects?category=html-css')
  })
})
