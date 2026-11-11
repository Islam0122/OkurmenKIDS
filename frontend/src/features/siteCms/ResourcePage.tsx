import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Archive, ExternalLink, Eye, FileText, Plus, Send, Trash2, Undo2, Upload } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, useSiteMeta, type Body, type Choice, type Row, type SiteMeta } from './api'
import { FieldInput, fromLocalInput, toLocalInput, TranslationInputs } from './fields'
import { RESOURCES, STATE_LABEL, type FieldDef, type ResourceDef } from './schema'

const PAGE_SIZE = 30

export const STATE_TONE: Record<string, BadgeTone> = {
  draft: 'muted',
  review: 'warning',
  scheduled: 'info',
  published: 'success',
  archived: 'muted',
}

function useChoices(meta: SiteMeta | undefined) {
  const branches = useSiteList('branches', {})
  return (source?: string): Choice[] => {
    if (!source) return []
    if (source === 'lms:courses') return (meta?.lms?.courses ?? []).map((c) => ({ value: String(c.id), label: `${c.name} (${c.lessons} зан.)` }))
    if (source === 'lms:teachers') return (meta?.lms?.teachers ?? []).map((t) => ({ value: String(t.id), label: `${t.name} — ${t.position}` }))
    if (source === 'branches') return toList(branches.data).rows.map((b) => ({ value: String(b.id), label: String(b.name) }))
    return meta?.choices[source] ?? []
  }
}

/** /marketing/site/<resource> — список, фильтры и редактор одного типа контента сайта. */
export function ResourcePage({ resource }: { resource: ResourceDef['key'] }) {
  const def = RESOURCES[resource]
  const meta = useSiteMeta()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Row | null | undefined>(undefined)
  // ?edit=<id> opens that record (links from the import results).
  const [searchParams, setSearchParams] = useSearchParams()
  const editId = Number(searchParams.get('edit')) || null
  useEffect(() => {
    if (!editId) return
    let active = true
    siteCmsApi.get(resource, editId).then((row) => active && setEditing(row)).catch(() => undefined)
    return () => { active = false }
  }, [resource, editId])
  const closeEditor = () => {
    setEditing(undefined)
    if (editId) setSearchParams((p) => { p.delete('edit'); return p }, { replace: true })
  }
  const params = { search: search || undefined, status: status || undefined, page, page_size: PAGE_SIZE, ...filters }
  const query = useSiteList(resource, params)
  const { rows, count } = toList(query.data)
  const choices = useChoices(meta.data)
  const label = (source: string, value: unknown) => choices(source).find((c) => c.value === String(value))?.label ?? ''
  const canEdit = meta.data?.permissions.can_edit !== false
  const statuses = def.workflow === 'news'
    ? [{ value: 'draft', label: 'Черновики' }, { value: 'scheduled', label: 'Запланировано' }, { value: 'published', label: 'На сайте' }]
    : def.workflow ? meta.data?.choices.workflow ?? [] : []

  return (
    <div className="space-y-4">
      <PageHeader title={def.title} description={def.description}
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing(null)}>Добавить</Button> : undefined} />

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Поиск" /></div>
        {statuses.length ? (
          <div className="sm:w-52"><Select aria-label="Статус" value={status} placeholder="Все статусы" options={statuses} onChange={(e) => { setStatus(e.target.value); setPage(1) }} /></div>
        ) : null}
        {def.filters?.map((f) => (
          <div key={f.name} className="sm:w-52">
            <Select aria-label={f.label} value={filters[f.name] ?? ''} placeholder={`${f.label}: все`} options={choices(f.choices)}
              onChange={(e) => { setFilters({ ...filters, [f.name]: e.target.value }); setPage(1) }} />
          </div>
        ))}
      </div>

      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <>
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {rows.map((row) => {
              const image = def.image ? (row[def.image] as string | null) : null
              const state = row.workflow_state as string | undefined
              return (
                <li key={row.id}>
                  <button type="button" onClick={() => setEditing(row)} className="flex w-full items-center gap-3 px-3 py-3 text-left hover:bg-surface-hover sm:px-4">
                    {def.image ? (
                      <span className="grid size-12 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-muted">
                        {image ? <img src={image} alt="" className="size-full object-cover" loading="lazy" /> : <FileText className="size-5 text-ink-muted" aria-hidden />}
                      </span>
                    ) : null}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-ink">{String(row[def.titleField] || '—')}</span>
                      <span className="block truncate text-xs text-ink-secondary">{def.subtitle?.(row, label)}</span>
                    </span>
                    {state ? <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge> : null}
                  </button>
                </li>
              )
            })}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : (
        <EmptyState title="Пока ничего нет" description={search || status ? 'Измените поиск или фильтр.' : `Добавьте первый материал — «${def.single}».`} />
      )}

      {editing !== undefined && meta.data ? (
        <Editor def={def} row={editing} meta={meta.data} choices={choices} onClose={closeEditor} onSaved={(r) => setEditing(r)} />
      ) : null}
    </div>
  )
}

