import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ExternalLink, Eye, EyeOff, GripVertical } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import { Input } from '@/components/ui/Input'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, useSiteInvalidate, useSiteMeta, useSiteSettings, type Row } from './api'
import { ContentListPage } from './ContentListPage'
import { SettingsForm, type SettingField } from './SettingsForm'
import { CMS_BASE, CmsPage, linkButton, ListSkeleton, Panel } from './ui'

const HERO: SettingField[] = [
  { name: 'hero_title', label: 'Заголовок главного экрана', i18n: true, max: 160, wide: true },
  { name: 'hero_subtitle', label: 'Текст под заголовком', area: true, i18n: true },
  { name: 'hero_image', label: 'Фото главного экрана', image: true, hint: 'Реальное фото академии или студентов (с согласия). Пусто — фирменная иллюстрация.' },
  { name: 'primary_cta_label', label: 'Кнопка 1 — текст', placeholder: 'Записать ребёнка' },
  { name: 'primary_cta_url', label: 'Кнопка 1 — ссылка', placeholder: 'Пусто — форма записи' },
  { name: 'secondary_cta_label', label: 'Кнопка 2 — текст', placeholder: 'Посмотреть курсы' },
  { name: 'secondary_cta_url', label: 'Кнопка 2 — ссылка', placeholder: '/courses' },
  { name: 'intro_video_url', label: 'Видео об академии (YouTube / Vimeo)', type: 'url', wide: true, placeholder: 'https://youtu.be/…' },
]

const ABOUT: SettingField[] = [
  { name: 'about_story', label: 'История академии', area: true, i18n: true },
  { name: 'mission', label: 'Миссия', area: true, i18n: true },
  { name: 'vision', label: 'Видение', area: true, i18n: true },
]

type Tab = 'hero' | 'sections' | 'featured' | 'stats'
const TABS: { key: Tab; label: string }[] = [
  { key: 'hero', label: 'Главный экран' },
  { key: 'sections', label: 'Блоки страницы' },
  { key: 'featured', label: 'Избранное' },
  { key: 'stats', label: 'Цифры академии' },
]

/** /marketing/site/pages/home — главная страница сайта (часть раздела «Страницы сайта»). */
export function HomepagePage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.key === params.get('tab'))?.key ?? 'hero') as Tab
  const site = useSiteMeta().data?.public_site_url
  return (
    <CmsPage title="Главная страница" back={{ to: `${CMS_BASE}/pages`, label: 'Страницы сайта' }}
      description="Что видит посетитель первым: заголовок, фото, кнопки, порядок блоков и избранные материалы."
      actions={site ? <a href={site} target="_blank" rel="noreferrer" className={linkButton('secondary')}><ExternalLink className="size-4" aria-hidden />Открыть главную</a> : undefined}>
      <div role="tablist" aria-label="Разделы главной страницы" className="scroll-x -mx-4 flex gap-1 border-b border-border px-4 sm:mx-0 sm:px-0">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setParams(t.key === 'hero' ? {} : { tab: t.key }, { replace: true })}
            className={cn('-mb-px h-11 shrink-0 border-b-2 px-3 text-sm font-medium', tab === t.key ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-secondary hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'hero' ? <SettingsForm title="Главный экран" description="Заголовок, текст, фото и кнопки первого экрана" fields={HERO} /> : null}
      {tab === 'sections' ? <Sections /> : null}
      {tab === 'featured' ? <Featured /> : null}
      {tab === 'stats' ? <ContentListPage resource="stats" embedded /> : null}
    </CmsPage>
  )
}

/** /marketing/site/pages/about — «Об академии». */
export function AboutPage() {
  return (
    <CmsPage title="Об академии" back={{ to: `${CMS_BASE}/pages`, label: 'Страницы сайта' }} description="Тексты страницы /about на трёх языках. Цифры академии — на вкладке «Цифры академии» главной.">
      <SettingsForm title="Тексты страницы" fields={ABOUT} />
    </CmsPage>
  )
}

