import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive, CalendarClock, Check, CircleAlert, Cloud, CloudOff, ExternalLink, Eye, History, ImagePlus, Loader2, MoreHorizontal, RotateCcw,
  Save, Send, Trash2, Undo2, Upload,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useBlocker, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, useSiteInvalidate, useSiteItem, useSiteMeta, type Body, type Choice, type Row, type SiteMeta, cmsErrorMessage } from './api'
import { useChoices } from './useChoices'
import {
  backupKey, buildBody, initialValues, isEmpty, langFill, mergeSaved, missingFields, readBackup, snapshot, writeBackup, type Values,
} from './editorState'
import { FieldInput, fromLocalInput, toLocalInput, type ImageValue } from './fields'
import { MediaPicker } from './MediaPicker'
import { parseMarkup } from './markup'
import { MarkupPreview } from './RichTextEditor'
import { CONTENT_KEYS, LANGS, RESOURCES, type FieldDef, type Lang, type ResourceDef } from './schema'
import {
  CMS_BASE, Counter, Dropdown, FieldLabel, formatDate, Hint, LangTabs, linkButton, Panel, relativeTime, Skeleton, StatusBadge,
} from './ui'

/** /marketing/site/:resource/:id (id = new) — полноэкранный редактор материала. */
export function ContentEditorRoute() {
  const { resource = '', id = '' } = useParams()
  const location = useLocation()
  // A record created on /new keeps its editor (and the state in it) when the
  // address becomes /<id>.
  const adopted = useRef<{ id: number; key: string } | null>(null)
  const valid = CONTENT_KEYS.includes(resource as ResourceDef['key']) && (id === 'new' || /^\d+$/.test(id))
  const numeric = id === 'new' ? null : Number(id)
  const isAdopted = adopted.current !== null && adopted.current.id === numeric
  const key = isAdopted ? adopted.current!.key : id === 'new' ? `new:${location.key}` : `id:${id}`
  const meta = useSiteMeta()
  const item = useSiteItem(resource, valid && !isAdopted ? numeric : null)
  if (!valid) return <Navigate to={CMS_BASE} replace />
  const def = RESOURCES[resource as ResourceDef['key']]
  if (meta.isPending || (numeric !== null && !isAdopted && item.isPending)) return <EditorSkeleton />
  if (meta.isError || item.isError) {
    return <ErrorState message={cmsErrorMessage(meta.error ?? item.error)} onRetry={() => { meta.refetch(); item.refetch() }} />
  }
  return (
    <ContentEditor key={`${resource}:${key}`} def={def} meta={meta.data!} initialRow={isAdopted ? null : item.data ?? null}
      onCreated={(row) => { adopted.current = { id: row.id, key } }} />
  )
}

function EditorSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Загрузка редактора">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-8 w-2/3" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4 rounded-2xl border border-border bg-surface p-5">
          <Skeleton className="h-9 w-48" /><Skeleton className="h-10 w-full" /><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" />
        </div>
        <div className="space-y-4">
          <div className="space-y-3 rounded-2xl border border-border bg-surface p-5"><Skeleton className="h-5 w-24" /><Skeleton className="h-10 w-full" /></div>
          <div className="space-y-3 rounded-2xl border border-border bg-surface p-5"><Skeleton className="aspect-video w-full" /></div>
        </div>
      </div>
    </div>
  )
}

type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'local'

