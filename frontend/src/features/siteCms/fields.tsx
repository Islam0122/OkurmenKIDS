import { ImageOff, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'

import type { Choice } from './api'
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

/** An image field: shows the current picture, lets you choose a new file or clear it. */
export function ImageInput({ id, current, value, onChange }: { id: string; current: string | null; value: File | null | undefined; onChange: (v: File | null | undefined) => void }) {
  const preview = useMemo(() => (value instanceof File ? URL.createObjectURL(value) : null), [value])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const shown = value === null ? null : preview ?? current
  return (
    <div className="flex items-center gap-3">
      <div className="grid size-24 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-surface-muted">
        {shown ? <img src={shown} alt="" className="size-full object-cover" /> : <ImageOff className="size-6 text-ink-muted" aria-hidden />}
      </div>
      <div className="flex flex-col gap-2">
        <label htmlFor={id} className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-brand-200 px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
          <Upload className="size-4" aria-hidden /> {shown ? 'Заменить' : 'Загрузить'}
          <input id={id} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => onChange(e.target.files?.[0] ?? undefined)} />
        </label>
        {shown ? (
          <button type="button" onClick={() => onChange(null)} className="inline-flex items-center gap-1 text-xs text-ink-secondary hover:text-danger">
            <X className="size-3.5" aria-hidden /> Убрать изображение
          </button>
        ) : null}
        <span className="text-xs text-ink-muted">JPEG, PNG или WebP до 15 МБ</span>
      </div>
    </div>
  )
}

export function FieldInput({ field, id, value, onChange, choices, current }: {
  field: FieldDef
  id: string
  value: unknown
  onChange: (v: unknown) => void
  choices: Choice[]
  current?: string | null
}) {
  switch (field.type) {
    case 'textarea':
    case 'lines':
      return <Textarea id={id} rows={field.type === 'lines' ? 5 : 3} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
    case 'richtext':
      return <RichTextEditor id={id} value={String(value ?? '')} onChange={onChange} />
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
      return <ImageInput id={id} current={current ?? null} value={value as File | null | undefined} onChange={onChange} />
    default:
      return <Input id={id} type={field.type === 'url' ? 'url' : 'text'} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
  }
}

/** Collapsible «Переводы» block for one translatable field. */
export function TranslationInputs({ field, values, onChange }: { field: FieldDef; values: Record<string, unknown>; onChange: (name: string, v: unknown) => void }) {
  const [open, setOpen] = useState(Boolean(values[`${field.name}_ky`] || values[`${field.name}_en`]))
  if (!open) {
    return <button type="button" onClick={() => setOpen(true)} className="mt-1 text-xs font-medium text-brand-600 hover:underline">+ Кыргызча / English</button>
  }
  return (
    <div className="mt-2 grid gap-2 rounded-lg border border-dashed border-border p-2 sm:grid-cols-2">
      {(['ky', 'en'] as const).map((lang) => {
        const name = `${field.name}_${lang}`
        const label = lang === 'ky' ? 'Кыргызча' : 'English'
        return (
          <label key={lang} className="block">
            <span className="mb-1 block text-xs text-ink-secondary">{label}</span>
            {field.type === 'richtext' || field.type === 'textarea' || field.type === 'lines' ? (
              <Textarea rows={field.type === 'richtext' ? 6 : 3} value={String(values[name] ?? '')} onChange={(e) => onChange(name, e.target.value)} />
            ) : (
              <Input value={String(values[name] ?? '')} onChange={(e) => onChange(name, e.target.value)} />
            )}
          </label>
        )
      })}
      <p className="text-xs text-ink-muted sm:col-span-2">Пусто — на сайте будет русский текст.</p>
    </div>
  )
}
