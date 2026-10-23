import { useState, type FormEvent } from 'react'
import { PencilLine } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useAdjustSession, useCreateManualSession } from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import type { Employee, WorkSession } from '@/types/staffAttendance'

import { formatDay, fromZonedInput, toZonedInput } from './format'

export type AdjustTarget =
  | { mode: 'edit'; employee: Employee; session: WorkSession }
  | { mode: 'create'; employee: Employee; date: string }

interface Props {
  target: AdjustTarget | null
  timeZone: string
  locations: { id: number; name: string }[]
  onClose: () => void
}

/** Ручное исправление записи или запись за забытую отметку. Причина
 * обязательна; backend сохраняет «было/стало», автора и время. */
export function AdjustModal({ target, timeZone, locations, onClose }: Props) {
  return (
    <Modal
      isOpen={target !== null}
      onClose={onClose}
      title={target?.mode === 'create' ? 'Добавить запись' : 'Исправить запись'}
      icon={<PencilLine className="size-5 text-brand-600" aria-hidden />}
    >
      {target ? <AdjustForm key={target.mode === 'edit' ? `s${target.session.id}` : `c${target.employee.id}${target.date}`} target={target} timeZone={timeZone} locations={locations} onClose={onClose} /> : null}
    </Modal>
  )
}

function AdjustForm({ target, timeZone, locations, onClose }: Props & { target: AdjustTarget }) {
  const { showToast } = useToast()
  const adjust = useAdjustSession()
  const create = useCreateManualSession()
  const session = target.mode === 'edit' ? target.session : null
  const day = target.mode === 'edit' ? target.session.work_date : target.date
  const [checkIn, setCheckIn] = useState(session ? toZonedInput(session.checked_in_at, timeZone) : `${day}T09:00`)
  const [checkOut, setCheckOut] = useState(session?.checked_out_at ? toZonedInput(session.checked_out_at, timeZone) : target.mode === 'create' ? `${day}T18:00` : '')
  const [location, setLocation] = useState(String(session?.location?.id ?? locations[0]?.id ?? ''))
  const [lateOverride, setLateOverride] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const pending = adjust.isPending || create.isPending

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const checkedIn = fromZonedInput(checkIn, timeZone)
    const checkedOut = checkOut ? fromZonedInput(checkOut, timeZone) : null
    if (!checkedIn || (checkOut && !checkedOut)) {
      setError('Укажите корректные дату и время.')
      return
    }
    if (reason.trim().length < 5) {
      setError('Укажите причину исправления (не короче 5 символов).')
      return
    }
    const payload = {
      checked_in_at: checkedIn,
      checked_out_at: checkedOut,
      reason: reason.trim(),
      location: location ? Number(location) : null,
      late_minutes: lateOverride === '' ? null : Number(lateOverride),
    }
    try {
      if (target.mode === 'edit') {
        await adjust.mutateAsync({ sessionId: target.session.id, payload })
      } else {
        await create.mutateAsync({ ...payload, user: target.employee.id })
      }
      showToast('Запись сохранена, исправление занесено в журнал', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-ink-secondary">
        {target.employee.full_name} · {formatDay(day)}. Время — по часовому поясу офиса ({timeZone}).
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="adj-in" className="mb-1.5 block field-label">Приход</label>
          <Input id="adj-in" type="datetime-local" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} required />
        </div>
        <div>
          <label htmlFor="adj-out" className="mb-1.5 block field-label">Уход</label>
          <Input id="adj-out" type="datetime-local" value={checkOut} onChange={(e) => setCheckOut(e.target.value)} required={target.mode === 'create'} />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="adj-loc" className="mb-1.5 block field-label">Офис</label>
          <Select id="adj-loc" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Не указан" options={locations.map((l) => ({ value: String(l.id), label: l.name }))} />
        </div>
        <div>
          <label htmlFor="adj-late" className="mb-1.5 block field-label">Опоздание, мин</label>
          <Input id="adj-late" type="number" min={0} max={1440} inputMode="numeric" placeholder="Рассчитать автоматически" value={lateOverride} onChange={(e) => setLateOverride(e.target.value)} />
        </div>
      </div>
      <div>
        <label htmlFor="adj-reason" className="mb-1.5 block field-label">Причина исправления *</label>
        <Textarea id="adj-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: телефон не считал QR, приход подтверждён руководителем" required />
      </div>
      {error ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
        <Button type="submit" isLoading={pending}>Сохранить</Button>
      </div>
    </form>
  )
}