const NULLABLE_SELECT = (f: FieldDef) => Boolean(f.choices?.startsWith('lms:') || f.choices === 'branches')

function emptyValue(f: FieldDef): unknown {
  if (f.type === 'boolean') return f.name === 'is_active' || f.name === 'is_visible'
  if (f.type === 'number' || f.type === 'datetime') return null
  if (f.type === 'select') return NULLABLE_SELECT(f) ? null : ''
  if (f.type === 'date') return new Date().toISOString().slice(0, 10)
  return ''
}

function initialValues(def: ResourceDef, row: Row | null, choices?: (source?: string) => Choice[]): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const f of def.fields) {
    if (f.type === 'image') continue // undefined = unchanged
    const current = row?.[f.name]
    values[f.name] = current === undefined || (current === null && !NULLABLE_SELECT(f) && f.type !== 'number' && f.type !== 'datetime') ? emptyValue(f) : current
    if (!row && f.type === 'select' && f.required && !values[f.name]) values[f.name] = choices?.(f.choices)[0]?.value ?? ''
    if (f.translatable) for (const l of ['ky', 'en']) values[`${f.name}_${l}`] = row?.[`${f.name}_${l}`] ?? ''
  }
  if (def.workflow) values.published_at = row?.published_at ?? null
  if (!row && def.key === 'testimonials') values.language = 'ru'
  return values
}