function ContentEditor({ def, meta, initialRow, onCreated }: { def: ResourceDef; meta: SiteMeta; initialRow: Row | null; onCreated: (row: Row) => void }) {
  const { showToast } = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const invalidate = useSiteInvalidate()
  const [params, setParams] = useSearchParams()
  const choices = useChoices(meta)
  const [row, setRow] = useState<Row | null>(initialRow)
  const [baseline, setBaseline] = useState<Values>(() => initialValues(def, initialRow, choices))
  const [values, setValues] = useState<Values>(baseline)
  const [lang, setLang] = useState<Lang>('ru')
  const [busy, setBusy] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [savedAt, setSavedAt] = useState<number | null>(initialRow ? Date.parse(String(initialRow.updated_at ?? '')) || null : null)
  const [confirm, setConfirm] = useState<null | 'delete' | 'discard' | 'archive'>(null)
  const [preview, setPreview] = useState(params.get('preview') === '1')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const storageKey = backupKey(def.key, row?.id ?? null)
  const [backup, setBackup] = useState(() => {
    const b = readBackup(backupKey(def.key, initialRow?.id ?? null))
    if (!b || b.base !== ((initialRow?.updated_at as string | undefined) ?? null)) return null
    return snapshot({ ...baseline, ...b.values }) !== snapshot(baseline) ? b : null
  })

  const state = (row?.workflow_state as string | undefined) ?? (def.workflow ? 'draft' : undefined)
  const dirty = snapshot(values) !== snapshot(baseline)
  const missing = missingFields(def, values, row)
  const { can_approve, require_approval, can_edit } = meta.permissions
  const canPublish = can_approve || !require_approval
  const isLive = state === 'published' || state === 'scheduled'
  const fill = langFill(def, values)
  const translatable = def.fields.some((f) => f.translatable)
  const set = useCallback((name: string, v: unknown) => {
    setValues((prev) => ({ ...prev, [name]: v }))
    setErrors((prev) => (prev[name] ? { ...prev, [name]: '' } : prev))
  }, [])

  // ----- saving ------------------------------------------------------------
  const inFlight = useRef(false)
  /** Set before a programmatic navigation that must not ask «leave without saving?». */
  const leaving = useRef(false)
  const valuesRef = useRef(values)
  valuesRef.current = values

  const applySaved = useCallback((saved: Row, sent: Values) => {
    const fresh = initialValues(def, saved, choices)
    setRow(saved)
    setBaseline(fresh)
    setValues((current) => mergeSaved(current, sent, fresh))
    setSavedAt(Date.now())
    queryClient.setQueryData(['site-cms', def.key, 'item', saved.id], saved)
  }, [def, choices, queryClient])

  const persist = useCallback(async (): Promise<Row> => {
    const sent = valuesRef.current
    const saved = await siteCmsApi.save(def.key, row?.id ?? null, buildBody(def, sent))
    if (!row) {
      writeBackup(backupKey(def.key, null), null)
      onCreated(saved)
      leaving.current = true
      navigate(`${CMS_BASE}/${def.key}/${saved.id}${preview ? '?preview=1' : ''}`, { replace: true })
    }
    applySaved(saved, sent)
    leaving.current = false
    return saved
  }, [def, row, onCreated, navigate, applySaved, preview])

  const fail = useCallback((error: unknown) => {
    const data = (error as { response?: { data?: unknown } })?.response?.data
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      const fieldErrors: Record<string, string> = {}
      for (const [k, v] of Object.entries(data as Record<string, unknown>)) fieldErrors[k] = Array.isArray(v) ? v.join(' ') : String(v)
      setErrors(fieldErrors)
    }
    showToast(extractErrorMessage(error), 'error')
  }, [showToast])

  const run = useCallback(async (name: string, task: () => Promise<unknown>, success?: string) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(name)
    setSaveState('saving')
    try {
      await task()
      await invalidate()
      setSaveState('saved')
      setErrors({})
      if (success) showToast(success, 'success')
    } catch (error) {
      setSaveState('error')
      fail(error)
    } finally {
      inFlight.current = false
      setBusy(null)
    }
  }, [invalidate, showToast, fail])

  const publishAt = values.published_at ? new Date(String(values.published_at)) : null
  const scheduled = publishAt !== null && publishAt.getTime() > Date.now() + 60_000

  const save = () => run('save', persist, isLive ? 'Изменения сохранены и уже на сайте' : def.workflow ? 'Черновик сохранён' : 'Сохранено')
  const transition = (action: string, success: string, extra: Body = {}) => run(action, async () => {
    const saved = dirty || !row ? await persist() : row
    const result = await siteCmsApi.action(def.key, saved.id, action, extra)
    applySaved(result, valuesRef.current)
  }, success)
  const publish = () => transition('publish', scheduled ? `Публикация запланирована на ${formatDate(values.published_at, true)}` : 'Опубликовано на сайте',
    { keep_schedule: scheduled, ...(scheduled ? { published_at: values.published_at } : {}) })

  // Autosave: drafts go to the server 3 s after the last change; published
  // content is kept locally only (saving it would change the live site).
  useEffect(() => {
    if (!dirty) {
      setSaveState((s) => (s === 'dirty' || s === 'local' ? 'idle' : s))
      writeBackup(storageKey, null)
      return
    }
    const local = window.setTimeout(() => {
      writeBackup(storageKey, { values, at: Date.now(), base: (row?.updated_at as string | undefined) ?? null })
    }, 600)
    const serverDraft = can_edit && row && def.workflow && (state === 'draft' || state === 'review') && missing.length === 0
    setSaveState(serverDraft ? 'dirty' : 'local')
    const remote = serverDraft ? window.setTimeout(() => {
      if (inFlight.current) return
      inFlight.current = true
      setSaveState('saving')
      persist().then(() => { setSaveState('saved'); invalidate() }, () => setSaveState('error')).finally(() => { inFlight.current = false })
    }, 3000) : undefined
    return () => {
      window.clearTimeout(local)
      if (remote) window.clearTimeout(remote)
    }
  }, [snapshot(values), dirty])

  // Ctrl/⌘ + S saves.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (can_edit && missing.length === 0 && !busy) save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // Leaving with unsaved changes asks first (in-app links and closing the tab).
  const blocker = useBlocker(({ currentLocation, nextLocation }) => !leaving.current && dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [dirty])

  const closePreview = () => {
    setPreview(false)
    if (params.get('preview')) {
      params.delete('preview')
      setParams(params, { replace: true })
    }
  }

  // ----- layout ------------------------------------------------------------
  const title = String(values[def.titleField] || (def.titleField === 'display_name' ? values.name : '') || row?.[def.titleField] || '')
  const mainFields = def.fields.filter((f) => !f.side && ['text', 'textarea', 'richtext', 'lines'].includes(f.type) && f.name !== 'slug')
  const mediaFields = def.fields.filter((f) => f.type === 'image')
  const sideFields = def.fields.filter((f) => !mainFields.includes(f) && !mediaFields.includes(f))
  const shownMain = lang === 'ru' ? mainFields : mainFields.filter((f) => f.translatable)
  const publicUrl = row?.public_url as string | null | undefined

  const moreItems = [
    ...(dirty ? [{ key: 'discard', label: 'Отменить изменения', icon: <RotateCcw className="size-4" aria-hidden />, onClick: () => setConfirm('discard') }] : []),
    ...(def.workflow && row && isLive ? [{ key: 'unpublish', label: 'Снять с публикации', hint: 'Вернуть в черновики', icon: <Undo2 className="size-4" aria-hidden />, onClick: () => transition('unpublish', 'Снято с публикации — материал в черновиках') }] : []),
    ...(def.workflow === 'full' && row && state === 'review' ? [{ key: 'back', label: 'Вернуть в черновики', icon: <Undo2 className="size-4" aria-hidden />, onClick: () => transition('unpublish', 'Перенесено в черновики') }] : []),
    ...(def.workflow === 'full' && row && state !== 'archived' ? [{ key: 'archive', label: 'В архив', hint: 'Скрыть с сайта, не удаляя', icon: <Archive className="size-4" aria-hidden />, onClick: () => setConfirm('archive') }] : []),
    ...(publicUrl ? [{ key: 'open', label: 'Открыть на сайте', icon: <ExternalLink className="size-4" aria-hidden />, onClick: () => window.open(publicUrl, '_blank', 'noopener') }] : []),
    ...(row ? [{ key: 'delete', label: 'Удалить', tone: 'danger' as const, icon: <Trash2 className="size-4" aria-hidden />, onClick: () => setConfirm('delete') }] : []),
  ]

  const primary = !can_edit ? null : def.workflow ? (
    canPublish ? (
      <Button leftIcon={scheduled ? <CalendarClock className="size-4" aria-hidden /> : <Upload className="size-4" aria-hidden />} isLoading={busy === 'publish'}
        disabled={missing.length > 0 || (state === 'published' && !dirty && !scheduled) || Boolean(busy && busy !== 'publish')} onClick={publish}>
        {scheduled ? 'Запланировать' : isLive ? 'Обновить на сайте' : 'Опубликовать'}
      </Button>
    ) : def.workflow === 'full' && state !== 'review' && !isLive ? (
      <Button leftIcon={<Send className="size-4" aria-hidden />} isLoading={busy === 'submit_review'} disabled={missing.length > 0}
        onClick={() => transition('submit_review', 'Отправлено на согласование')}>На согласование</Button>
    ) : null
  ) : (
    <Button leftIcon={<Save className="size-4" aria-hidden />} isLoading={busy === 'save'} disabled={missing.length > 0 || (!dirty && Boolean(row))} onClick={save}>Сохранить</Button>
  )
  const draftButton = can_edit && def.workflow ? (
    <Button variant="secondary" leftIcon={<Save className="size-4" aria-hidden />} isLoading={busy === 'save'} disabled={missing.length > 0 || (!dirty && Boolean(row)) || Boolean(busy && busy !== 'save')} onClick={save}>
      {isLive ? 'Сохранить' : 'Сохранить черновик'}
    </Button>
  ) : null

  return (
    <div className="space-y-5 pb-20 lg:pb-0">
      {/* Header: back, title, status, autosave, actions */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <button type="button" onClick={() => navigate(`${CMS_BASE}/${def.key}`)} className="mb-1.5 inline-flex items-center gap-1 text-sm font-medium text-ink-secondary hover:text-brand-600">
            ← {def.title}
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="min-w-0 truncate font-display text-xl font-bold text-ink sm:text-2xl">{title || `Новый материал: ${def.single.toLowerCase()}`}</h1>
            <StatusBadge state={state} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
            <SaveIndicator state={saveState} savedAt={savedAt} isNew={!row} />
            {row?.created_by_name || row?.author_name ? <span>Автор: {String(row.created_by_name ?? row.author_name)}</span> : null}
            {row?.reviewed_by_name ? <span>Утвердил: {String(row.reviewed_by_name)}</span> : null}
          </div>
        </div>
        <div className="hidden flex-wrap items-center gap-2 lg:flex">
          <Button variant="ghost" leftIcon={<Eye className="size-4" aria-hidden />} onClick={() => setPreview(true)}>Предпросмотр</Button>
          {draftButton}
          {primary}
          <Dropdown label="Ещё действия" items={moreItems} trigger={<MoreHorizontal className="size-4" aria-hidden />}
            triggerClassName="flex size-10 items-center justify-center rounded-lg border border-border bg-surface text-ink-secondary hover:bg-surface-hover" />
        </div>
      </div>

      {backup ? (
        <div className="flex flex-col gap-2 rounded-xl border border-cms-gold/50 bg-cms-gold-soft px-4 py-3 text-sm sm:flex-row sm:items-center">
          <History className="size-5 shrink-0 text-cms-gold-deep" aria-hidden />
          <p className="flex-1 text-ink">Найдены несохранённые изменения от {formatDate(new Date(backup.at), true)}. Восстановить их?</p>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => { writeBackup(storageKey, null); setBackup(null) }}>Отбросить</Button>
            <Button size="sm" onClick={() => { setValues({ ...baseline, ...backup.values }); setBackup(null); showToast('Изменения восстановлены', 'success') }}>Восстановить</Button>
          </div>
        </div>
      ) : null}

      {def.workflow === 'full' && require_approval && !can_approve ? (
        <p className="rounded-xl bg-info-soft px-4 py-2.5 text-sm text-info">Публикует директор или администратор: когда материал готов, отправьте его на согласование.</p>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* Main column — texts in the selected language */}
        <div className="min-w-0 space-y-5">
          <Panel
            title="Содержание"
            description={translatable ? (lang === 'ru' ? 'Основной язык сайта' : `Перевод: ${LANGS.find((l) => l.code === lang)?.name}. Пустое поле — на сайте будет русский текст.`) : undefined}
            actions={translatable ? <LangTabs value={lang} onChange={setLang} filled={fill} /> : undefined}
          >
            <div className="space-y-5">
              {shownMain.map((f) => {
                const name = lang === 'ru' ? f.name : `${f.name}_${lang}`
                const value = String(values[name] ?? '')
                return (
                  <div key={name}>
                    <FieldLabel htmlFor={`f-${name}`} required={lang === 'ru' && f.required}
                      aside={f.max ? <Counter value={value} max={f.max} /> : f.translatable && lang === 'ru' ? <TranslationDots field={f} values={values} /> : undefined}>
                      {f.label}{lang !== 'ru' ? ` (${LANGS.find((l) => l.code === lang)?.label})` : ''}
                    </FieldLabel>
                    <FieldInput field={f} id={`f-${name}`} value={values[name]} onChange={(v) => set(name, v)} choices={[]}
                      placeholder={lang !== 'ru' && !isEmpty(values[f.name]) ? String(values[f.name]).slice(0, 140) : undefined} />
                    {errors[name] ? <p className="mt-1 text-xs text-danger" role="alert">{errors[name]}</p> : null}
                    {f.hint && lang === 'ru' ? <Hint>{f.hint}</Hint> : null}
                  </div>
                )
              })}
              {lang !== 'ru' && !shownMain.length ? <p className="text-sm text-ink-muted">У этого материала нет полей для перевода.</p> : null}
            </div>
          </Panel>

          {def.gallery ? (
            row ? <GalleryManager resource={def.key} row={row} onChange={(r) => { setRow(r); queryClient.setQueryData(['site-cms', def.key, 'item', r.id], r) }} />
              : <Panel title="Дополнительные изображения"><p className="text-sm text-ink-secondary">Галерея станет доступна после первого сохранения — нажмите «Сохранить черновик».</p></Panel>
          ) : null}
        </div>

        {/* Side column — publication, image, parameters, SEO */}
        <aside className="min-w-0 space-y-5">
          {def.workflow ? (
            <Panel title="Публикация">
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between"><span className="text-ink-secondary">Статус</span><StatusBadge state={state} /></div>
                <div>
                  <FieldLabel htmlFor="f-published_at">Дата публикации</FieldLabel>
                  <Input id="f-published_at" type="datetime-local" value={toLocalInput(values.published_at)} onChange={(e) => set('published_at', fromLocalInput(e.target.value))} />
                  <Hint>{scheduled ? 'Материал появится на сайте в это время.' : 'Пусто или прошлая дата — сразу. Дата в будущем — «Запланировано».'}</Hint>
                </div>
                {publicUrl ? (
                  <a href={publicUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline">
                    Открыть на сайте <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                ) : null}
              </div>
            </Panel>
          ) : null}

          {mediaFields.map((f) => (
            <Panel key={f.name} title={f.name === 'cover' ? 'Главное изображение' : f.label}>
              <FieldInput field={f} id={`f-${f.name}`} value={values[f.name]} onChange={(v) => set(f.name, v as ImageValue)} choices={[]}
                current={(row?.[f.name] as string | null) ?? null} />
              {errors[f.name] ? <p className="mt-1 text-xs text-danger" role="alert">{errors[f.name]}</p> : null}
              {f.hint ? <Hint>{f.hint}</Hint> : null}
            </Panel>
          ))}

          {sideFields.length ? (
            <Panel title="Параметры">
              <div className="space-y-4">
                {sideFields.map((f) => (
                  <div key={f.name}>
                    {f.type !== 'boolean' ? <FieldLabel htmlFor={`f-${f.name}`} required={f.required}>{f.label}</FieldLabel> : null}
                    <FieldInput field={f} id={`f-${f.name}`} value={values[f.name]} onChange={(v) => set(f.name, v)} choices={choices(f.choices)} />
                    {f.translatable ? <SideTranslations field={f} values={values} set={set} /> : null}
                    {errors[f.name] ? <p className="mt-1 text-xs text-danger" role="alert">{errors[f.name]}</p> : null}
                    {f.hint ? <Hint>{f.hint}</Hint> : null}
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}

          {def.seo ? <SeoPanel def={def} values={values} set={set} row={row} site={meta.public_site_url} errors={errors} /> : null}
        </aside>
      </div>

      {missing.length ? (
        <p className="flex items-center gap-1.5 text-sm text-ink-secondary"><CircleAlert className="size-4 text-cms-gold-deep" aria-hidden />Чтобы сохранить, заполните: {missing.map((f) => f.label).join(', ')}.</p>
      ) : null}

      {/* Phone / tablet: sticky action bar */}
      {can_edit ? (
        <div className="fixed inset-x-0 bottom-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom))] z-30 border-t border-border bg-surface/95 px-4 py-2.5 backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-page items-center gap-2">
            <Button variant="ghost" className="px-3" aria-label="Предпросмотр" onClick={() => setPreview(true)}><Eye className="size-5" aria-hidden /></Button>
            <div className="flex flex-1 justify-end gap-2 [&>button]:flex-1 sm:[&>button]:flex-none">{draftButton}{primary}</div>
            <Dropdown label="Ещё действия" items={moreItems} trigger={<MoreHorizontal className="size-5" aria-hidden />}
              triggerClassName="flex size-10 items-center justify-center rounded-lg border border-border bg-surface text-ink-secondary" />
          </div>
        </div>
      ) : null}

      <PreviewDialog isOpen={preview} onClose={closePreview} def={def} values={values} row={row} dirty={dirty} lang={lang} meta={meta} choices={choices}
        onSaveAndOpen={async () => {
          await run('save', persist)
        }} />

      <ConfirmDialog isOpen={confirm === 'delete'} title="Удалить материал?" tone="danger" confirmLabel="Удалить" isLoading={busy === 'delete'}
        message="Материал и его фотографии будут удалены безвозвратно. Чтобы только убрать с сайта, используйте «Снять с публикации» или «В архив»."
        onCancel={() => setConfirm(null)}
        onConfirm={() => run('delete', async () => {
          await siteCmsApi.remove(def.key, row!.id)
          writeBackup(storageKey, null)
          setConfirm(null)
          leaving.current = true
          navigate(`${CMS_BASE}/${def.key}`, { replace: true })
        }, 'Удалено')} />
      <ConfirmDialog isOpen={confirm === 'archive'} title="Перенести в архив?" confirmLabel="В архив"
        message="Материал исчезнет с сайта, но останется в CMS — его можно вернуть в черновики и опубликовать снова."
        onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); transition('archive', 'Перенесено в архив') }} />
      <ConfirmDialog isOpen={confirm === 'discard'} title="Отменить изменения?" confirmLabel="Отменить изменения" tone="danger"
        message={row ? 'Форма вернётся к последней сохранённой версии.' : 'Введённые данные будут очищены.'}
        onCancel={() => setConfirm(null)}
        onConfirm={() => { setValues(baseline); writeBackup(storageKey, null); setErrors({}); setConfirm(null); showToast('Изменения отменены', 'info') }} />
      <ConfirmDialog isOpen={blocker.state === 'blocked'} title="Уйти без сохранения?" confirmLabel="Уйти" tone="danger"
        message="Есть несохранённые изменения. Их копия останется в этом браузере — при возврате их можно будет восстановить."
        onCancel={() => blocker.reset?.()} onConfirm={() => blocker.proceed?.()} />
    </div>
  )
}

function SaveIndicator({ state, savedAt, isNew }: { state: SaveState; savedAt: number | null; isNew: boolean }) {
  const map: Record<SaveState, { icon: typeof Cloud; text: string; cls: string }> = {
    idle: { icon: Check, text: isNew ? 'Новый материал — ещё не сохранён' : savedAt ? `Сохранено ${relativeTime(new Date(savedAt))}` : 'Сохранено', cls: 'text-ink-muted' },
    dirty: { icon: Cloud, text: 'Есть изменения — автосохранение через пару секунд', cls: 'text-cms-gold-deep' },
    local: { icon: CloudOff, text: 'Изменения не сохранены (копия — в этом браузере)', cls: 'text-cms-gold-deep' },
    saving: { icon: Loader2, text: 'Сохранение…', cls: 'text-ink-secondary' },
    saved: { icon: Check, text: 'Все изменения сохранены', cls: 'text-emerald-700' },
    error: { icon: CircleAlert, text: 'Не удалось сохранить — проверьте поля', cls: 'text-danger' },
  }
  const { icon: Icon, text, cls } = map[state]
  return <span className={cn('inline-flex items-center gap-1 font-medium', cls)} role="status" aria-live="polite"><Icon className={cn('size-3.5', state === 'saving' && 'animate-spin')} aria-hidden />{text}</span>
}

function TranslationDots({ field, values }: { field: FieldDef; values: Values }) {
  return (
    <span className="flex items-center gap-1 text-[0.6875rem] font-semibold text-ink-muted">
      {(['ky', 'en'] as const).map((l) => (
        <span key={l} className={cn('rounded px-1 py-0.5', isEmpty(values[`${field.name}_${l}`]) ? 'bg-surface-hover' : 'bg-emerald-50 text-emerald-700')}>
          {l === 'ky' ? 'KG' : 'EN'}
        </span>
      ))}
    </span>
  )
}

/** Short translatable values in the side card (position, duration…). */
function SideTranslations({ field, values, set }: { field: FieldDef; values: Values; set: (name: string, v: unknown) => void }) {
  return (
    <div className="mt-2 grid grid-cols-2 gap-2">
      {(['ky', 'en'] as const).map((l) => (
        <Input key={l} aria-label={`${field.label} (${l === 'ky' ? 'кыргызча' : 'English'})`} placeholder={l === 'ky' ? 'KG' : 'EN'} className="h-9 text-sm"
          value={String(values[`${field.name}_${l}`] ?? '')} onChange={(e) => set(`${field.name}_${l}`, e.target.value)} />
      ))}
    </div>
  )
}

function SeoPanel({ def, values, set, row, site, errors }: { def: ResourceDef; values: Values; set: (n: string, v: unknown) => void; row: Row | null; site: string | null; errors: Record<string, string> }) {
  const title = String(values.seo_title ?? '')
  const desc = String(values.seo_description ?? '')
  const fallbackTitle = String(values[def.titleField] ?? values.name ?? '')
  const fallbackDesc = def.excerptField ? String(values[def.excerptField] ?? '').replace(/\s+/g, ' ') : ''
  const host = (site ?? 'okurmenkids.kg').replace(/^https?:\/\//, '')
  const path = `${def.publicPath ?? `/${def.key}`}/${String(row?.slug ?? values.slug ?? '') || '…'}`
  return (
    <Panel title="SEO" description="Как материал выглядит в поиске и соцсетях">
      <div className="space-y-4">
        <div className="rounded-xl border border-border bg-surface-muted p-3" aria-label="Предпросмотр в поиске">
          <p className="truncate text-xs text-emerald-700">{host}{path}</p>
          <p className="mt-0.5 line-clamp-2 text-[0.9375rem] leading-snug font-medium text-[#1a0dab]">{(title || fallbackTitle || 'Заголовок страницы')} — Okurmen Kids</p>
          <p className="mt-1 line-clamp-2 text-xs text-ink-secondary">{desc || fallbackDesc || 'Описание страницы для поисковиков.'}</p>
        </div>
        <div>
          <FieldLabel htmlFor="f-seo_title" aside={<Counter value={title} max={60} />}>SEO title</FieldLabel>
          <Input id="f-seo_title" value={title} maxLength={70} onChange={(e) => set('seo_title', e.target.value)} placeholder={fallbackTitle.slice(0, 70)} />
          {errors.seo_title ? <p className="mt-1 text-xs text-danger">{errors.seo_title}</p> : null}
        </div>
        <div>
          <FieldLabel htmlFor="f-seo_description" aside={<Counter value={desc} max={160} />}>SEO description</FieldLabel>
          <Textarea id="f-seo_description" rows={3} value={desc} maxLength={200} onChange={(e) => set('seo_description', e.target.value)} placeholder={fallbackDesc.slice(0, 160)} />
          {errors.seo_description ? <p className="mt-1 text-xs text-danger">{errors.seo_description}</p> : null}
        </div>
        <Hint>Пусто — берутся название и краткое описание. SEO-поля — для русской версии; KG и EN используют переведённые тексты.</Hint>
      </div>
    </Panel>
  )
}

// ----- preview ---------------------------------------------------------------

function PreviewDialog({ isOpen, onClose, def, values, row, dirty, lang: initialLang, meta, choices, onSaveAndOpen }: {
  isOpen: boolean
  onClose: () => void
  def: ResourceDef
  values: Values
  row: Row | null
  dirty: boolean
  lang: Lang
  meta: SiteMeta
  choices: (source?: string) => Choice[]
  onSaveAndOpen: () => Promise<void>
}) {
  const [lang, setLang] = useState<Lang>(initialLang)
  const [device, setDevice] = useState<'desktop' | 'mobile'>('desktop')
  useEffect(() => { if (isOpen) setLang(initialLang) }, [isOpen, initialLang])
  const t = (name: string) => {
    const translated = lang === 'ru' ? '' : String(values[`${name}_${lang}`] ?? '')
    return translated.trim() ? translated : String(values[name] ?? '')
  }
  const coverField = def.fields.find((f) => f.type === 'image')
  const coverValue = coverField ? values[coverField.name] : undefined
  const cover = useMemo(() => {
    if (coverValue instanceof File) return URL.createObjectURL(coverValue)
    if (coverValue && typeof coverValue === 'object' && 'preview' in coverValue) return (coverValue as { preview: string }).preview
    if (coverValue === null) return null
    return coverField ? (row?.[coverField.name] as string | null) ?? null : null
  }, [coverValue, coverField, row])
  useEffect(() => () => { if (cover?.startsWith('blob:')) URL.revokeObjectURL(cover) }, [cover])
  if (!isOpen) return null

  const bodyField = def.fields.find((f) => f.type === 'richtext' || (f.type === 'textarea' && f.name === 'text') || f.name === 'bio')
  const category = def.categoryField ? choices(def.fields.find((f) => f.name === def.categoryField)?.choices).find((c) => c.value === String(values[def.categoryField!]))?.label : ''
  const date = def.dateField ? formatDate(values[def.dateField], def.dateField !== 'date') : ''
  const title = def.titleField === 'display_name' ? String(values.name || row?.display_name || '') : t(def.titleField)
  const excerpt = def.excerptField && def.excerptField !== bodyField?.name ? t(def.excerptField) : ''
  const sitePreview = (row?.preview as { url: string | null } | undefined)?.url
  const siteLink = sitePreview ? (lang === 'ru' ? sitePreview : sitePreview.replace('/preview/', `/${lang}/preview/`)) : null
  const photos = (row?.photos as { id: number; thumb: string; caption: string }[] | undefined) ?? []
  const draft = !row || ['draft', 'review'].includes(String(row.workflow_state))

  return (
    <Modal isOpen onClose={onClose} title="Предпросмотр" size="xl" icon={<Eye className="size-5 text-brand-600" aria-hidden />}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <LangTabs value={lang} onChange={setLang} />
          <div role="group" aria-label="Ширина экрана" className="inline-flex rounded-xl border border-border bg-surface-muted p-1 text-sm">
            {(['desktop', 'mobile'] as const).map((d) => (
              <button key={d} type="button" aria-pressed={device === d} onClick={() => setDevice(d)}
                className={cn('h-8 rounded-lg px-3 font-medium', device === d ? 'bg-surface text-brand-600 shadow-sm' : 'text-ink-secondary')}>
                {d === 'desktop' ? 'Компьютер' : 'Телефон'}
              </button>
            ))}
          </div>
        </div>
        {dirty ? <p className="rounded-lg bg-cms-gold-soft px-3 py-2 text-xs text-cms-gold-deep">Показаны несохранённые изменения из формы.</p> : null}
        <div className="rounded-2xl bg-surface-muted p-3 sm:p-5">
          <article className={cn('mx-auto overflow-hidden rounded-2xl bg-white shadow-sm transition-all', device === 'mobile' ? 'max-w-[380px]' : 'max-w-3xl')}>
            {cover ? <img src={cover} alt="" className="aspect-[16/9] w-full object-cover" /> : null}
            <div className="space-y-3 p-5 sm:p-7">
              {category || date ? (
                <p className="flex flex-wrap items-center gap-2 text-xs font-semibold tracking-wide text-brand-600 uppercase">
                  {category ? <span className="rounded-full bg-brand-50 px-2.5 py-1">{category}</span> : null}{date ? <span className="text-ink-muted">{date}</span> : null}
                </p>
              ) : null}
              <h2 className="font-display text-2xl leading-tight font-extrabold text-brand-700 sm:text-3xl">{title || 'Без названия'}</h2>
              {def.key === 'team' && values.position ? <p className="font-medium text-ink-secondary">{t('position')}</p> : null}
              {excerpt ? <p className="text-base text-ink-secondary">{excerpt}</p> : null}
              {bodyField ? (
                <div className="text-[0.9375rem] leading-relaxed text-ink">
                  {bodyField.type === 'richtext' ? <MarkupPreview blocks={parseMarkup(t(bodyField.name))} /> : <p className="whitespace-pre-line">{t(bodyField.name)}</p>}
                </div>
              ) : null}
              {photos.length ? (
                <div className="grid grid-cols-3 gap-2 pt-2">{photos.slice(0, 6).map((p) => <img key={p.id} src={p.thumb} alt={p.caption} className="aspect-square rounded-lg object-cover" />)}</div>
              ) : null}
            </div>
          </article>
        </div>
        <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-end">
          <p className="text-xs text-ink-muted sm:mr-auto">{siteLink ? 'Ссылка-предпросмотр действует 7 дней и показывает сохранённую версию.' : 'Предпросмотр на сайте появится после первого сохранения.'}</p>
          {meta.permissions.can_edit && (dirty || !row) && draft ? (
            <Button variant="secondary" leftIcon={<Save className="size-4" aria-hidden />} onClick={onSaveAndOpen}>Сохранить черновик</Button>
          ) : null}
          {siteLink ? <a href={siteLink} target="_blank" rel="noreferrer" className={linkButton('primary')}><ExternalLink className="size-4" aria-hidden />Открыть на сайте</a> : null}
        </div>
      </div>
    </Modal>
  )
}

// ----- gallery ---------------------------------------------------------------

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
  const [picker, setPicker] = useState(false)
  const [remove, setRemove] = useState<Photo | null>(null)
  const photos = useMemo(() => (row.photos as Photo[] | undefined) ?? [], [row.photos])
  const call = async (task: () => Promise<Row>, success?: string) => {
    try {
      onChange(await task())
      await invalidate()
      if (success) showToast(success, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  const upload = async (files: File[]) => {
    if (!files.length) return
    setUploading(true)
    await call(() => siteCmsApi.addPhotos(resource, row.id, files.slice(0, 40)), `Добавлено фото: ${Math.min(files.length, 40)}`)
    setUploading(false)
  }
  return (
    <Panel title={<>Дополнительные изображения <span className="font-normal text-ink-muted">({photos.length})</span></>} description="Галерея на странице материала"
      actions={
        <>
          <Button size="sm" variant="secondary" leftIcon={<ImagePlus className="size-4" aria-hidden />} onClick={() => setPicker(true)}>Медиатека</Button>
          <label className={cn('inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600 focus-within:outline-2 focus-within:outline-brand-700', uploading && 'pointer-events-none opacity-60')}>
            {uploading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Upload className="size-4" aria-hidden />}
            <span className="hidden sm:inline">{uploading ? 'Загрузка…' : 'Загрузить'}</span>
            <input type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Загрузить фото в галерею"
              onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; upload(f) }} />
          </label>
        </>
      }>
      {photos.length ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          {photos.map((p) => (
            <li key={p.id} className="overflow-hidden rounded-xl border border-border">
              <a href={p.url} target="_blank" rel="noreferrer" aria-label="Открыть фото"><img src={p.thumb} alt={p.caption} className="aspect-[4/3] w-full object-cover" loading="lazy" /></a>
              <div className="space-y-1.5 p-2">
                <Input aria-label="Подпись" defaultValue={p.caption} placeholder="Подпись" className="h-8 text-xs"
                  onBlur={(e) => e.target.value !== p.caption && call(() => siteCmsApi.updatePhoto(resource, row.id, p.id, { caption: e.target.value }))} />
                <div className="flex items-center gap-1">
                  <Input aria-label="Порядок" type="number" min={0} defaultValue={p.order} className="h-8 w-16 text-xs"
                    onBlur={(e) => Number(e.target.value) !== p.order && call(() => siteCmsApi.updatePhoto(resource, row.id, p.id, { order: Number(e.target.value) }))} />
                  <button type="button" onClick={() => setRemove(p)} className="ml-auto grid size-8 place-items-center rounded-md text-ink-secondary hover:bg-danger-soft hover:text-danger" aria-label="Удалить фото">
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <label className="flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-border bg-surface-muted px-4 py-8 text-center hover:border-brand-200"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(Array.from(e.dataTransfer.files)) }}>
          <ImagePlus className="size-7 text-ink-muted" aria-hidden />
          <span className="mt-2 text-sm font-medium text-ink">Перетащите фото сюда или нажмите, чтобы выбрать</span>
          <span className="text-xs text-ink-muted">Можно сразу несколько (до 40) — JPEG, PNG, WebP</span>
          <input type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; upload(f) }} />
        </label>
      )}
      <MediaPicker isOpen={picker} multiple onClose={() => setPicker(false)}
        onPickMany={(assets) => { setPicker(false); call(() => siteCmsApi.addLibraryPhotos(resource, row.id, assets.map((a) => a.id!).filter(Boolean)), `Добавлено фото: ${assets.length}`) }} />
      <ConfirmDialog isOpen={remove !== null} title="Удалить фото?" message="Фото исчезнет из галереи на сайте." confirmLabel="Удалить" tone="danger"
        onCancel={() => setRemove(null)} onConfirm={() => { const p = remove!; setRemove(null); call(() => siteCmsApi.deletePhoto(resource, row.id, p.id), 'Фото удалено') }} />
    </Panel>
  )
}
