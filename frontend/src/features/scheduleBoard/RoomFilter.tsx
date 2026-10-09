import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, DoorOpen } from 'lucide-react'

import { cn } from '@/utils/cn'

interface RoomOption {
  id: number
  name: string
  capacity?: number | null
}

/**
 * «Кабинет ▼» — one room, several, or all. Every tick applies at once (no
 * «Применить» button); «Только этот» narrows to one room in one click.
 */
export function RoomFilter({ rooms, value, onChange }: { rooms: RoomOption[]; value: number[]; onChange: (rooms: number[]) => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const selected = rooms.filter((room) => value.includes(room.id))
  const label = selected.length === 0 ? 'Все кабинеты' : selected.length <= 2 ? selected.map((r) => r.name).join(', ') : `Кабинеты: ${selected.length}`
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])

  return (
    <div ref={box} className="relative min-w-0">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Кабинет: ${label}`}
        onClick={() => setOpen((v) => !v)}
        className={cn('form-control flex items-center gap-2 pr-9 text-left', value.length > 0 && 'border-brand-500 text-brand-700')}
      >
        <DoorOpen className="size-4 shrink-0 text-ink-muted" aria-hidden />
        <span className="truncate">{label}</span>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      </button>
      {open ? (
        <div role="listbox" aria-multiselectable="true" aria-label="Кабинеты"
          className="absolute left-0 z-40 mt-1 max-h-80 w-64 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-lg">
          <button type="button" role="option" aria-selected={value.length === 0} onClick={() => onChange([])}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-hover">
            <span className={cn('flex size-4 items-center justify-center rounded border', value.length === 0 ? 'border-brand-500 bg-brand-500 text-white' : 'border-border-strong')}>
              {value.length === 0 ? <Check className="size-3" aria-hidden /> : null}
            </span>
            <span className="font-medium">Все кабинеты</span>
          </button>
          <div className="my-1 border-t border-border" />
          {rooms.length === 0 ? <p className="px-2 py-1.5 text-sm text-ink-muted">Кабинетов нет</p> : null}
          {rooms.map((room) => {
            const checked = value.includes(room.id)
            return (
              <div key={room.id} className="group flex items-center rounded-md hover:bg-surface-hover">
                <button type="button" role="option" aria-selected={checked} onClick={() => toggle(room.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-sm">
                  <span className={cn('flex size-4 shrink-0 items-center justify-center rounded border', checked ? 'border-brand-500 bg-brand-500 text-white' : 'border-border-strong')}>
                    {checked ? <Check className="size-3" aria-hidden /> : null}
                  </span>
                  <span className="truncate">{room.name}</span>
                  {room.capacity ? <span className="ml-auto shrink-0 text-2xs text-ink-muted">{room.capacity} мест</span> : null}
                </button>
                <button type="button" onClick={() => { onChange([room.id]); setOpen(false) }}
                  className="mr-1 hidden shrink-0 rounded px-1.5 py-0.5 text-2xs font-medium text-brand-700 hover:bg-brand-50 group-hover:block focus-visible:block">
                  Только
                </button>
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
