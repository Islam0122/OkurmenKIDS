import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { createQueryClient } from '@/app/providers/AppProviders'
import { EnrollmentProvider } from '@/features/enrollment/EnrollmentProvider'
import { I18nProvider } from '@/i18n'
import { HomePage } from '@/pages/Home/HomePage'
import { TeamPage } from '@/pages/Team/TeamPage'
import type { Lang, TeamMember } from '@/types/api'

/**
 * «Руководство академии» vs «Наши преподаватели»: the split comes from the CMS
 * field `category` and is the same on the homepage and on /team. Shaped like
 * the real data: the directors are stored in the «Администрация» department.
 */
const { members, home, page } = vi.hoisted(() => {
  const m = (id: number, name: string, position: string, category: string, group: string | null, extra = {}) =>
    ({ id, slug: `m${id}`, name, position, category, group, specialization: null, bio: `Био ${id}`, experience_years: null, photo: null, ...extra })
  const members = [
    m(2, 'Мунарбек Мавлянов', 'Директор академии', 'management', 'administration', { specialization: 'Управление академией' }),
    m(3, 'Усупбаева Аделина', 'Операционный директор', 'management', 'administration'),
    m(6, 'Хадижа Асангазиева', 'IT-специалист и Python-тренер', 'teacher', 'it_trainers', { specialization: 'Python, Django' }),
    m(1, 'Ислам Дуйшобаев', 'Full-Stack разработчик', 'teacher', 'it_trainers'),
    m(4, 'Айдана Дуйшемуратова', 'Тренер по ораторскому мастерству', 'teacher', 'soft_skills_trainers'),
    m(5, 'Нурсултан Караталов', 'IT-тренер', 'teacher', 'it_trainers'),
  ]
  const home = {
    hero: { title: 'Будущее', subtitle: '', image: null, primary_cta: { label: '', url: '' }, secondary_cta: { label: '', url: '' } },
    intro_video: null,
    about: { story: '', mission: '', vision: '' },
    contacts: { phone: '', whatsapp: null, telegram: null, instagram: null, facebook: null, youtube: null, tiktok: null, email: null, working_hours: null },
    branches: [], stats: [], banners: [], seo: { title: null, description: null, image: null },
    sections: [{ key: 'team', title: '' }],
    courses: [], projects: [], achievements: [], news: [], events: [], testimonials: [],
    team: members.filter((x) => x.category === 'teacher').slice(0, 4),
    management: members.filter((x) => x.category === 'management'),
  }
  const page = { count: 0, page: 1, page_size: 6, num_pages: 1, results: [] }
  return { members, home, page }
})

vi.mock('@/services/endpoints', () => ({
  siteApi: {
    home: vi.fn().mockResolvedValue(home),
    team: vi.fn().mockResolvedValue({ results: members }),
    courses: vi.fn().mockResolvedValue({ results: [] }),
    settings: vi.fn().mockResolvedValue({ branches: [], contacts: {} }),
    events: vi.fn().mockResolvedValue(page),
    achievements: vi.fn().mockResolvedValue(page),
  },
  careersApi: { vacancies: vi.fn().mockResolvedValue({ count: 0 }) },
}))

function renderAt(ui: React.ReactNode, lang: Lang = 'ru') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <I18nProvider lang={lang}><EnrollmentProvider>{ui}</EnrollmentProvider></I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const names = (el: HTMLElement) => within(el).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
const DIRECTORS = ['Мунарбек Мавлянов', 'Усупбаева Аделина']

describe('Team categories', () => {
  it('/team: directors only in «Руководство академии», teachers only in «Наши преподаватели», no duplicates', async () => {
    renderAt(<TeamPage />)
    const management = (await screen.findByRole('heading', { level: 2, name: 'Руководство академии' })).closest('section')!
    const teachers = screen.getByRole('heading', { level: 2, name: 'Наши преподаватели' }).closest('section')!
    expect(names(management)).toEqual(DIRECTORS)
    // Teachers are split by department (h3) with cards inside (card names are h3 too).
    const teacherNames = names(teachers).filter((n) => !['IT-направление', 'Soft Skills'].includes(n ?? ''))
    expect(teacherNames.sort()).toEqual(['Айдана Дуйшемуратова', 'Ислам Дуйшобаев', 'Нурсултан Караталов', 'Хадижа Асангазиева'])
    for (const d of DIRECTORS) expect(screen.getAllByRole('heading', { level: 3, name: d })).toHaveLength(1)
    // Management cards: no skill chips; teacher cards: skills shown.
    expect(within(management).queryByRole('list', { name: 'Специализация' })).toBeNull()
    expect(within(teachers).getByRole('list', { name: 'Специализация' })).toHaveTextContent('Python')
  })

  it('homepage: «Наши преподаватели» never contains management; leadership has its own block', async () => {
    renderAt(<HomePage />)
    const teachers = (await screen.findByRole('heading', { level: 2, name: 'Наши преподаватели' })).closest('section')!
    const management = screen.getByRole('heading', { level: 2, name: 'Руководство академии' }).closest('section')!
    for (const d of DIRECTORS) expect(within(teachers).queryByText(d)).toBeNull()
    expect(names(management)).toEqual(DIRECTORS)
    expect(names(teachers)).toHaveLength(4)
  })

  it('KG labels', async () => {
    renderAt(<TeamPage />, 'ky')
    expect(await screen.findByRole('heading', { level: 2, name: 'Академиянын жетекчилиги' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Биздин мугалимдер' })).toBeInTheDocument()
  })

  it('an older API without `category` still keeps directors («Администрация») out of the teachers block', async () => {
    const { siteApi } = await import('@/services/endpoints')
    const legacy = members.map(({ category: _c, ...rest }) => rest) as TeamMember[]
    vi.mocked(siteApi.home).mockResolvedValueOnce({ ...home, team: legacy, management: undefined } as never)
    renderAt(<HomePage />)
    const teachers = (await screen.findByRole('heading', { level: 2, name: 'Наши преподаватели' })).closest('section')!
    for (const d of DIRECTORS) expect(within(teachers).queryByText(d)).toBeNull()
    expect(names(screen.getByRole('heading', { level: 2, name: 'Руководство академии' }).closest('section')!)).toEqual(DIRECTORS)
  })
})
