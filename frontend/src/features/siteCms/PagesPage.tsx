import { Award, BookOpen, CalendarDays, ExternalLink, FolderKanban, Home, Info, MessageSquareQuote, Newspaper, Pencil, Phone, Users, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useSiteMeta, useSiteOverview, type Overview } from './api'
import { CMS_BASE, CmsPage, linkButton, Skeleton } from './ui'

interface SitePage {
  title: string
  path: string
  to: string
  icon: LucideIcon
  description: string
  stat?: (o: Overview) => string
}

const n = (v: number | null | undefined) => (typeof v === 'number' ? String(v) : '—')
const live = (c: Overview['news']) => (c ? `${c.published} на сайте · ${c.draft + c.review} в черновиках` : '')

/** Страницы публичного сайта: каждая ведёт туда, где редактируется её контент. */
const PAGES: SitePage[] = [
  { title: 'Главная', path: '/', to: 'pages/home', icon: Home, description: 'Главный экран, кнопки, видео, порядок блоков, избранные проекты и новости, цифры академии.' },
  { title: 'Об академии', path: '/about', to: 'pages/about', icon: Info, description: 'История, миссия и видение академии.' },
  { title: 'Курсы', path: '/courses', to: 'courses', icon: BookOpen, description: 'Страницы курсов: программа, возраст, формат.', stat: (o) => live(o.courses) },
  { title: 'Новости', path: '/news', to: 'news', icon: Newspaper, description: 'Новости академии с фото.', stat: (o) => live(o.news) },
  { title: 'События', path: '/events', to: 'events', icon: CalendarDays, description: 'Мероприятия с регистрацией и галереей.', stat: (o) => `${n(o.upcoming_events)} предстоящих · ${n(o.events?.draft)} в черновиках` },
  { title: 'Достижения', path: '/achievements', to: 'achievements', icon: Award, description: 'Победы, награды, сертификаты, партнёрства.', stat: (o) => live(o.achievements) },
  { title: 'Проекты учеников', path: '/projects', to: 'projects', icon: FolderKanban, description: 'Работы студентов (добавляют тренеры) и выбор для главной.', stat: (o) => `${n(o.projects)} опубликовано · ${n(o.featured_projects)} на главной` },
  { title: 'Отзывы', path: '/testimonials', to: 'testimonials', icon: MessageSquareQuote, description: 'Отзывы родителей и студентов — только с согласия.', stat: (o) => live(o.testimonials) },
  { title: 'Команда', path: '/team', to: 'team', icon: Users, description: 'Публичные профили тренеров и сотрудников.', stat: (o) => live(o.team) },
  { title: 'Контакты', path: '/contacts', to: 'contacts', icon: Phone, description: 'Телефон, мессенджеры, часы работы и филиалы.' },
]

export function PagesPage() {
  const meta = useSiteMeta()
  const overview = useSiteOverview()
  const site = meta.data?.public_site_url?.replace(/\/$/, '')
  return (
    <CmsPage title="Страницы сайта" description="Выберите страницу — откроется место, где редактируется её содержимое.">
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {PAGES.map((page) => (
          <li key={page.path} className="flex flex-col rounded-2xl border border-border bg-surface p-4 shadow-[0_1px_2px_rgba(28,21,51,0.04)] transition hover:border-brand-200">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><page.icon className="size-5" aria-hidden /></span>
              <div className="min-w-0">
                <h2 className="font-semibold text-ink">{page.title}</h2>
                <p className="font-mono text-xs text-ink-muted">{page.path}</p>
              </div>
            </div>
            <p className="mt-3 flex-1 text-sm text-ink-secondary">{page.description}</p>
            {page.stat ? (
              <p className="mt-2 text-xs font-medium text-ink-secondary">{overview.isPending ? <Skeleton className="h-3 w-40" /> : overview.data ? page.stat(overview.data) : null}</p>
            ) : null}
            <div className="mt-4 flex gap-2">
              <Link to={`${CMS_BASE}/${page.to}`} className={linkButton('primary', 'sm')}><Pencil className="size-3.5" aria-hidden />Редактировать</Link>
              {site ? <a href={`${site}${page.path}`} target="_blank" rel="noreferrer" className={linkButton('ghost', 'sm')}>Открыть<ExternalLink className="size-3.5" aria-hidden /></a> : null}
            </div>
          </li>
        ))}
      </ul>
    </CmsPage>
  )
}
