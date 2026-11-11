/**
 * DEMO DATA FOR UI DEVELOPMENT ONLY (VITE_USE_MOCKS=true).
 *
 * Everything here is fictional and clearly labelled «Демо». It is NOT academy
 * content, NOT real student work and must never be deployed: production
 * reads everything from the Django API. Every page shows a «Демо-режим»
 * banner while mocks are on. No images are bundled — cards show the brand
 * placeholders, so nothing can be mistaken for a real photo or project.
 */
import type { ListParams } from '@/services/endpoints'
import type {
  AchievementCard,
  AchievementDetail,
  AchievementsPage,
  CourseCard,
  CourseDetail,
  EventCard,
  EventDetail,
  EventsPage,
  HomeData,
  NewsArticle,
  NewsCard,
  NewsPage,
  Paginated,
  ProjectCard,
  ProjectDetail,
  ProjectsPage,
  SiteSettings,
  SubmitResult,
  TeamMember,
  Testimonial,
  TestimonialsPage,
} from '@/types/api'

import { ApiError } from '@/services/api/client'

const DEMO = 'Демо'
const day = (offset: number, hour = 11) => {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}
const delay = <T,>(value: T): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), 250))
const notFound = () => Promise.reject(new ApiError('not_found', 404, 'Not found'))

function page<T>(items: T[], params: ListParams, size = 9): Paginated<T> {
  const pageSize = params.page_size ?? size
  const number = params.page ?? 1
  return { count: items.length, page: number, page_size: pageSize, num_pages: Math.max(1, Math.ceil(items.length / pageSize)), results: items.slice((number - 1) * pageSize, number * pageSize) }
}

const COURSES: CourseDetail[] = [
  ['python', 'python', `${DEMO}: Python для начинающих`, 10, 14],
  ['web', 'web', `${DEMO}: Веб-разработка`, 12, 16],
  ['games', 'game', `${DEMO}: Создание игр`, 9, 13],
  ['robotics', 'robot', `${DEMO}: Робототехника`, 8, 12],
  ['digital', 'digital', `${DEMO}: Цифровые навыки`, 7, 10],
].map(([slug, icon, title, min, max], i) => ({
  slug: `demo-${slug}`,
  title: title as string,
  tagline: 'Демонстрационное описание курса для проверки вёрстки.',
  icon: icon as CourseCard['icon'],
  cover: null,
  age_min: min as number,
  age_max: max as number,
  duration: null,
  schedule: null,
  lessons: null,
  price: null,
  is_featured: i < 3,
  body: 'Это **демонстрационный** текст. Реальное описание курса заполняет маркетинг в LMS.\n\n- Пункт списка\n- Ещё один пункт\n\n> Цитата для проверки оформления.',
  outcomes: ['Демо-результат обучения 1', 'Демо-результат обучения 2', 'Демо-результат обучения 3'],
  curriculum: [{ title: 'Модуль 1', text: 'Демо-описание модуля' }, { title: 'Модуль 2', text: 'Демо-описание модуля' }],
  subjects: [],
  project_category: null,
  updated_at: day(-3),
  projects: [],
}))

const PROJECTS: ProjectDetail[] = Array.from({ length: 6 }, (_, i) => ({
  key: `demo${i + 1}`,
  title: `${DEMO}-проект №${i + 1}`,
  short_description: 'Вымышленная карточка для проверки сетки. Не работа студента.',
  description: 'Демонстрационное описание.',
  technologies: [['HTML', 'CSS'], ['JavaScript'], ['React'], ['Python'], ['Python', 'Pygame'], ['Figma']][i],
  categories: [['html-css'], ['javascript'], ['react'], ['python'], ['python'], ['other']][i] as ProjectCard['categories'],
  date: day(-i * 12).slice(0, 10),
  student: null,
  group: null,
  cover_url: null,
  trainer: null,
  demo_url: null,
  images: [],
}))

