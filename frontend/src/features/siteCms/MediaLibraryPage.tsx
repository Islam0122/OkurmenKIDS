import { useState } from 'react'
import { Copy, FileText, FolderPlus, Film, RefreshCw, Trash2, Upload } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, useSiteMeta, type Row } from './api'

const PAGE_SIZE = 48
const size = (bytes: number) => (bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`)

/** /marketing/site/media — загрузка, папки, поиск, просмотр, замена и удаление файлов сайта. */
export function MediaLibraryPage() {
  const { showToast } = useToast()
  const meta = useSiteMeta()
  const invalidate = useSiteInvalidate()
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('')
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const [uploading, setUploading] = useState(false)
  const [open, setOpen] = useState<Row | null>(null)
  const folders = useSiteList('media-categories', {})
  const query = useSiteList('media', { search: search || undefined, kind: kind || undefined, category: category || undefined, page, page_size: PAGE_SIZE })
  const { rows, count } = toList(query.data)
  const folderOptions = toList(folders.data).rows.map((f) => ({ value: String(f.id), label: `${f.name} (${f.count})` }))

  const upload = async (files: File[]) => {
    setUploading(true)
    let ok = 0
    for (const file of files) {
      try {
        await siteCmsApi.save('media', null, { file, ...(category ? { category: Number(category) } : {}) })
        ok++
      } catch (error) {
        showToast(`${file.name}: ${extractErrorMessage(error)}`, 'error')
      }
    }
    setUploading(false)
    await invalidate()
    if (ok) showToast(`Загружено файлов: ${ok}`, 'success')
  }

  const newFolder = async () => {
    const name = window.prompt('Название папки')
    if (!name?.trim()) return
    try {
      await siteCmsApi.save('media-categories', null, { name: name.trim() })
      await invalidate()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Медиатека" description="Фото и видео для сайта. Изображения из медиатеки вставляются в текст новостей и мероприятий кнопкой «Изображение»."
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" leftIcon={<FolderPlus className="size-4" aria-hidden />} onClick={newFolder}>Папка</Button>
            <label className={cn('inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600', uploading && 'pointer-events-none opacity-60')}>
              <Upload className="size-4" aria-hidden /> {uploading ? 'Загрузка…' : 'Загрузить'}
              <input type="file" multiple accept="image/*,video/mp4,video/webm,video/quicktime,application/pdf" className="sr-only"
                onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; if (f.length) upload(f) }} />
            </label>
          </div>
        } />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Поиск по названию" /></div>
        <div className="sm:w-44"><Select aria-label="Тип" value={kind} placeholder="Все типы" options={meta.data?.choices.media_kind ?? []} onChange={(e) => { setKind(e.target.value); setPage(1) }} /></div>
        <div className="sm:w-56"><Select aria-label="Папка" value={category} placeholder="Все папки" options={folderOptions} onChange={(e) => { setCategory(e.target.value); setPage(1) }} /></div>
      </div>
      {query.isPending ? <LoadingState /> : rows.length ? (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {rows.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setOpen(row)} className="block w-full overflow-hidden rounded-lg border border-border bg-surface text-left hover:border-brand-500">
                  <Thumb row={row} />
                  <span className="block truncate px-2 pt-1.5 text-xs font-medium text-ink">{String(row.title)}</span>
                  <span className="block px-2 pb-1.5 text-[11px] text-ink-muted">{size(Number(row.size))}</span>
                </button>
              </li>
            ))}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : <EmptyState title="Файлов нет" description="Загрузите фото и видео академии — их можно будет вставлять в материалы сайта." />}
      {open ? <AssetDialog row={open} folders={folderOptions} onClose={() => setOpen(null)} /> : null}
    </div>
  )
}

function Thumb({ row, large }: { row: Row; large?: boolean }) {
  const url = String(row.url)
  if (row.kind === 'image') return <img src={url} alt={String(row.alt || row.title)} loading="lazy" className={cn('w-full bg-surface-muted object-cover', large ? 'max-h-[50vh] object-contain' : 'aspect-square')} />
  if (row.kind === 'video') return large ? <video src={url} controls className="max-h-[50vh] w-full" /> : <div className="grid aspect-square place-items-center bg-surface-muted"><Film className="size-8 text-ink-muted" aria-hidden /></div>
  return <div className="grid aspect-square place-items-center bg-surface-muted"><FileText className="size-8 text-ink-muted" aria-hidden /></div>
}

function AssetDialog({ row, folders, onClose }: { row: Row; folders: { value: string; label: string }[]; onClose: () => void }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [title, setTitle] = useState(String(row.title))
  const [alt, setAlt] = useState(String(row.alt ?? ''))
  const [category, setCategory] = useState(row.category ? String(row.category) : '')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)
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
    <Modal isOpen onClose={onClose} title={String(row.title)} size="lg">
      <div className="space-y-4">
        <div className="overflow-hidden rounded-lg border border-border"><Thumb row={row} large /></div>
        <div className="flex items-center gap-2">
          <Input readOnly value={String(row.url)} aria-label="Ссылка на файл" className="text-xs" />
          <Button variant="secondary" leftIcon={<Copy className="size-4" aria-hidden />} onClick={() => navigator.clipboard.writeText(String(row.url)).then(() => showToast('Ссылка скопирована', 'success'))}>Копировать</Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="field-label">Название</span><Input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="block"><span className="field-label">Папка</span><Select value={category} placeholder="Без папки" options={folders} onChange={(e) => setCategory(e.target.value)} /></label>
          <label className="block sm:col-span-2"><span className="field-label">Описание для незрячих (alt)</span><Input value={alt} onChange={(e) => setAlt(e.target.value)} placeholder="Что изображено на фото" /></label>
        </div>
        <p className="text-xs text-ink-muted">{String(row.uploaded_by_name ?? '')} · {new Date(String(row.created_at)).toLocaleString('ru-RU')} · {size(Number(row.size))}</p>
        <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
          <Button variant="ghost" className="text-danger sm:mr-auto" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirm(true)}>Удалить</Button>
          <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-brand-200 px-4 text-sm font-medium text-brand-700 hover:bg-brand-50">
            <RefreshCw className="size-4" aria-hidden /> Заменить файл
            <input type="file" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (file) act(() => siteCmsApi.save('media', row.id, { file }), 'Файл заменён', true) }} />
          </label>
          <Button isLoading={busy} onClick={() => act(() => siteCmsApi.save('media', row.id, { title, alt, category: category ? Number(category) : null }), 'Сохранено', true)}>Сохранить</Button>
        </div>
      </div>
      <ConfirmDialog isOpen={confirm} title="Удалить файл?" message="Если файл вставлен в тексты сайта, там останется пустое место." confirmLabel="Удалить" tone="danger"
        onCancel={() => setConfirm(false)} onConfirm={() => act(() => siteCmsApi.remove('media', row.id), 'Файл удалён', true)} />
    </Modal>
  )
}
