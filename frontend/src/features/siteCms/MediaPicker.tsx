import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ImagePlus, Link2, Upload } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, type Row } from './api'
import { Skeleton } from './ui'

export interface PickedAsset {
  /** Media library id; absent for a direct link. */
  id?: number
  url: string
  title: string
  alt: string
}

type Tab = 'library' | 'upload' | 'url'

/**
 * Выбор изображения: из медиатеки (поиск, папки), загрузка новых файлов
 * (сразу попадают в медиатеку) или прямая ссылка. `multiple` — выбор
 * нескольких фото для галереи.
 */
export function MediaPicker({ isOpen, onClose, onPick, onPickMany, multiple, allowUrl = !multiple, title }: {
  isOpen: boolean
  onClose: () => void
  onPick?: (asset: PickedAsset) => void
  onPickMany?: (assets: PickedAsset[]) => void
  multiple?: boolean
  allowUrl?: boolean
  title?: string
}) {
  const [tab, setTab] = useState<Tab>('library')
  const [search, setSearch] = useState('')
  const [folder, setFolder] = useState('')
  const [selected, setSelected] = useState<PickedAsset[]>([])
  useEffect(() => {
    if (isOpen) {
      setSelected([])
      setTab('library')
    }
  }, [isOpen])
  const folders = useSiteList('media-categories', {}, isOpen)
  const query = useSiteList('media', { kind: 'image', search: search || undefined, category: folder || undefined, page_size: 60 }, isOpen)
  const { rows } = toList(query.data)
  if (!isOpen) return null

  const asset = (row: Row): PickedAsset => ({ id: row.id, url: String(row.url), title: String(row.title), alt: String(row.alt ?? '') })
  const choose = (picked: PickedAsset) => {
    if (multiple) {
      setSelected((prev) => (prev.some((p) => p.id === picked.id) ? prev.filter((p) => p.id !== picked.id) : [...prev, picked]))
      return
    }
    onPick?.(picked)
  }
  const tabs: { key: Tab; label: string; icon: typeof Upload }[] = [
    { key: 'library', label: 'Медиатека', icon: ImagePlus },
    { key: 'upload', label: 'Загрузить', icon: Upload },
    ...(allowUrl ? [{ key: 'url' as const, label: 'По ссылке', icon: Link2 }] : []),
  ]

  return (
    <Modal isOpen onClose={onClose} title={title ?? (multiple ? 'Выберите фотографии' : 'Выберите изображение')} size="xl" icon={<ImagePlus className="size-5 text-brand-600" aria-hidden />}>
      <div className="space-y-4">
        <div role="tablist" aria-label="Источник изображения" className="flex gap-1 rounded-xl bg-surface-muted p-1">
          {tabs.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
              className={cn('inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-lg text-sm font-medium', tab === t.key ? 'bg-surface text-brand-600 shadow-sm' : 'text-ink-secondary hover:text-ink')}>
              <t.icon className="size-4" aria-hidden /><span className="hidden sm:inline">{t.label}</span><span className="sm:hidden">{t.label.split(' ')[0]}</span>
            </button>
          ))}
        </div>

        {tab === 'library' ? (
          <>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="flex-1"><SearchInput value={search} onChange={setSearch} placeholder="Поиск по названию" /></div>
              <div className="sm:w-56">
                <Select aria-label="Папка" value={folder} placeholder="Все папки" onChange={(e) => setFolder(e.target.value)}
                  options={toList(folders.data).rows.map((f) => ({ value: String(f.id), label: `${f.name} (${f.count})` }))} />
              </div>
            </div>
            {query.isPending ? (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="aspect-square rounded-lg" />)}</div>
            ) : rows.length ? (
              <ul className="grid max-h-[52vh] grid-cols-3 gap-2 overflow-y-auto p-0.5 sm:grid-cols-5" aria-label="Изображения медиатеки">
                {rows.map((row) => {
                  const on = selected.some((s) => s.id === row.id)
                  return (
                    <li key={row.id}>
                      <button type="button" onClick={() => choose(asset(row))} aria-pressed={multiple ? on : undefined}
                        className={cn('group relative block w-full overflow-hidden rounded-lg border-2 text-left transition',
                          on ? 'border-brand-500 ring-2 ring-brand-200' : 'border-transparent hover:border-brand-200')}>
                        <img src={String(row.url)} alt={String(row.alt || row.title)} className="aspect-square w-full bg-surface-muted object-cover" loading="lazy" />
                        <span className="block truncate px-1.5 py-1 text-xs text-ink">{String(row.title)}</span>
                        {on ? <span className="absolute top-1.5 right-1.5 grid size-6 place-items-center rounded-full bg-brand-500 text-white"><Check className="size-4" aria-hidden /></span> : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <div className="rounded-xl border border-dashed border-border py-10 text-center">
                <p className="text-sm font-medium text-ink">{search || folder ? 'Ничего не найдено' : 'В медиатеке пока нет изображений'}</p>
                <button type="button" onClick={() => setTab('upload')} className="mt-2 text-sm font-medium text-brand-600 hover:underline">Загрузить фотографии</button>
              </div>
            )}
          </>
        ) : null}

        {tab === 'upload' ? <UploadZone multiple={multiple} folder={folder} onUploaded={(assets) => {
          if (multiple) {
            setSelected((prev) => [...prev, ...assets])
            setTab('library')
          } else if (assets[0]) {
            onPick?.(assets[0])
          }
        }} /> : null}

        {tab === 'url' ? <UrlTab onPick={(a) => onPick?.(a)} /> : null}

        {multiple ? (
          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-end">
            <span className="text-sm text-ink-secondary sm:mr-auto">Выбрано: {selected.length}</span>
            <Button variant="ghost" onClick={onClose}>Отмена</Button>
            <Button disabled={!selected.length} onClick={() => onPickMany?.(selected)}>Добавить {selected.length ? `(${selected.length})` : ''}</Button>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}

/** Drag-and-drop / file chooser upload into the media library. */
export function UploadZone({ multiple = true, folder, onUploaded, accept = 'image/jpeg,image/png,image/webp,image/gif', compact }: {
  multiple?: boolean
  folder?: string
  onUploaded?: (assets: PickedAsset[]) => void
  accept?: string
  compact?: boolean
}) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)

  const upload = async (files: File[]) => {
    if (!files.length) return
    setProgress({ done: 0, total: files.length })
    const uploaded: PickedAsset[] = []
    for (const [index, file] of files.entries()) {
      try {
        const row = await siteCmsApi.save('media', null, { file, ...(folder ? { category: Number(folder) } : {}) })
        uploaded.push({ id: row.id, url: String(row.url), title: String(row.title), alt: String(row.alt ?? '') })
      } catch (error) {
        showToast(`${file.name}: ${extractErrorMessage(error)}`, 'error')
      }
      setProgress({ done: index + 1, total: files.length })
    }
    setProgress(null)
    await invalidate()
    if (uploaded.length) {
      showToast(uploaded.length === 1 ? 'Файл загружен в медиатеку' : `Загружено файлов: ${uploaded.length}`, 'success')
      onUploaded?.(uploaded)
    }
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); upload(Array.from(e.dataTransfer.files).slice(0, multiple ? 40 : 1)) }}
      className={cn('flex flex-col items-center justify-center rounded-2xl border-2 border-dashed text-center transition-colors',
        compact ? 'px-4 py-5' : 'px-4 py-10', over ? 'border-brand-500 bg-brand-50' : 'border-border bg-surface-muted')}
    >
      <span className="grid size-11 place-items-center rounded-full bg-brand-50 text-brand-600"><Upload className="size-5" aria-hidden /></span>
      {progress ? (
        <div className="mt-3 w-full max-w-xs" role="status">
          <p className="text-sm font-medium text-ink">Загрузка {progress.done} из {progress.total}…</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border"><div className="h-full bg-brand-500 transition-all" style={{ width: `${(progress.done / progress.total) * 100}%` }} /></div>
        </div>
      ) : (
        <>
          <p className="mt-3 text-sm font-medium text-ink">Перетащите {multiple ? 'файлы' : 'файл'} сюда</p>
          <p className="mt-0.5 text-xs text-ink-muted">или</p>
          <Button className="mt-2" size="sm" onClick={() => input.current?.click()}>Выбрать {multiple ? 'файлы' : 'файл'}</Button>
          <p className="mt-2 text-xs text-ink-muted">JPEG, PNG, WebP{accept.includes('video') ? ', MP4, WebM' : ''} · можно с телефона</p>
        </>
      )}
      <input ref={input} type="file" multiple={multiple} accept={accept} className="sr-only" tabIndex={-1} aria-hidden
        onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; upload(f) }} />
    </div>
  )
}