const NEWS: NewsArticle[] = Array.from({ length: 5 }, (_, i) => ({
  slug: `demo-news-${i + 1}`,
  title: `${DEMO}-новость №${i + 1}`,
  excerpt: 'Демонстрационный анонс новости для проверки вёрстки карточек.',
  category: (['announcements', 'events', 'education', 'competitions', 'activities'] as const)[i],
  published_at: day(-i * 5),
  cover: null,
  author: null,
  body: '## Демо-заголовок\nДемонстрационный текст новости.\n\n- Пункт\n- Пункт',
  photos: [],
  related: [],
}))

const EVENTS: EventDetail[] = [
  [5, 'open_day'],
  [12, 'hackathon'],
  [26, 'workshop'],
  [-20, 'presentation'],
].map(([offset, category], i) => ({
  slug: `demo-event-${i + 1}`,
  title: `${DEMO}-событие №${i + 1}`,
  excerpt: 'Демонстрационное описание мероприятия.',
  category: category as EventCard['category'],
  starts_at: day(offset as number),
  ends_at: null,
  location: 'Демо-адрес',
  branch: null,
  cover: null,
  phase: (offset as number) > 0 ? 'upcoming' : 'completed',
  registration_open: (offset as number) > 0,
  is_featured: false,
  body: 'Демонстрационный текст мероприятия.',
  branch_address: null,
  photos: [],
  registration: { enabled: (offset as number) > 0, open: (offset as number) > 0, deadline: null, spots_left: 12 },
  updated_at: day(-1),
  related: [],
}))

const ACHIEVEMENTS: AchievementDetail[] = (['competition', 'award', 'partnership'] as const).map((category, i) => ({
  slug: `demo-achievement-${i + 1}`,
  title: `${DEMO}-достижение №${i + 1}`,
  excerpt: 'Вымышленная карточка достижения для проверки вёрстки.',
  category,
  date: day(-i * 30).slice(0, 10),
  cover: null,
  photo_count: 0,
  is_featured: i === 0,
  body: 'Демонстрационный текст.',
  photos: [],
  updated_at: day(-1),
  related: [],
}))

const TEAM: TeamMember[] = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1,
  name: `${DEMO}-тренер ${i + 1}`,
  position: 'Тренер (демо)',
  specialization: ['Python', 'Веб-разработка', 'Game dev', 'Робототехника'][i],
  group: (['it_trainers', 'it_trainers', 'english_trainers', 'management'] as const)[i],
  bio: 'Демонстрационная биография.',
  experience_years: null,
  photo: null,
}))

const TESTIMONIALS: Testimonial[] = Array.from({ length: 3 }, (_, i) => ({
  id: i + 1,
  author_name: `${DEMO}-автор ${i + 1}`,
  author_role: 'parent',
  course: null,
  text: 'Демонстрационный отзыв для проверки вёрстки. Это не настоящий отзыв.',
  language: 'ru',
  rating: null,
  photo: null,
  video_embed: null,
  kind: 'text',
  is_featured: false,
}))

const SETTINGS: SiteSettings = {
  hero: { title: '', subtitle: '', image: null, primary_cta: { label: '', url: '' }, secondary_cta: { label: '', url: '' } },
  intro_video: null,
  about: { story: 'Демонстрационная история академии. Реальный текст заполняется в LMS.', mission: 'Демо-миссия.', vision: 'Демо-видение.' },
  contacts: { phone: '+996 000 000 000', whatsapp: null, telegram: null, instagram: null, email: null, working_hours: 'Демо: Пн–Сб 9:00–19:00' },
  branches: [{ id: 1, name: 'Демо-филиал', address: 'Бишкек (демо-адрес)', phone: '', working_hours: '', map_url: null, latitude: 42.8746, longitude: 74.5698 }],
  stats: [{ value: '00+', label: 'Демо-показатель' }, { value: '00', label: 'Демо-показатель' }, { value: '00', label: 'Демо-показатель' }, { value: '00%', label: 'Демо-показатель' }],
  sections: ['stats', 'courses', 'projects', 'achievements', 'events', 'news', 'team', 'testimonials', 'cta'].map((key) => ({ key: key as SiteSettings['sections'][number]['key'], title: '' })),
  banners: [],
}

