import { CheckCircle2, ChevronRight, ExternalLink, ShieldCheck } from 'lucide-react'
import { Link, Navigate, NavLink, useParams } from 'react-router-dom'

import { ErrorState } from '@/components/ui/ErrorState'
import { cn } from '@/utils/cn'

import { useSiteMeta, useSiteOverview, useSiteSettings, type ContentSummary, type Overview, cmsErrorMessage } from './api'
import { SettingsForm, type SettingField } from './SettingsForm'
import { ISSUE_LABEL, RESOURCES, type ResourceDef } from './schema'
import { CMS_BASE, CmsPage, editorPath, linkButton, ListSkeleton, Panel, StatusBadge } from './ui'

const TABS = [
  { key: 'seo', label: 'SEO' },
  { key: 'metadata', label: 'Метаданные' },
  { key: 'social', label: 'Социальные ссылки' },
  { key: 'languages', label: 'Языки сайта' },
  { key: 'general', label: 'Общие настройки' },
] as const

const SEO: SettingField[] = [
  { name: 'seo_title', label: 'SEO title сайта', i18n: true, max: 70, wide: true, hint: 'Заголовок страниц без своего SEO (главная, списки). Пусто — стандартный.' },
  { name: 'seo_description', label: 'SEO description сайта', i18n: true, area: true, max: 200, hint: '1–2 предложения: кто вы, для кого, где. 140–160 символов.' },
]
const META: SettingField[] = [
  { name: 'og_image', label: 'Картинка для соцсетей (Open Graph)', image: true, hint: 'Показывается, когда ссылкой на сайт делятся в Telegram, WhatsApp, Facebook. 1200 × 630 px.' },
]
const SOCIAL: SettingField[] = [
  { name: 'instagram', label: 'Instagram', placeholder: '@okurmenkids или ссылка' },
  { name: 'telegram', label: 'Telegram', placeholder: '@okurmenkids или ссылка' },
  { name: 'whatsapp', label: 'WhatsApp (номер)', type: 'tel', placeholder: '+996 …' },
  { name: 'facebook', label: 'Facebook', placeholder: 'https://facebook.com/…' },
  { name: 'youtube', label: 'YouTube', placeholder: '@канал или ссылка' },
  { name: 'tiktok', label: 'TikTok', placeholder: '@okurmenkids или ссылка' },
]

const TYPES: ResourceDef['key'][] = ['news', 'events', 'achievements', 'courses', 'team', 'testimonials']

