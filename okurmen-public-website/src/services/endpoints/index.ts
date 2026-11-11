/**
 * One function per public endpoint. With VITE_USE_MOCKS=true (UI development
 * only) the same functions return the clearly-labelled demo fixtures from
 * src/mocks — loaded lazily, so they never ship in a production bundle's
 * main chunk.
 */
import { env } from '@/app/config/env'
import { get, post } from '@/services/api/client'
import type {
  AchievementDetail,
  AchievementsPage,
  CourseCard,
  CourseDetail,
  EventDetail,
  EventsPage,
  HomeData,
  LeadInput,
  NewsArticle,
  NewsPage,
  PreviewData,
  ProjectDetail,
  ProjectsPage,
  RegistrationInput,
  SiteSettings,
  SubmitResult,
  TeamMember,
  TestimonialsPage,
  VacanciesPage,
} from '@/types/api'

export interface ListParams {
  page?: number
  page_size?: number
  q?: string
  category?: string
  phase?: string
  kind?: string
  technology?: string
}

type Mocks = typeof import('@/mocks/fixtures')
const mocks = (): Promise<Mocks> => import('@/mocks/fixtures')
const mocked = <T>(pick: (m: Mocks) => T | Promise<T>): Promise<T> => mocks().then(pick)

export const siteApi = {
  settings: () => (env.useMocks ? mocked((m) => m.settings()) : get<SiteSettings>('/site/settings/')),
  home: () => (env.useMocks ? mocked((m) => m.home()) : get<HomeData>('/site/home/')),
  courses: () => (env.useMocks ? mocked((m) => m.courses()) : get<{ results: CourseCard[] }>('/site/courses/')),
  course: (slug: string) => (env.useMocks ? mocked((m) => m.course(slug)) : get<CourseDetail>(`/site/courses/${slug}/`)),
  events: (params: ListParams) => (env.useMocks ? mocked((m) => m.events(params)) : get<EventsPage>('/site/events/', { ...params })),
  event: (slug: string) => (env.useMocks ? mocked((m) => m.event(slug)) : get<EventDetail>(`/site/events/${slug}/`)),
  register: (slug: string, body: RegistrationInput) =>
    env.useMocks ? mocked((m) => m.submit()) : post<SubmitResult>(`/site/events/${slug}/register/`, body),
  achievements: (params: ListParams) =>
    env.useMocks ? mocked((m) => m.achievements(params)) : get<AchievementsPage>('/site/achievements/', { ...params }),
  achievement: (slug: string) =>
    env.useMocks ? mocked((m) => m.achievement(slug)) : get<AchievementDetail>(`/site/achievements/${slug}/`),
  team: () => (env.useMocks ? mocked((m) => m.team()) : get<{ results: TeamMember[] }>('/site/team/')),
  testimonials: (params: ListParams) =>
    env.useMocks ? mocked((m) => m.testimonials(params)) : get<TestimonialsPage>('/site/testimonials/', { ...params }),
  lead: (body: LeadInput) => (env.useMocks ? mocked((m) => m.submit()) : post<SubmitResult>('/site/leads/', body)),
  preview: (token: string) => get<PreviewData>(`/site/preview/${encodeURIComponent(token)}/`),
}

export const newsApi = {
  list: (params: ListParams) => (env.useMocks ? mocked((m) => m.news(params)) : get<NewsPage>('/news/', { ...params })),
  article: (slug: string) => (env.useMocks ? mocked((m) => m.article(slug)) : get<NewsArticle>(`/news/${slug}/`)),
}

export const projectsApi = {
  list: (params: ListParams) =>
    env.useMocks ? mocked((m) => m.projects(params)) : get<ProjectsPage>('/projects/', { ...params }),
  detail: (key: string) => (env.useMocks ? mocked((m) => m.project(key)) : get<ProjectDetail>(`/projects/${key}/`)),
}

/** The existing public careers API (apps.recruitment) — only the number of open vacancies is used. */
export const careersApi = {
  vacancies: () =>
    env.useMocks ? mocked((m) => m.vacancies()) : get<VacanciesPage>('/careers/vacancies/', { page_size: 1 }),
}