function UrlTab({ onPick }: { onPick: (asset: PickedAsset) => void }) {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<'idle' | 'ok' | 'error'>('idle')
  const valid = useMemo(() => /^https?:\/\/\S+$/i.test(url.trim()), [url])
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (valid) onPick({ url: url.trim(), title: url.trim(), alt: '' }) }}>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-ink">Прямая ссылка на изображение</span>
        <Input type="url" inputMode="url" value={url} onChange={(e) => { setUrl(e.target.value); setState('idle') }} placeholder="https://…/photo.jpg" autoFocus />
      </label>
      <p className="text-xs text-ink-muted">Сервер скопирует картинку к себе при сохранении (JPEG, PNG или WebP до 15 МБ) — сайт не будет зависеть от чужой ссылки. Ссылка на файл из медиатеки тоже подходит.</p>
      {valid ? (
        <div className="grid place-items-center overflow-hidden rounded-xl border border-border bg-surface-muted p-2">
          <img src={url.trim()} alt="Предпросмотр по ссылке" className={cn('max-h-56 rounded-lg object-contain', state === 'error' && 'hidden')}
            onLoad={() => setState('ok')} onError={() => setState('error')} />
          {state === 'error' ? <p className="py-6 text-sm text-danger">Не удалось показать картинку по этой ссылке.</p> : null}
        </div>
      ) : null}
      <div className="flex justify-end"><Button type="submit" disabled={!valid || state === 'error'}>Использовать</Button></div>
    </form>
  )
}