const card = <T extends object, K extends keyof T>(item: T, omit: K[]) => Object.fromEntries(Object.entries(item).filter(([k]) => !omit.includes(k as K))) as Omit<T, K>

export const settings = () => delay(SETTINGS)
export const home = (): Promise<HomeData> =>
  delay({
    ...SETTINGS,
    courses: COURSES.filter((c) => c.is_featured),
    projects: PROJECTS.slice(0, 3),
    news: NEWS.slice(0, 3).map((n) => ({ ...card(n, ['body', 'author', 'photos', 'related']), photo_count: 0 })),
    events: EVENTS.filter((e) => e.phase !== 'completed').slice(0, 3),
    achievements: ACHIEVEMENTS,
    team: TEAM,
    testimonials: TESTIMONIALS,
  })
export const courses = () => delay({ results: COURSES as CourseCard[] })
export const course = (slug: string) => (COURSES.find((c) => c.slug === slug) ? delay(COURSES.find((c) => c.slug === slug)!) : notFound())
export const projects = (params: ListParams): Promise<ProjectsPage> => {
  const items = params.category ? PROJECTS.filter((p) => p.categories.includes(params.category as ProjectCard['categories'][number])) : PROJECTS
  const filtered = params.technology ? items.filter((p) => p.technologies.some((t) => t.toLowerCase() === params.technology!.toLowerCase())) : items
  const technologies = [...new Set(PROJECTS.flatMap((p) => p.technologies))].map((name) => ({ name, count: PROJECTS.filter((p) => p.technologies.includes(name)).length }))
  return delay({ ...page(filtered, params, 12), counts: { all: PROJECTS.length }, technologies })
}
export const project = (key: string) => (PROJECTS.find((p) => p.key === key) ? delay(PROJECTS.find((p) => p.key === key)!) : notFound())
export const news = (params: ListParams): Promise<NewsPage> => {
  const cards: NewsCard[] = NEWS.map((n) => ({ ...card(n, ['body', 'author', 'photos', 'related']), photo_count: 0 }))
  return delay({ ...page(cards.slice(1), params), counts: { all: cards.length }, featured: params.page && params.page > 1 ? null : cards[0] })
}
export const article = (slug: string) => (NEWS.find((n) => n.slug === slug) ? delay(NEWS.find((n) => n.slug === slug)!) : notFound())
export const events = (params: ListParams): Promise<EventsPage> => {
  const items = params.phase ? EVENTS.filter((e) => e.phase === params.phase) : EVENTS
  return delay({ ...page(items, params), counts: { all: EVENTS.length, upcoming: 3, ongoing: 0, completed: 1 } })
}
export const event = (slug: string) => (EVENTS.find((e) => e.slug === slug) ? delay(EVENTS.find((e) => e.slug === slug)!) : notFound())
export const achievements = (params: ListParams): Promise<AchievementsPage> =>
  delay({ ...page(ACHIEVEMENTS as AchievementCard[], params), counts: { all: ACHIEVEMENTS.length } })
export const achievement = (slug: string) => (ACHIEVEMENTS.find((a) => a.slug === slug) ? delay(ACHIEVEMENTS.find((a) => a.slug === slug)!) : notFound())
export const team = () => delay({ results: TEAM })
export const testimonials = (params: ListParams): Promise<TestimonialsPage> =>
  delay({ ...page(TESTIMONIALS, params, 12), counts: { all: TESTIMONIALS.length, text: 3, photo: 0, video: 0 }, average_rating: null })
export const submit = (): Promise<SubmitResult> => delay({ ok: true, duplicate: false })
export const vacancies = () => delay({ count: 0, results: [] })
