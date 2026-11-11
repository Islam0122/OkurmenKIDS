import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Eye, EyeOff } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, useSiteInvalidate, useSiteMeta, type Row } from './api'
import { ImageInput } from './fields'
import { ResourcePage } from './ResourcePage'

type Tab = 'main' | 'sections' | 'contacts' | 'stats' | 'branches' | 'banners'
const TABS = [
  { key: 'main', label: 'Главный экран и тексты' },
  { key: 'sections', label: 'Блоки' },
  { key: 'contacts', label: 'Контакты' },
  { key: 'stats', label: 'Показатели' },
  { key: 'branches', label: 'Филиалы' },
  { key: 'banners', label: 'Баннеры' },
] as const

const TEXT = (name: string, label: string, opts: { area?: boolean; hint?: string; i18n?: boolean } = {}) => ({ name, label, ...opts })
const MAIN = [
  TEXT('hero_title', 'Заголовок главного экрана', { i18n: true }),
  TEXT('hero_subtitle', 'Текст под заголовком', { area: true, i18n: true }),
  TEXT('intro_video_url', 'Видео об академии (YouTube / Vimeo)'),
  TEXT('primary_cta_label', 'Кнопка 1 — текст', { hint: 'Пусто — «Записать ребёнка»' }),
  TEXT('primary_cta_url', 'Кнопка 1 — ссылка', { hint: 'Пусто — форма записи' }),
  TEXT('secondary_cta_label', 'Кнопка 2 — текст', { hint: 'Пусто — «Посмотреть курсы»' }),
  TEXT('secondary_cta_url', 'Кнопка 2 — ссылка', { hint: 'Пусто — /courses' }),
  TEXT('about_story', 'История академии («Об академии»)', { area: true, i18n: true }),
  TEXT('mission', 'Миссия', { area: true, i18n: true }),
  TEXT('vision', 'Видение', { area: true, i18n: true }),
]
const CONTACTS = [
  TEXT('phone', 'Телефон'), TEXT('whatsapp', 'WhatsApp (номер)'), TEXT('telegram', 'Telegram (@имя или ссылка)'),
  TEXT('instagram', 'Instagram (@имя или ссылка)'), TEXT('email', 'E-mail'), TEXT('working_hours', 'Часы работы'),
]

/** /marketing/site/home — главная страница сайта и общие настройки. */
export function HomepagePage() {
  const [tab, setTab] = useState<Tab>('main')
  return (
    <div className="space-y-4">
      <PageHeader title="Главная страница" description="Что видит посетитель первым: заголовок, фото, видео, порядок блоков, избранные проекты и новости, контакты." />
      <Tabs aria-label="Разделы главной страницы" items={TABS} value={tab} onChange={setTab} />
      {tab === 'main' ? <SettingsForm fields={MAIN} withMedia /> : null}
      {tab === 'contacts' ? <SettingsForm fields={CONTACTS} /> : null}
      {tab === 'sections' ? <Sections /> : null}
      {tab === 'stats' ? <ResourcePage resource="stats" /> : null}
      {tab === 'branches' ? <ResourcePage resource="branches" /> : null}
      {tab === 'banners' ? <ResourcePage resource="banners" /> : null}
    </div>
  )
}