/** /marketing/site/settings/:tab — SEO, метаданные, соцсети, языки, общие. */
export function SettingsPage() {
  const { tab = 'seo' } = useParams()
  if (!TABS.some((t) => t.key === tab)) return <Navigate to={`${CMS_BASE}/settings/seo`} replace />
  const current = TABS.find((t) => t.key === tab)!
  return (
    <CmsPage title={current.label} description="Настройки публичного сайта">
      <nav aria-label="Настройки" className="scroll-x -mx-4 flex gap-1 border-b border-border px-4 sm:mx-0 sm:px-0">
        {TABS.map((t) => (
          <NavLink key={t.key} to={`${CMS_BASE}/settings/${t.key}`}
            className={({ isActive }) => cn('-mb-px inline-flex h-11 shrink-0 items-center border-b-2 px-3 text-sm font-medium', isActive ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-secondary hover:text-ink')}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      {tab === 'seo' ? <SeoTab /> : null}
      {tab === 'metadata' ? <MetadataTab /> : null}
      {tab === 'social' ? <SettingsForm title="Социальные сети" description="Иконки в подвале сайта и ссылки на странице «Контакты». Пустое поле — иконка не показывается." fields={SOCIAL} /> : null}
      {tab === 'languages' ? <LanguagesTab /> : null}
      {tab === 'general' ? <GeneralTab /> : null}
    </CmsPage>
  )
}

function SeoTab() {
  const site = useSiteMeta().data?.public_site_url ?? 'https://okurmenkids.com'
  return (
    <SettingsForm title="SEO сайта" description="Как сайт выглядит в Google и Яндексе" fields={SEO}>
      {(values, _set, lang) => {
        const t = (n: string) => String((lang !== 'ru' && values[`${n}_${lang}`]) || values[n] || '')
        return (
          <div className="rounded-xl border border-border bg-surface-muted p-4" aria-label="Предпросмотр в поиске">
            <p className="text-xs font-medium text-ink-muted">Так сайт будет выглядеть в поиске ({lang.toUpperCase()})</p>
            <p className="mt-2 truncate text-xs text-emerald-700">{site.replace(/^https?:\/\//, '')}{lang !== 'ru' ? `/${lang}` : ''}</p>
            <p className="mt-0.5 text-lg leading-snug text-[#1a0dab]">{t('seo_title') || 'Okurmen Kids — IT-академия для детей'}</p>
            <p className="mt-1 line-clamp-2 text-sm text-ink-secondary">{t('seo_description') || 'Описание сайта для поисковиков.'}</p>
          </div>
        )
      }}
    </SettingsForm>
  )
}

function MetadataTab() {
  const overview = useSiteOverview()
  const settings = useSiteSettings()
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <SettingsForm title="Open Graph" description="Превью ссылки в мессенджерах и соцсетях" fields={META} />
        <Panel title="Превью ссылки" description="Как выглядит ссылка на сайт в Telegram / WhatsApp">
          <div className="max-w-sm overflow-hidden rounded-xl border border-border bg-surface">
            {settings.data?.og_image ? <img src={String(settings.data.og_image)} alt="" className="aspect-[1200/630] w-full object-cover" /> : <div className="grid aspect-[1200/630] place-items-center bg-brand-500 font-display text-lg font-bold text-white">Okurmen Kids</div>}
            <div className="space-y-0.5 p-3">
              <p className="text-sm font-semibold text-ink">{String(settings.data?.seo_title || 'Okurmen Kids')}</p>
              <p className="line-clamp-2 text-xs text-ink-secondary">{String(settings.data?.seo_description || 'IT-академия для детей и подростков')}</p>
            </div>
          </div>
        </Panel>
      </div>
      <Panel title="SEO материалов" description="Сколько материалов заполнили SEO title и description" bodyClassName="p-0">
        <QualityReport query={overview} metric="seo" issues={['seo']} empty="У всех материалов заполнено SEO." />
      </Panel>
    </div>
  )
}

function LanguagesTab() {
  const overview = useSiteOverview()
  return (
    <div className="space-y-5">
      <Panel title="Языки сайта">
        <ul className="grid gap-3 sm:grid-cols-3">
          {[['RU', 'Русский', 'Основной язык. Обязательные поля заполняются на нём.', '/'], ['KG', 'Кыргызча', 'Пустое поле перевода — посетитель увидит русский текст.', '/ky'], ['EN', 'English', 'Пустое поле перевода — посетитель увидит русский текст.', '/en']].map(([code, name, text, path]) => (
            <li key={code} className="rounded-xl border border-border p-3">
              <p className="flex items-center gap-2 font-semibold text-ink"><span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-xs text-brand-700">{code}</span>{name}<CheckCircle2 className="ml-auto size-4 text-emerald-600" aria-label="включён" /></p>
              <p className="mt-1 text-xs text-ink-secondary">{text}</p>
              <p className="mt-1 font-mono text-xs text-ink-muted">{path}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-ink-muted">Переводы заполняются в редакторе каждого материала — переключатель RU / KG / EN над текстом.</p>
      </Panel>
      <Panel title="Полнота переводов" bodyClassName="p-0">
        <QualityReport query={overview} metric="lang" issues={['ky', 'en']} empty="Все материалы переведены на KG и EN." />
      </Panel>
    </div>
  )
}

/** Coverage table + the materials to fix, in every state of the overview request. */
function QualityReport({ query, metric, issues, empty }: { query: ReturnType<typeof useSiteOverview>; metric: 'seo' | 'lang'; issues: string[]; empty: string }) {
  if (query.isPending) return <div className="p-4"><ListSkeleton rows={4} thumb={false} /></div>
  if (query.isError) return <ErrorState message={cmsErrorMessage(query.error)} onRetry={() => query.refetch()} />
  const { coverage, attention } = query.data
  if (!coverage || !attention) {
    return <p className="px-5 py-8 text-center text-sm text-ink-muted">Сервер пока не передаёт отчёт о заполнении — он появится после обновления сервера.</p>
  }
  return (
    <>
      <Coverage coverage={coverage} metric={metric} />
      <IssueList rows={attention.filter((r) => r.issues.some((i) => issues.includes(i)))} empty={empty} filter={issues} />
    </>
  )
}

function Coverage({ coverage, metric }: { coverage: NonNullable<Overview['coverage']>; metric: 'seo' | 'lang' }) {
  const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 100)
  const bar = (n: number, total: number) => (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-border sm:w-28"><span className={cn('block h-full rounded-full', pct(n, total) === 100 ? 'bg-emerald-500' : 'bg-cms-gold')} style={{ width: `${pct(n, total)}%` }} /></span>
      <span className="text-xs text-ink-secondary tabular-nums">{n}/{total}</span>
    </span>
  )
  const types = TYPES.filter((t) => t !== 'testimonials')
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-border text-left text-xs text-ink-muted"><th className="px-5 py-2 font-medium">Раздел</th>{metric === 'lang' ? <><th className="px-3 py-2 font-medium">KG</th><th className="px-3 py-2 font-medium">EN</th></> : <th className="px-3 py-2 font-medium">SEO заполнено</th>}</tr></thead>
        <tbody className="divide-y divide-border">
          {types.map((t) => {
            const c = coverage[t]
            if (!c) return null
            return (
              <tr key={t}>
                <td className="px-5 py-2.5"><Link to={`${CMS_BASE}/${t}`} className="font-medium text-ink hover:text-brand-600">{RESOURCES[t].title}</Link></td>
                {metric === 'lang' ? <><td className="px-3 py-2.5">{bar(c.ky, c.total)}</td><td className="px-3 py-2.5">{bar(c.en, c.total)}</td></> : <td className="px-3 py-2.5">{bar(c.seo, c.total)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function IssueList({ rows, empty, filter }: { rows: ContentSummary[]; empty: string; filter?: string[] }) {
  if (!rows.length) return <p className="border-t border-border px-5 py-6 text-center text-sm text-ink-muted">{empty}</p>
  return (
    <ul className="divide-y divide-border border-t border-border">
      {rows.slice(0, 50).map((r) => (
        <li key={`${r.resource}-${r.id}`}>
          <Link to={editorPath(r.resource, r.id)} className="flex items-center gap-3 px-5 py-2.5 hover:bg-surface-hover">
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{r.title}</span>
              <span className="mt-0.5 flex flex-wrap gap-1 text-xs text-ink-muted">{r.type_label}
                {r.issues.filter((i) => !filter || filter.includes(i)).map((i) => <span key={i} className="rounded-full bg-cms-gold-soft px-1.5 text-[0.6875rem] font-medium text-cms-gold-deep">{ISSUE_LABEL[i]}</span>)}
              </span>
            </span>
            <span className="hidden sm:block"><StatusBadge state={r.state} /></span>
            <ChevronRight className="size-4 text-ink-muted" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}

function GeneralTab() {
  const meta = useSiteMeta()
  const p = meta.data?.permissions
  const site = meta.data?.public_site_url
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="Сайт">
        <dl className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-3"><dt className="text-ink-secondary">Адрес</dt><dd className="truncate font-medium text-ink">{site ?? 'не настроен (PUBLIC_WEBSITE_URL)'}</dd></div>
          <div className="flex items-center justify-between gap-3"><dt className="text-ink-secondary">Языки</dt><dd className="font-medium text-ink">RU · KG · EN</dd></div>
          <div className="flex items-center justify-between gap-3"><dt className="text-ink-secondary">Обновление на сайте</dt><dd className="text-right font-medium text-ink">в течение ~2 минут</dd></div>
        </dl>
        {site ? <a href={site} target="_blank" rel="noreferrer" className={cn(linkButton('secondary'), 'mt-4')}><ExternalLink className="size-4" aria-hidden />Открыть сайт</a> : null}
      </Panel>
      <Panel title="Публикация и права">
        <ul className="space-y-2.5 text-sm">
          <li className="flex gap-2"><ShieldCheck className="size-4 shrink-0 text-brand-600" aria-hidden /><span>{p?.require_approval ? 'Маркетинг отправляет материалы на согласование; публикует директор или администратор.' : 'Маркетинг публикует материалы сам — без согласования.'}</span></li>
          <li className="flex gap-2"><ShieldCheck className="size-4 shrink-0 text-brand-600" aria-hidden /><span>Ваши права: {p?.can_edit ? 'редактирование' : 'просмотр'}{p?.can_approve ? ', публикация и согласование' : ''}{p?.can_delete_leads ? ', удаление заявок' : ''}.</span></li>
          <li className="flex gap-2"><ShieldCheck className="size-4 shrink-0 text-brand-600" aria-hidden /><span>Заявки видят маркетинг, отдел продаж, директор и администратор. Проекты учеников добавляют тренеры.</span></li>
        </ul>
        <p className="mt-3 text-xs text-ink-muted">Режим согласования включает администратор сервера (WEBSITE_REQUIRE_APPROVAL).</p>
      </Panel>
    </div>
  )
}
