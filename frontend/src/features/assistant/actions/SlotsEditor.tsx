import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { useAssistantOptions } from '@/hooks/useAssistant'
import type { SlotInput } from '@/types/assistant'
import type { DayOfWeek } from '@/types/common'

/** The weekly slots of one teaching program: day, start–end, room. */
export function SlotsEditor({ slots, onChange }: { slots: SlotInput[]; onChange: (slots: SlotInput[]) => void }) {
  const { data: options } = useAssistantOptions()
  const weekdays = (options?.weekdays ?? []).map((day) => ({ value: day.code, label: day.label }))
  const rooms = (options?.rooms ?? []).map((room) => ({ value: String(room.id), label: room.name }))

  const update = (index: number, patch: Partial<SlotInput>) =>
    onChange(slots.map((slot, i) => (i === index ? { ...slot, ...patch } : slot)))
  const remove = (index: number) => onChange(slots.filter((_, i) => i !== index))
  const add = () => {
    const last = slots[slots.length - 1]
    const order: DayOfWeek[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    const nextDay = last ? order[(order.indexOf(last.day) + 2) % 7] : 'mon'
    onChange([...slots, { day: nextDay, start: last?.start ?? '16:00', end: last?.end ?? '17:30', room: last?.room ?? null }])
  }

  return (
    <div className="space-y-2">
      {slots.length === 0 ? <p className="text-sm text-ink-secondary">Слотов пока нет — добавьте день занятий.</p> : null}
      {slots.map((slot, index) => (
        <div key={index} className="grid grid-cols-2 gap-2 rounded-lg border border-border p-2 sm:grid-cols-[1.4fr_1fr_1fr_1.2fr_auto] sm:items-center sm:border-0 sm:p-0">
          <Select aria-label="День недели" value={slot.day} onChange={(event) => update(index, { day: event.target.value as DayOfWeek })} options={weekdays} className="col-span-2 sm:col-span-1" />
          <Input aria-label="Начало" type="time" value={slot.start} onChange={(event) => update(index, { start: event.target.value })} required />
          <Input aria-label="Окончание" type="time" value={slot.end} onChange={(event) => update(index, { end: event.target.value })} required />
          <Select aria-label="Аудитория" value={slot.room ? String(slot.room) : ''} onChange={(event) => update(index, { room: event.target.value ? Number(event.target.value) : null })} options={rooms} placeholder="Без аудитории" />
          <button
            type="button"
            onClick={() => remove(index)}
            aria-label="Удалить слот"
            className="flex size-10 items-center justify-center justify-self-end rounded-lg text-ink-muted hover:bg-danger-soft hover:text-danger"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        </div>
      ))}
      <Button type="button" variant="ghost" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={add}>
        Добавить день
      </Button>
    </div>
  )
}
