import { Copy, ImageOff, ImagePlus, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/utils/cn'

import type { Choice } from './api'
import { MediaPicker } from './MediaPicker'
import { RichTextEditor } from './RichTextEditor'
import type { FieldDef } from './schema'

/** ISO ↔ <input type="datetime-local"> (local time). */
export function toLocalInput(iso: unknown): string {
  if (!iso || typeof iso !== 'string') return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null)

/** An image field value: undefined — unchanged, null — cleared, a File — a
 * new upload, `ref` — `media:<id>` or a direct link (copied by the server). */
export type ImageValue = File | null | undefined | { ref: string; preview: string }

export const imageRef = (value: unknown): unknown =>
  value && typeof value === 'object' && !(value instanceof File) && 'ref' in value ? (value as { ref: string }).ref : value

/** An image field: the current picture, «from the library / by link», upload from the device, clear. */
export function ImageInput({ id, current, value, onChange, square }: { id: string; current: string | null; value: ImageValue; onChange: (v: ImageValue) => void; square?: boolean }) {
  const { showToast } = useToast()
  const [picker, setPicker] = useState(false)
  const filePreview = useMemo(() => (value instanceof File ? URL.createObjectURL(value) : null), [value])
  useEffect(() => () => { if (filePreview) URL.revokeObjectURL(filePreview) }, [filePreview])
  const shown = value === null ? null : filePreview ?? (value && 'preview' in value ? value.preview : null) ?? current
  const pending = value !== undefined
  return (
    <div>
      <div className={cn('relative grid place-items-center overflow-hidden rounded-xl border border-border bg-surface-muted', square ? 'aspect-square max-w-56' : 'aspect-[16/9]')}>
        {shown ? <img src={shown} alt="" className="size-full object-cover" /> : (
          <button type="button" onClick={() => setPicker(true)} className="flex flex-col items-center gap-1.5 p-4 text-ink-muted hover:text-brand-600">
            <ImageOff className="size-7" aria-hidden />
            <span className="text-xs font-medium">Изображение не выбрано</span>
          </button>
        )}
        {pending ? <span className="absolute top-2 left-2 rounded-full bg-cms-gold px-2 py-0.5 text-[0.6875rem] font-semibold text-brand-700">Не сохранено</span> : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" leftIcon={<ImagePlus className="size-4" aria-hidden />} onClick={() => setPicker(true)}>Медиатека</Button>
        <label htmlFor={id} className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium text-ink-secondary hover:bg-surface-hover focus-within:outline-2 focus-within:outline-brand-500">
          <Upload className="size-4" aria-hidden /> С устройства
          <input id={id} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onChange(f) }} />
        </label>
        {shown ? (
          <Button size="sm" variant="ghost" className="text-ink-secondary hover:text-danger" leftIcon={<X className="size-4" aria-hidden />} onClick={() => onChange(null)}>Убрать</Button>
        ) : null}
        {pending ? <Button size="sm" variant="ghost" onClick={() => onChange(undefined)}>Вернуть</Button> : null}
      </div>
      {current && !pending ? (
        <button type="button" onClick={() => navigator.clipboard?.writeText(current).then(() => showToast('Прямая ссылка скопирована', 'success'), () => showToast('Не удалось скопировать', 'error'))}
          className="mt-1.5 inline-flex max-w-full items-center gap-1 text-xs text-ink-muted hover:text-brand-600">
          <Copy className="size-3.5 shrink-0" aria-hidden /><span className="truncate">Копировать прямую ссылку</span>
        </button>
      ) : null}
      <MediaPicker isOpen={picker} onClose={() => setPicker(false)}
        onPick={(asset) => { setPicker(false); onChange({ ref: asset.id ? `media:${asset.id}` : asset.url, preview: asset.url }) }} />
    </div>
  )
}

export function FieldInput({ field, id, value, onChange, choices, current, placeholder }: {
  field: FieldDef
  id: string
  value: unknown
  onChange: (v: unknown) => void
  choices: Choice[]
  current?: string | null
  /** For a translation: the Russian original as a hint. */
  placeholder?: string
}) {
  switch (field.type) {
    case 'textarea':
    case 'lines':
      return <Textarea id={id} rows={field.type === 'lines' ? 5 : 3} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    case 'richtext':
      return <RichTextEditor id={id} value={String(value ?? '')} onChange={onChange} placeholder={placeholder} />
    case 'number':
      return <Input id={id} type="number" value={value === null || value === undefined ? '' : String(value)} onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)} />
    case 'date':
      return <Input id={id} type="date" value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} />
    case 'datetime':
      return <Input id={id} type="datetime-local" value={toLocalInput(value)} onChange={(e) => onChange(fromLocalInput(e.target.value))} />
    case 'select':
      return <Select id={id} value={value === null || value === undefined ? '' : String(value)} placeholder={field.required ? undefined : '—'} options={choices} onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)} />
    case 'boolean':
      return (
        <label className="flex h-10 items-center gap-2 text-sm">
          <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-brand-600" />
          {field.label}
        </label>
      )
    case 'image':
      return <ImageInput id={id} current={current ?? null} value={value as ImageValue} onChange={onChange} square={field.name === 'photo'} />
    default:
      return <Input id={id} type={field.type === 'url' ? 'url' : 'text'} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
  }
}
