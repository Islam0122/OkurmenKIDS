import { useState } from 'react'
import { Copy, FileText, Film, FolderPlus, Link2, RefreshCw, Trash2, Upload, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, type Row } from './api'
import { UploadZone } from './MediaPicker'
import { CmsPage, fileExt, formatDate, formatSize, Skeleton } from './ui'

const PAGE_SIZE = 48
const KIND_TITLE = { '': 'Медиатека', image: 'Изображения', video: 'Видео' } as const
const KIND_OPTIONS = [{ value: 'image', label: 'Изображения' }, { value: 'video', label: 'Видео' }, { value: 'document', label: 'Документы (PDF)' }]
const ACCEPT = { '': 'image/*,video/mp4,video/webm,video/quicktime,application/pdf', image: 'image/jpeg,image/png,image/webp,image/gif,image/svg+xml', video: 'video/mp4,video/webm,video/quicktime' }

/** /marketing/site/media (+ /images, /videos) — библиотека файлов сайта. */
export function MediaLibraryPage({ kind: preset = '' }: { kind?: '' | 'image' | 'video' }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [kindFilter, setKind] = useState('')
  const kind = preset || kindFilter
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<Row | null>(null)
  const [folderDialog, setFolderDialog] = useState(false)
  const uploading = params.get('upload') === '1'
  const folders = useSiteList('media-categories', {})
  const query = useSiteList('media', { search: search || undefined, kind: kind || undefined, category: category || undefined, page, page_size: PAGE_SIZE })
  const { rows, count } = toList(query.data)
  const folderRows = toList(folders.data).rows
  const folderOptions = folderRows.map((f) => ({ value: String(f.id), label: `${f.name} (${f.count})` }))
  const showUpload = (on: boolean) => { if (on) params.set('upload', '1'); else params.delete('upload'); setParams(params, { replace: true }) }

  const copy = (text: string, message: string) => navigator.clipboard?.writeText(text).then(() => showToast(message, 'success'), () => showToast('Не удалось скопировать', 'error'))

  return (
    <CmsPage title={KIND_TITLE[preset]}
      description={preset === 'video' ? 'Видеофайлы сайта (MP4, WebM). Видео с YouTube вставляется в текст ссылкой.' : 'Фото и файлы сайта: загружайте, ищите, копируйте прямые ссылки и выбирайте в редакторе материалов.'}
      actions={
        <>
          <Button variant="secondary" leftIcon={<FolderPlus className="size-4" aria-hidden />} onClick={() => setFolderDialog(true)}>Папка</Button>
          <Button leftIcon={uploading ? <X className="size-4" aria-hidden /> : <Upload className="size-4" aria-hidden />} onClick={() => showUpload(!uploading)}>{uploading ? 'Скрыть загрузку' : 'Загрузить'}</Button>
        </>
      }>
      {uploading ? <UploadZone folder={category} accept={ACCEPT[preset]} onUploaded={() => setPage(1)} /> : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Поиск по названию и описанию" /></div>
        {!preset ? <div className="sm:w-48"><Select aria-label="Тип" value={kindFilter} placeholder="Все типы" options={KIND_OPTIONS} onChange={(e) => { setKind(e.target.value); setPage(1) }} /></div> : null}
        {count ? <span className="text-sm text-ink-muted sm:ml-auto">Файлов: {count}</span> : null}
      </div>

      {folderRows.length ? (
        <div className="scroll-x -mx-4 flex gap-1.5 px-4 sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="Папки">
          {[{ value: '', label: 'Все папки' }, ...folderOptions].map((f) => (
            <button key={f.value} type="button" aria-pressed={category === f.value} onClick={() => { setCategory(f.value); setPage(1) }}
              className={cn('h-8 shrink-0 rounded-full px-3 text-sm font-medium', category === f.value ? 'bg-brand-500 text-white' : 'bg-surface text-ink-secondary ring-1 ring-border hover:text-ink')}>
              {f.label}
            </button>
          ))}
        </div>
      ) : null}

      {query.isPending ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">{Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="aspect-[4/5] rounded-xl" />)}</div>
      ) : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {rows.map((row) => (
              <li key={row.id} className="group relative">
                <button type="button" onClick={() => setOpen(row)} className="block w-full overflow-hidden rounded-xl border border-border bg-surface text-left transition hover:border-brand-500 hover:shadow-md">
                  <Thumb row={row} />
                  <span className="block truncate px-2.5 pt-2 text-xs font-medium text-ink">{String(row.title)}</span>
                  <span className="block px-2.5 pb-2 text-[0.6875rem] text-ink-muted">{fileExt(String(row.url))} · {formatSize(Number(row.size))}</span>
                </button>
                <button type="button" onClick={() => copy(String(row.url), 'Прямая ссылка скопирована')} aria-label={`Копировать ссылку на «${String(row.title)}»`}
                  className="absolute top-2 right-2 grid size-8 place-items-center rounded-lg bg-white/90 text-ink-secondary opacity-100 shadow-sm hover:text-brand-600 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100">
                  <Link2 className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : (
        <EmptyState title={search || category || kindFilter ? 'Ничего не найдено' : 'Файлов пока нет'}
          description={search || category || kindFilter ? 'Измените поиск или папку.' : 'Загрузите фото и видео академии — их можно выбирать как обложки, добавлять в галереи и вставлять в тексты.'}
          action={!uploading ? <Button leftIcon={<Upload className="size-4" aria-hidden />} onClick={() => showUpload(true)}>Загрузить файлы</Button> : undefined} />
      )}

      {open ? <AssetDialog row={open} folders={folderOptions} onClose={() => setOpen(null)} copy={copy} /> : null}
      <FolderDialog isOpen={folderDialog} onClose={() => setFolderDialog(false)} onCreated={async () => { await invalidate() }} />
    </CmsPage>
  )
}

function Thumb({ row, large }: { row: Row; large?: boolean }) {
  const url = String(row.url)
  if (row.kind === 'image') return <img src={url} alt={String(row.alt || row.title)} loading="lazy" className={cn('w-full bg-surface-muted', large ? 'max-h-[50vh] object-contain' : 'aspect-square object-cover')} />
  if (row.kind === 'video') return large ? <video src={url} controls className="max-h-[50vh] w-full bg-black" /> : <div className="grid aspect-square place-items-center bg-surface-muted"><Film className="size-8 text-ink-muted" aria-hidden /></div>
  return <div className="grid aspect-square place-items-center bg-surface-muted"><FileText className="size-8 text-ink-muted" aria-hidden /></div>
}

function FolderDialog({ isOpen, onClose, onCreated }: { isOpen: boolean; onClose: () => void; onCreated: () => Promise<void> }) {
  const { showToast } = useToast()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Новая папка">
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault()
        if (!name.trim()) return
        setBusy(true)
        try {
          await siteCmsApi.save('media-categories', null, { name: name.trim() })
          await onCreated()
          showToast('Папка создана', 'success')
          setName('')
          onClose()
        } catch (error) {
          showToast(extractErrorMessage(error), 'error')
        } finally {
          setBusy(false)
        }
      }}>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-ink">Название</span><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Хакатон 2026" autoFocus maxLength={80} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Отмена</Button><Button type="submit" isLoading={busy} disabled={!name.trim()}>Создать</Button></div>
      </form>
    </Modal>
  )
}

