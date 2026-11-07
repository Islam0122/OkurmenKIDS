import { useEffect, useId, useRef, useState } from 'react'
import { AlertCircle, CloudUpload, ImagePlus, Loader2, Star, Trash2 } from 'lucide-react'

import { resolveMediaUrl } from '@/lib/mediaUrl'
import { cn } from '@/utils/cn'

import { IMAGE_TYPES, MAX_IMAGE_BYTES } from './shared'

/** An image of the form: one already on the server, or a picked file not yet uploaded. */
export type FormImage =
  | { key: string; kind: 'existing'; id: number; url: string | null; isCover: boolean }
  | { key: string; kind: 'new'; file: File; previewUrl: string; isCover: boolean; progress: number | null; error: string | null }

let seq = 0
export const nextImageKey = () => `img-${++seq}`

export interface ImageDropzoneProps {
  images: FormImage[]
  onChange: (images: FormImage[]) => void
  max: number
  disabled?: boolean
}

function withCover(images: FormImage[]): FormImage[] {
  if (images.length === 0 || images.some((i) => i.isCover)) return images
  return images.map((img, n) => ({ ...img, isCover: n === 0 }))
}

/** Drag-and-drop gallery editor: previews, cover choice, removal and per-file upload progress. */
export function ImageDropzone({ images, onChange, max, disabled }: ImageDropzoneProps) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [rejected, setRejected] = useState<string[]>([])
  const left = Math.max(0, max - images.length)

  // Revoke object URLs of previews that left the list (and on unmount).
  const previews = useRef(new Set<string>())
  useEffect(() => {
    // An uploaded file keeps showing its local preview until the page reloads.
    const current = new Set(images.map((img) => (img.kind === 'new' ? img.previewUrl : img.url ?? '')).filter((url) => url.startsWith('blob:')))
    for (const url of previews.current) if (!current.has(url)) URL.revokeObjectURL(url)
    previews.current = current
  }, [images])
  useEffect(() => () => { for (const url of previews.current) URL.revokeObjectURL(url) }, [])

  const addFiles = (files: FileList | File[]) => {
    const errors: string[] = []
    const added: FormImage[] = []
    for (const file of Array.from(files)) {
      if (!IMAGE_TYPES.includes(file.type)) {
        errors.push(`«${file.name}» — поддерживаются только JPG, PNG и WEBP.`)
      } else if (file.size > MAX_IMAGE_BYTES) {
        errors.push(`«${file.name}» больше 10 МБ.`)
      } else if (images.length + added.length >= max) {
        errors.push(`Можно загрузить не больше ${max} изображений — «${file.name}» не добавлен.`)
      } else {
        added.push({ key: nextImageKey(), kind: 'new', file, previewUrl: URL.createObjectURL(file), isCover: false, progress: null, error: null })
      }
    }
    setRejected(errors)
    if (added.length) onChange(withCover([...images, ...added]))
  }

  const remove = (key: string) => onChange(withCover(images.filter((img) => img.key !== key)))
  const makeCover = (key: string) => onChange(images.map((img) => ({ ...img, isCover: img.key === key })))

  return (
    <div className="space-y-4">
      <label
        htmlFor={inputId}
        onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (!disabled) addFiles(event.dataTransfer.files)
        }}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors',
          dragging ? 'border-brand-500 bg-brand-50' : 'border-border-strong bg-surface-muted hover:border-brand-200 hover:bg-brand-50/40',
          (disabled || left === 0) && 'pointer-events-none opacity-60',
        )}
      >
        <span className={cn('flex size-12 items-center justify-center rounded-full bg-surface text-brand-600 shadow-sm ring-1 ring-border transition-transform', dragging && 'scale-110')}>
          <CloudUpload className="size-6" aria-hidden />
        </span>
        <span>
          <span className="block text-sm font-medium text-ink">
            <span className="text-brand-700">Выберите файлы</span> или перетащите их сюда
          </span>
          <span className="mt-1 block text-xs text-ink-muted">JPG, PNG или WEBP · до 10 МБ · осталось мест: {left} из {max}</span>
        </span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={IMAGE_TYPES.join(',')}
          multiple
          disabled={disabled || left === 0}
          className="sr-only"
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files)
            event.target.value = ''
          }}
        />
      </label>

      {rejected.length > 0 ? (
        <div role="alert" className="space-y-1 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger">
          {rejected.map((message) => (
            <p key={message} className="flex items-start gap-2"><AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />{message}</p>
          ))}
        </div>
      ) : null}

      {images.length > 0 ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-label="Изображения проекта">
          {images.map((img, index) => {
            const src = img.kind === 'new' ? img.previewUrl : resolveMediaUrl(img.url)
            const uploading = img.kind === 'new' && img.progress !== null && img.progress < 100 && !img.error
            const failed = img.kind === 'new' && img.error
            return (
              <li
                key={img.key}
                className={cn(
                  'group relative overflow-hidden rounded-xl border bg-surface-muted',
                  img.isCover ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-border',
                  failed && 'border-danger',
                )}
              >
                <div className="aspect-[4/3]">
                  {src ? <img src={src} alt={`Изображение ${index + 1}`} className="size-full object-cover" /> : <ImagePlus className="m-auto size-6 text-ink-muted" aria-hidden />}
                </div>

                {img.isCover ? (
                  <span className="absolute left-2 top-2 inline-flex h-6 items-center gap-1 rounded-full bg-brand-500 px-2 text-[11px] font-semibold text-white shadow-sm">
                    <Star className="size-3 fill-current" aria-hidden /> Обложка
                  </span>
                ) : null}

                {uploading ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-ink/45 text-white">
                    <Loader2 className="size-5 animate-spin" aria-hidden />
                    <span className="text-xs font-medium">{img.progress}%</span>
                    <div className="absolute inset-x-0 bottom-0 h-1 bg-white/30">
                      <div className="h-full bg-brand-500 transition-[width] duration-200" style={{ width: `${img.progress}%` }} />
                    </div>
                  </div>
                ) : null}

                {failed ? (
                  <div className="absolute inset-x-0 bottom-0 flex items-start gap-1.5 bg-danger px-2 py-1.5 text-[11px] leading-tight text-white">
                    <AlertCircle className="size-3.5 shrink-0" aria-hidden />
                    <span className="line-clamp-2">{img.error}</span>
                  </div>
                ) : null}

                {!uploading && !disabled ? (
                  <div className="absolute right-2 top-2 flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                    {!img.isCover ? (
                      <button
                        type="button"
                        onClick={() => makeCover(img.key)}
                        aria-label={`Сделать изображение ${index + 1} обложкой`}
                        title="Сделать обложкой"
                        className="flex size-8 items-center justify-center rounded-lg bg-surface/95 text-ink-secondary shadow-sm backdrop-blur hover:text-brand-700"
                      >
                        <Star className="size-4" aria-hidden />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => remove(img.key)}
                      aria-label={`Удалить изображение ${index + 1}`}
                      title="Удалить"
                      className="flex size-8 items-center justify-center rounded-lg bg-surface/95 text-ink-secondary shadow-sm backdrop-blur hover:text-danger"
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