function Editor({ def, row, meta, choices, onClose, onSaved }: {
  def: ResourceDef
  row: Row | null
  meta: SiteMeta
  choices: (source?: string) => Choice[]
  onClose: () => void
  onSaved: (row: Row) => void
}) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [values, setValues] = useState<Record<string, unknown>>(() => initialValues(def, row, choices))
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const set = (name: string, v: unknown) => setValues((prev) => ({ ...prev, [name]: v }))
  const { can_approve, require_approval, can_edit } = meta.permissions
  const canPublish = can_approve || !require_approval
  const state = row?.workflow_state as string | undefined
  const missing = def.fields.filter((f) => f.required && f.type !== 'boolean' && (values[f.name] === null || values[f.name] === undefined || values[f.name] === ''))

  const body = (): Body => {
    const out: Body = {}
    for (const [key, value] of Object.entries(values)) {
      if (value === undefined) continue
      const field = def.fields.find((f) => f.name === key)
      out[key] = field && field.type === 'select' && NULLABLE_SELECT(field) && value !== null ? Number(value) : value
    }
    if (!out.published_at) delete out.published_at
    return out
  }

  const run = async (name: string, task: () => Promise<Row | void>, success: string) => {
    setBusy(name)
    try {
      const result = await task()
      await invalidate()
      showToast(success, 'success')
      if (result) {
        onSaved(result)
        setValues(initialValues(def, result, choices))
      }
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setBusy(null)
    }
  }

  const save = () => run('save', () => siteCmsApi.save(def.key, row?.id ?? null, body()), 'Сохранено')
  const transition = (action: string, success: string, extra: Body = {}) =>
    run(action, async () => {
      const saved = await siteCmsApi.save(def.key, row?.id ?? null, body())
      return siteCmsApi.action(def.key, saved.id, action, extra)
    }, success)
  const publishAt = values.published_at ? new Date(String(values.published_at)) : null
  const scheduled = publishAt !== null && publishAt.getTime() > Date.now() + 60_000

  const preview = row?.preview as { url: string | null } | undefined
  const publicUrl = row?.public_url as string | null | undefined
  const wide = (f: FieldDef) => f.wide || f.type === 'richtext' || f.type === 'image'

  return (
    <Modal isOpen onClose={onClose} title={row ? String(row[def.titleField] || def.single) : `Новый материал: ${def.single.toLowerCase()}`} size="xl">
      <div className="space-y-5">
        {state ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
            {row?.created_by_name ? <span className="text-ink-secondary">Автор: {String(row.created_by_name)}</span> : null}
            {row?.reviewed_by_name ? <span className="text-ink-secondary">· Утвердил: {String(row.reviewed_by_name)}</span> : null}
            {publicUrl ? <a href={publicUrl} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 font-medium text-brand-700 hover:underline">На сайте <ExternalLink className="size-3.5" aria-hidden /></a> : null}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          {def.fields.map((f) => (
            <div key={f.name} className={cn(wide(f) && 'sm:col-span-2')}>
              {f.type !== 'boolean' ? (
                <label htmlFor={`f-${f.name}`} className="field-label">{f.label}{f.required ? ' *' : ''}</label>
              ) : null}
              <FieldInput field={f} id={`f-${f.name}`} value={values[f.name]} onChange={(v) => set(f.name, v)} choices={choices(f.choices)}
                current={f.type === 'image' ? (row?.[f.name] as string | null) ?? null : undefined} />
              {f.hint ? <p className="mt-1 text-xs text-ink-muted">{f.hint}</p> : null}
              {f.translatable ? <TranslationInputs field={f} values={values} onChange={set} /> : null}
            </div>
          ))}
          {def.workflow ? (
            <div>
              <label htmlFor="f-published_at" className="field-label">Дата публикации</label>
              <Input id="f-published_at" type="datetime-local" value={toLocalInput(values.published_at)} onChange={(e) => set('published_at', fromLocalInput(e.target.value))} />
              <p className="mt-1 text-xs text-ink-muted">Дата в будущем — материал появится на сайте в это время (запланировано).</p>
            </div>
          ) : null}
        </div>

        {def.gallery && row ? <GalleryManager resource={def.key} row={row} onChange={onSaved} /> : null}
        {def.gallery && !row ? <p className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-ink-secondary">Галерея фотографий станет доступна после первого сохранения.</p> : null}

        {can_edit ? (
          <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap sm:items-center">
            {row ? <Button variant="ghost" className="text-danger sm:mr-auto" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirmDelete(true)}>Удалить</Button> : <span className="sm:mr-auto" />}
            {preview?.url ? (
              <a href={preview.url} target="_blank" rel="noreferrer" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium text-ink-secondary hover:bg-surface-hover">
                <Eye className="size-4" aria-hidden /> Предпросмотр
              </a>
            ) : null}
            {def.workflow && row && state !== 'draft' && state !== 'archived' ? (
              <Button variant="ghost" leftIcon={<Undo2 className="size-4" aria-hidden />} isLoading={busy === 'unpublish'} onClick={() => transition('unpublish', 'Перенесено в черновики')}>В черновики</Button>
            ) : null}
            {def.workflow === 'full' && row && state !== 'archived' ? (
              <Button variant="ghost" leftIcon={<Archive className="size-4" aria-hidden />} isLoading={busy === 'archive'} onClick={() => transition('archive', 'Перенесено в архив')}>В архив</Button>
            ) : null}
            <Button variant="secondary" isLoading={busy === 'save'} disabled={missing.length > 0} onClick={save}>Сохранить</Button>
            {def.workflow === 'full' && !canPublish && state !== 'review' && state !== 'published' && state !== 'scheduled' ? (
              <Button leftIcon={<Send className="size-4" aria-hidden />} isLoading={busy === 'submit_review'} disabled={missing.length > 0}
                onClick={() => transition('submit_review', 'Отправлено на согласование')}>На согласование</Button>
            ) : null}
            {def.workflow && canPublish && (state !== 'published' || def.workflow === 'news') ? (
              <Button leftIcon={<Upload className="size-4" aria-hidden />} isLoading={busy === 'publish'} disabled={missing.length > 0}
                onClick={() => transition('publish', scheduled ? 'Публикация запланирована' : 'Опубликовано', { keep_schedule: scheduled, ...(scheduled ? { published_at: values.published_at } : {}) })}>
                {scheduled ? 'Запланировать' : state === 'published' ? 'Обновить на сайте' : 'Опубликовать'}
              </Button>
            ) : null}
          </div>
        ) : null}
        {missing.length ? <p className="text-xs text-ink-muted">Заполните: {missing.map((f) => f.label).join(', ')}.</p> : null}
        {def.workflow === 'full' && require_approval && !can_approve ? (
          <p className="text-xs text-ink-muted">Публикует директор или администратор: отправьте материал на согласование.</p>
        ) : null}
      </div>

      <ConfirmDialog isOpen={confirmDelete} title="Удалить?" message="Материал и его фотографии будут удалены безвозвратно. Чтобы просто убрать с сайта, используйте «В черновики» или «В архив»."
        confirmLabel="Удалить" tone="danger" isLoading={busy === 'delete'} onCancel={() => setConfirmDelete(false)}
        onConfirm={() => run('delete', async () => { await siteCmsApi.remove(def.key, row!.id); onClose() }, 'Удалено')} />
    </Modal>
  )
}

