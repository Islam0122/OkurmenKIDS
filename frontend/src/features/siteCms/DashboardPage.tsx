import { useState } from 'react'
import {
  Award, CalendarDays, CheckCircle2, ChevronRight, ExternalLink, Eye, FileClock, FolderKanban, ImagePlus, Inbox, MessageSquareQuote, Newspaper,
  Plus, type LucideIcon,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { ErrorState } from '@/components/ui/ErrorState'
import { Modal } from '@/components/ui/Modal'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { useSiteMeta, useSiteOverview, type ContentSummary, type Overview } from './api'
import { ISSUE_LABEL, RESOURCES } from './schema'
import { CardsSkeleton, CMS_BASE, CmsPage, Dropdown, editorPath, linkButton, ListSkeleton, Panel, relativeTime, StatusBadge } from './ui'

const CONTENT = ['news', 'events', 'achievements', 'testimonials', 'team', 'courses'] as const
const sum = (o: Overview | undefined, states: string[]) =>
  o ? CONTENT.reduce((n, key) => n + states.reduce((m, s) => m + (o[key]?.[s as keyof Overview['news']] ?? 0), 0), 0) : 0
const live = (o: Overview | undefined, key: (typeof CONTENT)[number]) =>
  o ? (['draft', 'review', 'scheduled', 'published'] as const).reduce((n, s) => n + (o[key]?.[s] ?? 0), 0) : 0

const QUICK: { label: string; to: string; icon: LucideIcon }[] = [
  { label: 'Добавить новость', to: editorPath('news'), icon: Newspaper },
  { label: 'Добавить событие', to: editorPath('events'), icon: CalendarDays },
  { label: 'Проект на главную', to: `${CMS_BASE}/projects`, icon: FolderKanban },
  { label: 'Добавить достижение', to: editorPath('achievements'), icon: Award },
  { label: 'Добавить отзыв', to: editorPath('testimonials'), icon: MessageSquareQuote },
  { label: 'Загрузить фотографии', to: `${CMS_BASE}/media?upload=1`, icon: ImagePlus },
]

/** /marketing/site — обзор сайта: цифры, быстрые действия, последние изменения, черновики, что заполнить. */
export function DashboardPage() {
  const navigate = useNavigate()
  const meta = useSiteMeta()
  const overview = useSiteOverview()
  const data = overview.data
  const site = meta.data?.public_site_url
  const approval = meta.data?.permissions.require_approval
  const [previewList, setPreviewList] = useState(false)

  const create = (['news', 'events', 'achievements', 'testimonials', 'team', 'courses', 'banners'] as const).map((key) => ({
    key, label: RESOURCES[key].single, onClick: () => navigate(editorPath(key)),
  }))

  return (
    <CmsPage
      title="Управление сайтом"
      eyebrow={
        <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1',
          site ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-warning-soft text-warning ring-warning/20')}>
          <span className={cn('size-1.5 rounded-full', site ? 'bg-emerald-500' : 'bg-warning')} aria-hidden />
          {site ? 'Сайт работает' : 'Адрес сайта не настроен'}
          <span className="text-ink-muted">· {approval ? 'публикация после согласования' : 'публикация сразу'}</span>
        </span>
      }
      description="Контент, медиа и заявки публичного сайта Okurmen Kids Digital в одном месте."
      actions={
        <>
          {site ? <a href={site} target="_blank" rel="noreferrer" className={linkButton('ghost')}><ExternalLink className="size-4" aria-hidden />Открыть сайт</a> : null}
          <button type="button" className={linkButton('secondary')} onClick={() => setPreviewList(true)}><Eye className="size-4" aria-hidden />Предпросмотр</button>
          <CreateMenu items={create} />
        </>
      }
    >
      {overview.isPending ? <CardsSkeleton count={6} className="lg:grid-cols-6" /> : overview.isError ? (
        <ErrorState message={extractErrorMessage(overview.error)} onRetry={() => overview.refetch()} />
      ) : (
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Kpi to={`${CMS_BASE}/pages`} icon={CheckCircle2} value={sum(data, ['published'])} label="Опубликовано" note={`запланировано: ${sum(data, ['scheduled'])}`} />
          <Kpi to={`${CMS_BASE}/news?status=draft`} icon={FileClock} value={sum(data, ['draft', 'review'])} label="Черновики" note={sum(data, ['review']) ? `на согласовании: ${sum(data, ['review'])}` : 'в работе'} />
          <Kpi to={`${CMS_BASE}/projects`} icon={FolderKanban} value={data?.projects ?? 0} label="Проекты" note={`на главной: ${data?.featured_projects ?? 0}`} />
          <Kpi to={`${CMS_BASE}/events`} icon={CalendarDays} value={live(data, 'events')} label="События" note={`предстоящих: ${data?.upcoming_events ?? 0}`} />
          <Kpi to={`${CMS_BASE}/news`} icon={Newspaper} value={live(data, 'news')} label="Новости" note={`на сайте: ${data?.news.published ?? 0}`} />
          <Kpi to={`${CMS_BASE}/leads`} icon={Inbox} value={data?.leads_new ?? 0} label="Новые заявки" note={`регистраций: ${data?.registrations_new ?? 0}`} accent />
        </ul>
      )}

      <section aria-labelledby="quick-actions">
        <h2 id="quick-actions" className="sr-only">Быстрые действия</h2>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          {QUICK.map((q) => (
            <li key={q.label}>
              <Link to={q.to} className="flex h-full min-h-14 items-center gap-2.5 rounded-xl border border-dashed border-brand-200 bg-surface px-3 py-2.5 text-sm font-medium text-brand-700 transition-colors hover:border-brand-500 hover:bg-brand-50">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600"><q.icon className="size-4" aria-hidden /></span>
                <span className="leading-tight">{q.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Panel title="Последние изменения" className="lg:col-span-2" bodyClassName="p-0">
          {overview.isPending ? <div className="p-4"><ListSkeleton rows={5} /></div> : <ChangesTable rows={data?.recent ?? []} />}
        </Panel>
        <Panel title="Черновики" description="Не опубликованы на сайте" bodyClassName="p-0"
          actions={<Link to={`${CMS_BASE}/news?status=draft`} className="text-xs font-medium text-brand-600 hover:underline">Все</Link>}>
          {overview.isPending ? <div className="p-4"><ListSkeleton rows={4} thumb={false} /></div> : <SummaryList rows={data?.drafts ?? []} empty="Черновиков нет — всё опубликовано." />}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel title="Последние опубликованные" bodyClassName="p-0">
          {overview.isPending ? <div className="p-4"><ListSkeleton rows={4} /></div> : <SummaryList rows={data?.recently_published ?? []} thumbs empty="Пока ничего не опубликовано." />}
        </Panel>
        <Panel title="Требует заполнения" description="Обложка, описание, переводы KG / EN и SEO" bodyClassName="p-0"
          actions={<Link to={`${CMS_BASE}/settings/languages`} className="text-xs font-medium text-brand-600 hover:underline">Переводы</Link>}>
          {overview.isPending ? <div className="p-4"><ListSkeleton rows={4} thumb={false} /></div> : <SummaryList rows={(data?.attention ?? []).slice(0, 8)} issues empty="Всё заполнено. Отличная работа!" />}
        </Panel>
      </div>

      <Modal isOpen={previewList} onClose={() => setPreviewList(false)} title="Предпросмотр" size="lg" icon={<Eye className="size-5 text-brand-600" aria-hidden />}>
        <p className="mb-3 text-sm text-ink-secondary">Выберите материал — откроется редактор с предпросмотром на всех языках. Опубликованный сайт: «Открыть сайт».</p>
        {data?.drafts.length ? <SummaryList rows={data.drafts} preview /> : <p className="py-6 text-center text-sm text-ink-muted">Черновиков нет.</p>}
        {site ? <a href={site} target="_blank" rel="noreferrer" className={cn(linkButton('secondary'), 'mt-4 w-full')}><ExternalLink className="size-4" aria-hidden />Открыть опубликованный сайт</a> : null}
      </Modal>
    </CmsPage>
  )
}

function CreateMenu({ items }: { items: { key: string; label: string; onClick: () => void }[] }) {
  return (
    <Dropdown label="Создать контент" items={items} triggerClassName={linkButton('primary')}
      trigger={<><Plus className="size-4" aria-hidden />Создать контент</>} />
  )
}

function Kpi({ to, icon: Icon, value, label, note, accent }: { to: string; icon: LucideIcon; value: number; label: string; note: string; accent?: boolean }) {
  return (
    <li>
      <Link to={to} className={cn('flex h-full flex-col rounded-2xl border bg-surface p-4 shadow-[0_1px_2px_rgba(28,21,51,0.04)] transition hover:-translate-y-0.5 hover:shadow-md',
        accent && value ? 'border-cms-gold/60 bg-cms-gold-soft' : 'border-border')}>
        <span className={cn('grid size-9 place-items-center rounded-xl', accent && value ? 'bg-cms-gold text-brand-700' : 'bg-brand-50 text-brand-600')}>
          <Icon className="size-[18px]" aria-hidden />
        </span>
        <span className="mt-3 font-display text-2xl font-bold text-ink tabular-nums">{value}</span>
        <span className="text-sm font-medium text-ink">{label}</span>
        <span className="mt-0.5 text-xs text-ink-muted">{note}</span>
      </Link>
    </li>
  )
}

function ChangesTable({ rows }: { rows: ContentSummary[] }) {
  if (!rows.length) return <p className="px-5 py-10 text-center text-sm text-ink-muted">Изменений пока нет. Начните с «Создать контент».</p>
  return (
    <>
      <table className="hidden w-full table-fixed text-sm md:table">
        <thead>
          <tr className="border-b border-border text-left text-xs text-ink-muted">
            <th className="px-5 py-2 font-medium">Материал</th>
            <th className="w-28 px-3 py-2 font-medium">Раздел</th>
            <th className="w-36 px-3 py-2 font-medium">Статус</th>
            <th className="w-32 px-5 py-2 text-right font-medium">Изменено</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={`${row.resource}-${row.id}`} className="hover:bg-surface-hover">
              <td className="px-5 py-2.5">
                <Link to={editorPath(row.resource, row.id)} className="flex items-center gap-3 font-medium text-ink hover:text-brand-600">
                  <Thumb src={row.cover} />
                  <span className="truncate">{row.title}</span>
                </Link>
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap text-ink-secondary">{row.type_label}</td>
              <td className="px-3 py-2.5"><StatusBadge state={row.state} /></td>
              <td className="px-5 py-2.5 text-right whitespace-nowrap text-ink-muted">{relativeTime(row.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="md:hidden"><SummaryList rows={rows} thumbs /></div>
    </>
  )
}

function Thumb({ src }: { src: string | null }) {
  return (
    <span className="grid size-9 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-hover">
      {src ? <img src={src} alt="" className="size-full object-cover" loading="lazy" /> : <Newspaper className="size-4 text-ink-muted" aria-hidden />}
    </span>
  )
}

function SummaryList({ rows, empty, thumbs, issues, preview }: { rows: ContentSummary[]; empty?: string; thumbs?: boolean; issues?: boolean; preview?: boolean }) {
  if (!rows.length) return <p className="px-5 py-8 text-center text-sm text-ink-muted">{empty}</p>
  return (
    <ul className="divide-y divide-border">
      {rows.map((row) => (
        <li key={`${row.resource}-${row.id}`}>
          <Link to={`${editorPath(row.resource, row.id)}${preview ? '?preview=1' : ''}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover sm:px-5">
            {thumbs ? <Thumb src={row.cover} /> : null}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{row.title}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
                {row.type_label} · {relativeTime(row.updated_at)}
                {issues ? row.issues.map((i) => <span key={i} className="rounded-full bg-cms-gold-soft px-1.5 py-0.5 text-[0.6875rem] font-medium text-cms-gold-deep">{ISSUE_LABEL[i]}</span>) : null}
              </span>
            </span>
            {!issues ? <span className="hidden sm:block"><StatusBadge state={row.state} /></span> : null}
            <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