function AssetDialog({ row, folders, onClose, copy }: { row: Row; folders: { value: string; label: string }[]; onClose: () => void; copy: (text: string, msg: string) => void }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [title, setTitle] = useState(String(row.title))
  const [alt, setAlt] = useState(String(row.alt ?? ''))
  const [category, setCategory] = useState(row.category ? String(row.category) : '')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const url = String(row.url)
  const act = async (task: () => Promise<unknown>, message: string, close = false) => {
    setBusy(true)
    try {
      await task()
      await invalidate()
      showToast(message, 'success')
      if (close) onClose()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal isOpen onClose={onClose} title={String(row.title)} size="xl">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="grid place-items-center overflow-hidden rounded-xl border border-border bg-surface-muted"><Thumb row={row} large /></div>
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 rounded-xl bg-surface-muted p-3 text-xs">
            <div><dt className="text-ink-muted">Формат</dt><dd className="font-medium text-ink">{fileExt(url)}</dd></div>
            <div><dt className="text-ink-muted">Размер</dt><dd className="font-medium text-ink">{formatSize(Number(row.size))}</dd></div>
            <div><dt className="text-ink-muted">Загружен</dt><dd className="font-medium text-ink">{formatDate(row.created_at, true)}</dd></div>
            <div><dt className="text-ink-muted">Кем</dt><dd className="truncate font-medium text-ink">{String(row.uploaded_by_name ?? '—')}</dd></div>
          </dl>
          <div>
            <span className="mb-1.5 block text-sm font-medium text-ink">Прямой URL</span>
            <div className="flex gap-2">
              <Input readOnly value={url} aria-label="Прямой URL файла" className="text-xs" onFocus={(e) => e.target.select()} />
              <Button variant="secondary" aria-label="Копировать прямой URL" onClick={() => copy(url, 'Прямой URL скопирован')}><Copy className="size-4" aria-hidden /></Button>
            </div>
            {row.kind === 'image' ? (
              <button type="button" onClick={() => copy(`![${alt || title}](${url})`, 'Ссылка для текста скопирована')} className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline">
                <Link2 className="size-3.5" aria-hidden /> Копировать ссылку для вставки в текст
              </button>
            ) : null}
          </div>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-ink">Название</span><Input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-ink">Папка</span><Select value={category} placeholder="Без папки" options={folders} onChange={(e) => setCategory(e.target.value)} /></label>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-ink">Описание (alt)</span><Input value={alt} onChange={(e) => setAlt(e.target.value)} placeholder="Что изображено — для незрячих и поисковиков" /></label>
        </div>
      </div>
      <div className="mt-5 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
        <Button variant="ghost" className="text-danger sm:mr-auto" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirm(true)}>Удалить</Button>
        <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-brand-200 px-4 text-sm font-medium text-brand-700 hover:bg-brand-50 focus-within:outline-2 focus-within:outline-brand-500">
          <RefreshCw className="size-4" aria-hidden /> Заменить файл
          <input type="file" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (file) act(() => siteCmsApi.save('media', row.id, { file }), 'Файл заменён', true) }} />
        </label>
        <Button isLoading={busy} onClick={() => act(() => siteCmsApi.save('media', row.id, { title, alt, category: category ? Number(category) : null }), 'Сохранено', true)}>Сохранить</Button>
      </div>
      <ConfirmDialog isOpen={confirm} title="Удалить файл?" tone="danger" confirmLabel="Удалить"
        message="Обложки и галереи, выбранные из медиатеки, хранят свою копию и не пострадают. Но если файл вставлен в текст ссылкой, там останется пустое место."
        onCancel={() => setConfirm(false)} onConfirm={() => act(() => siteCmsApi.remove('media', row.id), 'Файл удалён', true)} />
    </Modal>
  )
}