interface Photo {
  id: number
  url: string
  thumb: string
  caption: string
  order: number
}

function GalleryManager({ resource, row, onChange }: { resource: string; row: Row; onChange: (row: Row) => void }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [uploading, setUploading] = useState(false)
  const photos = useMemo(() => (row.photos as Photo[] | undefined) ?? [], [row.photos])
  const call = async (task: () => Promise<Row>) => {
    try {
      const updated = await task()
      onChange(updated)
      await invalidate()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  return (
    <section className="rounded-xl border border-border p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-semibold text-ink">Фотографии <span className="text-ink-muted">({photos.length})</span></h3>
        <label className={cn('inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600', uploading && 'pointer-events-none opacity-60')}>
          <Upload className="size-4" aria-hidden /> {uploading ? 'Загрузка…' : 'Добавить фото'}
          <input type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only"
            onChange={async (e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (!files.length) return
              setUploading(true)
              await call(() => siteCmsApi.addPhotos(resource, row.id, files))
              setUploading(false)
            }} />
        </label>
      </div>
      {photos.length ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {photos.map((p) => (
            <li key={p.id} className="overflow-hidden rounded-lg border border-border">
              <img src={p.thumb} alt={p.caption} className="aspect-[4/3] w-full object-cover" loading="lazy" />
              <div className="space-y-1 p-2">
                <Input aria-label="Подпись" defaultValue={p.caption} placeholder="Подпись" className="h-8 text-xs"
                  onBlur={(e) => e.target.value !== p.caption && call(() => siteCmsApi.updatePhoto(resource, row.id, p.id, { caption: e.target.value }))} />
                <div className="flex items-center gap-1">
                  <Input aria-label="Порядок" type="number" defaultValue={p.order} className="h-8 w-16 text-xs"
                    onBlur={(e) => Number(e.target.value) !== p.order && call(() => siteCmsApi.updatePhoto(resource, row.id, p.id, { order: Number(e.target.value) }))} />
                  <button type="button" onClick={() => call(() => siteCmsApi.deletePhoto(resource, row.id, p.id))} className="ml-auto grid size-8 place-items-center rounded-md text-ink-secondary hover:bg-danger-soft hover:text-danger" aria-label="Удалить фото">
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-ink-muted">Фотографий пока нет. Можно выбрать сразу несколько файлов (до 40).</p>}
    </section>
  )
}