function SettingsForm({ fields, withMedia }: { fields: ReturnType<typeof TEXT>[]; withMedia?: boolean }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const meta = useSiteMeta()
  const settings = useQuery({ queryKey: ['site-cms', 'settings'], queryFn: siteCmsApi.settings })
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [image, setImage] = useState<File | null | undefined>(undefined)
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (settings.data) setValues(settings.data) }, [settings.data])
  if (settings.isPending || !settings.data) return <LoadingState />

  const set = (name: string, v: unknown) => setValues((p) => ({ ...p, [name]: v }))
  const save = async () => {
    setSaving(true)
    try {
      const body: Record<string, unknown> = {}
      for (const f of fields) {
        body[f.name] = values[f.name] ?? ''
        if (f.i18n) for (const l of ['ky', 'en']) body[`${f.name}_${l}`] = values[`${f.name}_${l}`] ?? ''
      }
      if (withMedia) {
        if (image !== undefined) body.hero_image = image
        body.featured_projects = values.featured_projects ?? []
        body.featured_news = values.featured_news ?? []
      }
      if (body.hero_image instanceof File || body.hero_image === null) {
        // multipart: send lists via JSON afterwards (FormData can't send an empty list)
        const { featured_projects, featured_news, ...rest } = body
        await siteCmsApi.saveSettings(rest)
        await siteCmsApi.saveSettings({ featured_projects, featured_news })
      } else {
        await siteCmsApi.saveSettings(body)
      }
      setImage(undefined)
      await invalidate()
      showToast('Сохранено', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setSaving(false)
    }
  }
  const lms = meta.data?.lms
  const toggle = (name: string, id: number) => {
    const list = (values[name] as number[] | undefined) ?? []
    set(name, list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  return (
    <div className="space-y-5 rounded-xl border border-border bg-surface p-4 sm:p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.name} className={cn(f.area && 'sm:col-span-2')}>
            <label htmlFor={`s-${f.name}`} className="field-label">{f.label}</label>
            {f.area ? <Textarea id={`s-${f.name}`} rows={4} value={String(values[f.name] ?? '')} onChange={(e) => set(f.name, e.target.value)} />
              : <Input id={`s-${f.name}`} value={String(values[f.name] ?? '')} onChange={(e) => set(f.name, e.target.value)} />}
            {f.hint ? <p className="mt-1 text-xs text-ink-muted">{f.hint}</p> : null}
            {f.i18n ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {(['ky', 'en'] as const).map((l) => (
                  <Input key={l} aria-label={`${f.label} (${l})`} placeholder={l === 'ky' ? 'Кыргызча' : 'English'} value={String(values[`${f.name}_${l}`] ?? '')} onChange={(e) => set(`${f.name}_${l}`, e.target.value)} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {withMedia ? (
          <div className="sm:col-span-2">
            <span className="field-label">Фото главного экрана</span>
            <ImageInput id="s-hero-image" current={(settings.data.hero_image as string | null) ?? null} value={image} onChange={setImage} />
            <p className="mt-1 text-xs text-ink-muted">Реальное фото академии или студентов (с согласия). Пусто — фирменная иллюстрация.</p>
          </div>
        ) : null}
      </div>
      {withMedia && lms ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Picker title="Проекты на главной" hint="Только опубликованные тренерами. Ничего не выбрано — последние." items={lms.projects.map((p) => ({ id: p.id, label: p.title }))}
            selected={(values.featured_projects as number[]) ?? []} onToggle={(id) => toggle('featured_projects', id)} />
          <Picker title="Новости на главной" hint="Ничего не выбрано — последние." items={lms.news.map((n) => ({ id: n.id, label: n.title }))}
            selected={(values.featured_news as number[]) ?? []} onToggle={(id) => toggle('featured_news', id)} />
        </div>
      ) : null}
      <div className="flex justify-end border-t border-border pt-4"><Button isLoading={saving} onClick={save}>Сохранить</Button></div>
    </div>
  )
}

function Picker({ title, hint, items, selected, onToggle }: { title: string; hint: string; items: { id: number; label: string }[]; selected: number[]; onToggle: (id: number) => void }) {
  return (
    <fieldset className="rounded-lg border border-border p-3">
      <legend className="px-1 text-sm font-medium text-ink">{title} <span className="text-ink-muted">({selected.length})</span></legend>
      <p className="mb-2 text-xs text-ink-muted">{hint}</p>
      <ul className="max-h-60 space-y-1 overflow-y-auto">
        {items.length ? items.map((item) => (
          <li key={item.id}>
            <label className="flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-surface-hover">
              <input type="checkbox" className="size-4 accent-brand-600" checked={selected.includes(item.id)} onChange={() => onToggle(item.id)} />
              <span className="truncate">{item.label}</span>
            </label>
          </li>
        )) : <li className="text-sm text-ink-muted">Нет опубликованных материалов.</li>}
      </ul>
    </fieldset>
  )
}

function Sections() {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const query = useQuery({ queryKey: ['site-cms', 'sections'], queryFn: siteCmsApi.sections })
  const [rows, setRows] = useState<Row[]>([])
  useEffect(() => { if (query.data) setRows(query.data) }, [query.data])
  if (query.isPending) return <LoadingState />
  const act = async (task: () => Promise<unknown>) => {
    try {
      await task()
      await invalidate()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  const move = (index: number, delta: number) => {
    const next = [...rows]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    setRows(next)
    act(() => siteCmsApi.reorderSections(next.map((r) => String(r.key))))
  }
  return (
    <div className="rounded-xl border border-border bg-surface">
      <p className="border-b border-border px-4 py-3 text-sm text-ink-secondary">Порядок блоков главной страницы после главного экрана. Пустые блоки (например, нет отзывов) сайт не показывает сам.</p>
      <ol className="divide-y divide-border">
        {rows.map((row, i) => (
          <li key={row.id} className={cn('flex items-center gap-2 px-3 py-2.5 sm:px-4', !row.is_visible && 'opacity-60')}>
            <span className="w-6 text-sm text-ink-muted">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-ink">{String(row.label)}</span>
              <Input aria-label="Свой заголовок" defaultValue={String(row.title ?? '')} placeholder="Свой заголовок (необязательно)" className="mt-1 h-8 max-w-sm text-xs"
                onBlur={(e) => e.target.value !== row.title && act(() => siteCmsApi.saveSection(row.id, { title: e.target.value }))} />
            </span>
            <Button variant="ghost" size="sm" aria-label="Выше" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="size-4" aria-hidden /></Button>
            <Button variant="ghost" size="sm" aria-label="Ниже" disabled={i === rows.length - 1} onClick={() => move(i, 1)}><ArrowDown className="size-4" aria-hidden /></Button>
            <Button variant="ghost" size="sm" aria-label={row.is_visible ? 'Скрыть' : 'Показать'} onClick={() => act(() => siteCmsApi.saveSection(row.id, { is_visible: !row.is_visible }))}>
              {row.is_visible ? <Eye className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}
            </Button>
          </li>
        ))}
      </ol>
    </div>
  )
}
