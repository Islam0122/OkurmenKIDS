import { useQuery } from '@tanstack/react-query'
import { Award, BookOpen, CalendarDays, ExternalLink, Home, Image, Inbox, MessageSquareQuote, Newspaper, Users, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { extractErrorMessage } from '@/lib/apiError'

import { siteCmsApi, useSiteMeta } from './api'
import { STATE_LABEL } from './schema'

const TILES: { to: string; key: string; label: string; icon: LucideIcon }[] = [
  { to: 'courses', key: 'courses', label: 'Курсы', icon: BookOpen },
  { to: 'news', key: 'news', label: 'Новости', icon: Newspaper },
  { to: 'events', key: 'events', label: 'Мероприятия', icon: CalendarDays },
  { to: 'achievements', key: 'achievements', label: 'Достижения', icon: Award },
  { to: 'team', key: 'team', label: 'Команда', icon: Users },
  { to: 'testimonials', key: 'testimonials', label: 'Отзывы', icon: MessageSquareQuote },
]

/** /marketing/site — всё, что видят посетители публичного сайта, в одном месте. */
export function SiteOverviewPage() {
  const meta = useSiteMeta()
  const overview = useQuery({ queryKey: ['site-cms', 'overview'], queryFn: siteCmsApi.overview })
  const data = overview.data
  const num = (key: string) => (typeof data?.[key] === 'number' ? (data[key] as number) : 0)
  const site = meta.data?.public_site_url

  return (
    <div className="space-y-5">
      <PageHeader title="Сайт" description="Публичный сайт Okurmen Kids Digital: курсы, новости, мероприятия, достижения, команда, отзывы, главная страница и заявки."
        actions={site ? <a href={site} target="_blank" rel="noreferrer" className="inline-flex h-10 items-center gap-2 rounded-lg border border-brand-200 px-4 text-sm font-medium text-brand-700 hover:bg-brand-50">Открыть сайт <ExternalLink className="size-4" aria-hidden /></a> : undefined} />
      {overview.isPending ? <LoadingState /> : overview.isError ? <ErrorState message={extractErrorMessage(overview.error)} onRetry={() => overview.refetch()} /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Link to="leads" className="rounded-xl border border-border bg-surface p-4 hover:border-brand-200">
              <Inbox className="size-5 text-brand-600" aria-hidden />
              <p className="mt-2 text-2xl font-semibold text-ink">{num('leads_new')}</p>
              <p className="text-sm text-ink-secondary">новых заявок на обучение</p>
            </Link>
            <Link to="leads?tab=registrations" className="rounded-xl border border-border bg-surface p-4 hover:border-brand-200">
              <CalendarDays className="size-5 text-brand-600" aria-hidden />
              <p className="mt-2 text-2xl font-semibold text-ink">{num('registrations_new')}</p>
              <p className="text-sm text-ink-secondary">новых регистраций на мероприятия</p>
            </Link>
            <Link to="media" className="rounded-xl border border-border bg-surface p-4 hover:border-brand-200">
              <Image className="size-5 text-brand-600" aria-hidden />
              <p className="mt-2 text-2xl font-semibold text-ink">{num('media')}</p>
              <p className="text-sm text-ink-secondary">файлов в медиатеке</p>
            </Link>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {TILES.map((tile) => {
              const counts = (data?.[tile.key] ?? {}) as Record<string, number>
              return (
                <li key={tile.key}>
                  <Link to={tile.to} className="block h-full rounded-xl border border-border bg-surface p-4 hover:border-brand-200">
                    <div className="flex items-center gap-2 font-medium text-ink"><tile.icon className="size-5 text-brand-600" aria-hidden />{tile.label}</div>
                    <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                      {Object.entries(counts).map(([state, n]) => (
                        <div key={state} className="flex gap-1"><dt className="text-ink-secondary">{STATE_LABEL[state]}:</dt><dd className={state === 'review' && n ? 'font-semibold text-warning' : 'font-medium text-ink'}>{n}</dd></div>
                      ))}
                    </dl>
                  </Link>
                </li>
              )
            })}
            <li>
              <Link to="home" className="flex h-full flex-col justify-center rounded-xl border border-dashed border-brand-200 bg-brand-50 p-4 hover:border-brand-500">
                <div className="flex items-center gap-2 font-medium text-brand-700"><Home className="size-5" aria-hidden />Главная страница</div>
                <p className="mt-1 text-sm text-ink-secondary">Заголовок, фото, видео, блоки и их порядок, контакты, филиалы, баннеры.</p>
              </Link>
            </li>
          </ul>
        </>
      )}
    </div>
  )
}
