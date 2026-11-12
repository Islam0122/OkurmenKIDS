import { useState } from 'react'
import { Archive, Copy, ExternalLink, FileText, MoreHorizontal, Pencil, Plus, Trash2, Undo2, Upload } from 'lucide-react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, useSiteMeta, type Row } from './api'
import { useChoices } from './useChoices'
import { CONTENT_KEYS, RESOURCES, type ResourceDef } from './schema'
import { CmsPage, Dropdown, editorPath, formatDate, linkButton, ListSkeleton, relativeTime, StatusBadge } from './ui'

const PAGE_SIZE = 30

/** /marketing/site/:resource — список материалов одного типа. */
export function ContentListRoute() {
  const { resource = '' } = useParams()
  if (!CONTENT_KEYS.includes(resource as ResourceDef['key'])) return <Navigate to="/marketing/site" replace />
  return <ContentListPage key={resource} resource={resource as ResourceDef['key']} />
}

export function ContentListPage({ resource, embedded }: { resource: ResourceDef['key']; embedded?: boolean }) {
  const def = RESOURCES[resource]
  const navigate = useNavigate()
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const meta = useSiteMeta()
  const choices = useChoices(meta.data)
  const [params, setParams] = useSearchParams()
  const status = embedded ? '' : params.get('status') ?? ''
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState(1)
  const [remove, setRemove] = useState<Row | null>(null)
  const query = useSiteList(resource, { search: search || undefined, status: status || undefined, page, page_size: PAGE_SIZE, ...filters })
  const { rows, count } = toList(query.data)
  const label = (source: string | undefined, value: unknown) => choices(source).find((c) => c.value === String(value))?.label ?? ''
  const canEdit = meta.data?.permissions.can_edit !== false
  const canPublish = Boolean(meta.data && (meta.data.permissions.can_approve || !meta.data.permissions.require_approval))

  const tabs = def.workflow ? [
    { value: '', label: 'Все' },
    { value: 'draft', label: 'Черновики' },
    ...(def.workflow === 'full' && meta.data?.permissions.require_approval ? [{ value: 'review', label: 'На согласовании' }] : []),
    { value: 'scheduled', label: 'Запланировано' },
    { value: 'published', label: 'Опубликовано' },
    ...(def.workflow === 'full' ? [{ value: 'archived', label: 'Архив' }] : []),
  ] : []

  const act = async (row: Row, action: string, success: string) => {
    try {
      await siteCmsApi.action(resource, row.id, action, action === 'publish' ? { keep_schedule: true } : {})
      await invalidate()
      showToast(success, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }

  const rowActions = (row: Row) => {
    const state = row.workflow_state as string | undefined
    const preview = (row.preview as { url: string | null } | undefined)?.url
    return [
      { key: 'edit', label: 'Редактировать', icon: <Pencil className="size-4" aria-hidden />, onClick: () => navigate(editorPath(resource, row.id)) },
      ...(preview ? [{ key: 'preview', label: 'Предпросмотр на сайте', icon: <ExternalLink className="size-4" aria-hidden />, onClick: () => window.open(preview, '_blank', 'noopener') }] : []),
      ...(row.public_url ? [{ key: 'copy', label: 'Копировать ссылку', icon: <Copy className="size-4" aria-hidden />, onClick: () => navigator.clipboard?.writeText(String(row.public_url)).then(() => showToast('Ссылка скопирована', 'success')) }] : []),
      ...(canEdit && def.workflow && canPublish && (state === 'draft' || state === 'review') ? [{ key: 'publish', label: 'Опубликовать', icon: <Upload className="size-4" aria-hidden />, onClick: () => act(row, 'publish', 'Опубликовано') }] : []),
      ...(canEdit && def.workflow && (state === 'published' || state === 'scheduled') ? [{ key: 'unpublish', label: 'Снять с публикации', icon: <Undo2 className="size-4" aria-hidden />, onClick: () => act(row, 'unpublish', 'Снято с публикации') }] : []),
      ...(canEdit && def.workflow === 'full' && state === 'archived' ? [{ key: 'restore', label: 'Вернуть в черновики', icon: <Undo2 className="size-4" aria-hidden />, onClick: () => act(row, 'unpublish', 'Возвращено в черновики') }] : []),
      ...(canEdit && def.workflow === 'full' && state !== 'archived' ? [{ key: 'archive', label: 'В архив', icon: <Archive className="size-4" aria-hidden />, onClick: () => act(row, 'archive', 'Перенесено в архив') }] : []),
      ...(canEdit ? [{ key: 'delete', label: 'Удалить', tone: 'danger' as const, icon: <Trash2 className="size-4" aria-hidden />, onClick: () => setRemove(row) }] : []),
    ]
  }

  const title = (row: Row) => String(row[def.titleField] || '—')
  const image = (row: Row) => (def.image ? ((row[def.image] as string | null) ?? (row.teacher_photo as string | null) ?? null) : null)
  const meta2 = (row: Row) => [
    def.categoryField ? label(def.fields.find((f) => f.name === def.categoryField)?.choices, row[def.categoryField]) : '',
    def.dateField && row[def.dateField] ? formatDate(row[def.dateField], def.dateField !== 'date') : '',
  ].filter(Boolean).join(' · ') || (def.subtitle?.(row, (s, v) => label(s, v)) ?? '')
  const langs = (row: Row) => {
    const fields = def.fields.filter((f) => f.translatable && String(row[f.name] ?? '').trim())
    if (!fields.length) return null
    return (['ky', 'en'] as const).map((l) => ({ l, ok: fields.every((f) => String(row[`${f.name}_${l}`] ?? '').trim()) }))
  }

  const add = canEdit ? (
    <Link to={editorPath(resource)} className={linkButton('primary')}><Plus className="size-4" aria-hidden />Добавить</Link>
  ) : undefined

  const body = (
    <>
      {tabs.length ? (
        <div role="tablist" aria-label="Статус" className="scroll-x -mx-4 flex gap-1 px-4 sm:mx-0 sm:px-0">
          {tabs.map((t) => (
            <button key={t.value} type="button" role="tab" aria-selected={status === t.value}
              onClick={() => { setParams(t.value ? { status: t.value } : {}, { replace: true }); setPage(1) }}
              className={cn('h-9 shrink-0 rounded-full px-3.5 text-sm font-medium transition-colors', status === t.value ? 'bg-brand-500 text-white' : 'bg-surface text-ink-secondary ring-1 ring-border hover:text-ink')}>
              {t.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Поиск" /></div>
        {def.filters?.map((f) => (
          <div key={f.name} className="sm:w-56">
            <Select aria-label={f.label} value={filters[f.name] ?? ''} placeholder={`${f.label}: все`} options={choices(f.choices)}
              onChange={(e) => { setFilters({ ...filters, [f.name]: e.target.value }); setPage(1) }} />
          </div>
        ))}
        {count ? <span className="text-sm text-ink-muted sm:ml-auto">{count} {plural(count)}</span> : null}
      </div>

      {query.isPending ? <ListSkeleton rows={6} thumb={Boolean(def.image)} /> : query.isError ? (
        <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : rows.length ? (
        <>
          {/* Desktop / laptop: table */}
          <div className="hidden overflow-hidden rounded-2xl border border-border bg-surface md:block">
            <table className="w-full table-fixed text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-muted/60 text-left text-xs text-ink-muted">
                  <th className="px-4 py-2.5 font-medium">{def.single}</th>
                  {def.workflow ? <th className="w-36 px-3 py-2.5 font-medium">Статус</th> : null}
                  {def.fields.some((f) => f.translatable) ? <th className="w-32 px-3 py-2.5 font-medium">Языки</th> : null}
                  <th className="w-32 px-3 py-2.5 font-medium">Изменено</th>
                  <th className="w-12 px-3 py-2.5"><span className="sr-only">Действия</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((row) => (
                  <tr key={row.id} className="group hover:bg-surface-hover">
                    <td className="px-4 py-2.5">
                      <Link to={editorPath(resource, row.id)} className="flex min-w-0 items-center gap-3">
                        {def.image ? <Thumb src={image(row)} /> : null}
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink group-hover:text-brand-600">{title(row)}</span>
                          <span className="block truncate text-xs text-ink-muted">{meta2(row)}</span>
                        </span>
                      </Link>
                    </td>
                    {def.workflow ? <td className="px-3 py-2.5"><StatusBadge state={row.workflow_state as string} /></td> : null}
                    {def.fields.some((f) => f.translatable) ? <td className="px-3 py-2.5"><LangChips langs={langs(row)} /></td> : null}
                    <td className="px-3 py-2.5 whitespace-nowrap text-ink-muted">{relativeTime(row.updated_at)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <Dropdown label={`Действия: ${title(row)}`} items={rowActions(row)} trigger={<MoreHorizontal className="size-4" aria-hidden />} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Phone / tablet: cards */}
          <ul className="space-y-2 md:hidden">
            {rows.map((row) => (
              <li key={row.id} className="flex items-center gap-3 rounded-2xl border border-border bg-surface p-3">
                <Link to={editorPath(resource, row.id)} className="flex min-w-0 flex-1 items-center gap-3">
                  {def.image ? <Thumb src={image(row)} size="lg" /> : null}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-ink">{title(row)}</span>
                    <span className="block truncate text-xs text-ink-muted">{meta2(row)}</span>
                    <span className="mt-1.5 flex items-center gap-2">
                      {def.workflow ? <StatusBadge state={row.workflow_state as string} /> : null}
                      <LangChips langs={langs(row)} />
                    </span>
                  </span>
                </Link>
                <Dropdown label={`Действия: ${title(row)}`} items={rowActions(row)} trigger={<MoreHorizontal className="size-5" aria-hidden />}
                  triggerClassName="flex size-11 items-center justify-center rounded-xl text-ink-secondary hover:bg-surface-hover" />
              </li>
            ))}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : (
        <EmptyState icon={FileText}
          title={search || status || Object.values(filters).some(Boolean) ? 'Ничего не найдено' : `Здесь пока пусто`}
          description={search || status || Object.values(filters).some(Boolean) ? 'Измените поиск или фильтр.' : `${def.description} Добавьте первый материал — он сохранится как черновик и не появится на сайте до публикации.`}
          action={canEdit && !search && !status ? <Link to={editorPath(resource)} className={linkButton('primary')}><Plus className="size-4" aria-hidden />Добавить: {def.single.toLowerCase()}</Link> : undefined} />
      )}

      <ConfirmDialog isOpen={remove !== null} title="Удалить материал?" tone="danger" confirmLabel="Удалить"
        message={`«${remove ? title(remove) : ''}» будет удалён безвозвратно вместе с фотографиями. Чтобы только скрыть с сайта, снимите с публикации.`}
        onCancel={() => setRemove(null)}
        onConfirm={async () => {
          const row = remove!
          setRemove(null)
          try {
            await siteCmsApi.remove(resource, row.id)
            await invalidate()
            showToast('Удалено', 'success')
          } catch (error) {
            showToast(extractErrorMessage(error), 'error')
          }
        }} />
    </>
  )

  if (embedded) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-2"><p className="text-sm text-ink-secondary">{def.description}</p>{add}</div>
        {body}
      </div>
    )
  }
  return <CmsPage title={def.title} description={def.description} actions={add}><div className="space-y-4">{body}</div></CmsPage>
}

function plural(n: number) {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return 'материал'
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'материала'
  return 'материалов'
}

function Thumb({ src, size = 'md' }: { src: string | null; size?: 'md' | 'lg' }) {
  return (
    <span className={cn('grid shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-hover', size === 'lg' ? 'size-14' : 'size-11')}>
      {src ? <img src={src} alt="" className="size-full object-cover" loading="lazy" /> : <FileText className="size-5 text-ink-muted" aria-hidden />}
    </span>
  )
}

function LangChips({ langs }: { langs: { l: 'ky' | 'en'; ok: boolean }[] | null }) {
  if (!langs) return null
  return (
    <span className="inline-flex gap-1 text-[0.6875rem] font-semibold">
      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">RU</span>
      {langs.map(({ l, ok }) => (
        <span key={l} title={ok ? 'Переведено' : 'Нет перевода'} className={cn('rounded px-1.5 py-0.5', ok ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-hover text-ink-muted line-through')}>
          {l === 'ky' ? 'KG' : 'EN'}
        </span>
      ))}
    </span>
  )
}
