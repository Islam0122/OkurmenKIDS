import { Navigate, Outlet, type RouteObject } from 'react-router-dom'

import { SiteLayout } from '@/components/layout/SiteLayout'
import { I18nProvider } from '@/i18n'
import { HomePage } from '@/pages/Home/HomePage'
import type { Lang } from '@/types/api'

import { RouteError } from './RouteError'

/** Pages other than Home are code-split: each section loads only when visited. */
const page = (load: () => Promise<object>, name: string): RouteObject['lazy'] =>
  async () => ({ Component: (await load() as Record<string, React.ComponentType>)[name] })

const pages: RouteObject[] = [
  { index: true, element: <HomePage /> },
  { path: 'about', lazy: page(() => import('@/pages/About/AboutPage'), 'AboutPage') },
  { path: 'courses', lazy: page(() => import('@/pages/Courses/CoursesPage'), 'CoursesPage') },
  { path: 'courses/:slug', lazy: page(() => import('@/pages/Courses/CourseDetailPage'), 'CourseDetailPage') },
  { path: 'projects', lazy: page(() => import('@/pages/Projects/ProjectsPage'), 'ProjectsPage') },
  { path: 'projects/:slug', lazy: page(() => import('@/pages/Projects/ProjectDetailPage'), 'ProjectDetailPage') },
  { path: 'achievements', lazy: page(() => import('@/pages/Achievements/AchievementsPage'), 'AchievementsPage') },
  { path: 'achievements/:slug', lazy: page(() => import('@/pages/Achievements/AchievementDetailPage'), 'AchievementDetailPage') },
  { path: 'news', lazy: page(() => import('@/pages/News/NewsPage'), 'NewsPage') },
  { path: 'news/:slug', lazy: page(() => import('@/pages/News/ArticlePage'), 'ArticlePage') },
  { path: 'events', lazy: page(() => import('@/pages/Events/EventsPage'), 'EventsPage') },
  { path: 'events/:slug', lazy: page(() => import('@/pages/Events/EventDetailPage'), 'EventDetailPage') },
  { path: 'team', lazy: page(() => import('@/pages/Team/TeamPage'), 'TeamPage') },
  { path: 'testimonials', lazy: page(() => import('@/pages/Testimonials/TestimonialsPage'), 'TestimonialsPage') },
  { path: 'contacts', lazy: page(() => import('@/pages/Contacts/ContactsPage'), 'ContactsPage') },
  { path: 'enroll', element: <Navigate to="../contacts#enroll" replace /> },
  { path: 'preview/:token', lazy: page(() => import('@/pages/Preview/PreviewPage'), 'PreviewPage') },
  { path: '*', lazy: page(() => import('@/pages/NotFound/NotFoundPage'), 'NotFoundPage') },
]

function LangRoot({ lang }: { lang: Lang }) {
  return (
    <I18nProvider lang={lang}>
      <Outlet />
    </I18nProvider>
  )
}

const branch = (lang: Lang, path: string): RouteObject => ({
  path,
  element: <LangRoot lang={lang} />,
  errorElement: <I18nProvider lang={lang}><RouteError /></I18nProvider>,
  children: [{ element: <SiteLayout />, children: pages }],
})

/** Russian at /, Kyrgyz at /ky/…, English at /en/… — the same pages in each. */
export const routes: RouteObject[] = [branch('ky', '/ky'), branch('en', '/en'), branch('ru', '/')]