function Featured() {
  const meta = useSiteMeta()
  const settings = useSiteSettings()
  const [news, setNews] = useState<number[]>([])
  const initial = (settings.data?.featured_news as number[] | undefined) ?? []
  useEffect(() => { setNews(initial) }, [settings.data]) // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(news) !== JSON.stringify(initial)
  const items = meta.data?.lms?.news ?? []
  const toggle = (id: number) => setNews((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]))
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <SettingsForm title="Новости на главной" description="Ничего не выбрано — три последние" fields={[]}
        extra={{ values: { featured_news: news }, dirty, reset: () => setNews(initial) }}>
        {() => (
          <ul className="max-h-80 space-y-1 overflow-y-auto">
            {items.length ? items.map((item) => (
              <li key={item.id}>
                <label className="flex min-h-10 items-center gap-3 rounded-lg px-2 py-1.5 text-sm hover:bg-surface-hover">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={news.includes(item.id)} onChange={() => toggle(item.id)} />
                  <span className="min-w-0 flex-1 truncate">{item.title}</span>
                  <span className="text-xs text-ink-muted">{new Date(item.published_at).toLocaleDateString('ru-RU')}</span>
                </label>
              </li>
            )) : <li className="text-sm text-ink-muted">Нет опубликованных новостей.</li>}
          </ul>
        )}
      </SettingsForm>
      <Panel title="Проекты учеников на главной" description="Отметки ставятся в разделе «Проекты учеников»">
        <p className="text-sm text-ink-secondary">Проекты добавляют тренеры в LMS. Маркетинг выбирает, какие из опубликованных показать на главной; ничего не выбрано — последние.</p>
        <Link to={`${CMS_BASE}/projects`} className={cn(linkButton('primary'), 'mt-4')}>Выбрать проекты</Link>
      </Panel>
    </div>
  )
}

function Sections() {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const query = useQuery({ queryKey: ['site-cms', 'sections'], queryFn: siteCmsApi.sections })
  const [rows, setRows] = useState<Row[]>([])
  const [drag, setDrag] = useState<number | null>(null)
  useEffect(() => { if (query.data) setRows(query.data) }, [query.data])
  if (query.isPending) return <ListSkeleton rows={8} thumb={false} />
  const act = async (task: () => Promise<unknown>, ok?: string) => {
    try {
      await task()
      await invalidate()
      if (ok) showToast(ok, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  const reorder = (next: Row[]) => {
    setRows(next)
    act(() => siteCmsApi.reorderSections(next.map((r) => String(r.key))), 'Порядок блоков сохранён')
  }
  const move = (index: number, delta: number) => {
    const next = [...rows]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    reorder(next)
  }
  return (
    <Panel title="Блоки главной страницы" description="Порядок после главного экрана. Перетащите или используйте стрелки; пустые блоки сайт скрывает сам." bodyClassName="p-0">
      <ol className="divide-y divide-border">
        {rows.map((row, i) => (
          <li key={row.id} draggable onDragStart={() => setDrag(i)} onDragOver={(e) => e.preventDefault()}
            onDrop={() => { if (drag === null || drag === i) return; const next = [...rows]; const [it] = next.splice(drag, 1); next.splice(i, 0, it); setDrag(null); reorder(next) }}
            className={cn('flex flex-wrap items-center gap-2 px-3 py-3 sm:flex-nowrap sm:px-5', !row.is_visible && 'bg-surface-muted/60', drag === i && 'opacity-50')}>
            <GripVertical className="hidden size-4 shrink-0 cursor-grab text-ink-muted sm:block" aria-hidden />
            <span className="w-6 text-sm text-ink-muted tabular-nums">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className={cn('block font-medium', row.is_visible ? 'text-ink' : 'text-ink-muted line-through')}>{String(row.label)}</span>
              <Input aria-label={`Свой заголовок блока «${String(row.label)}»`} defaultValue={String(row.title ?? '')} placeholder="Свой заголовок (необязательно)" className="mt-1 h-9 max-w-sm text-sm"
                onBlur={(e) => e.target.value !== (row.title ?? '') && act(() => siteCmsApi.saveSection(row.id, { title: e.target.value }), 'Заголовок сохранён')} />
            </span>
            <div className="flex items-center gap-1">
              <button type="button" className="grid size-10 place-items-center rounded-lg text-ink-secondary hover:bg-surface-hover disabled:opacity-30" aria-label="Выше" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="size-4" aria-hidden /></button>
              <button type="button" className="grid size-10 place-items-center rounded-lg text-ink-secondary hover:bg-surface-hover disabled:opacity-30" aria-label="Ниже" disabled={i === rows.length - 1} onClick={() => move(i, 1)}><ArrowDown className="size-4" aria-hidden /></button>
              <button type="button" aria-pressed={Boolean(row.is_visible)} aria-label={row.is_visible ? 'Скрыть блок' : 'Показать блок'}
                onClick={() => act(() => siteCmsApi.saveSection(row.id, { is_visible: !row.is_visible }), row.is_visible ? 'Блок скрыт' : 'Блок показан')}
                className={cn('inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium', row.is_visible ? 'text-emerald-700 hover:bg-emerald-50' : 'text-ink-muted hover:bg-surface-hover')}>
                {row.is_visible ? <Eye className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}
                <span className="hidden sm:inline">{row.is_visible ? 'Показан' : 'Скрыт'}</span>
              </button>
            </div>
          </li>
        ))}
      </ol>
    </Panel>
  )
}
