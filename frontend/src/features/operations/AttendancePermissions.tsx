import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { useAttendancePermissionActions, useOpsAttendancePermissions, useOpsMeta } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { AttendancePermission, AttendancePermissionBrief, AttendancePermissionKind, OpsFiltersParams } from '@/types/operations'

import { LevelBadge, QueryView, Section, Table, dateTime } from './shared'

const KINDS: { value: AttendancePermissionKind; label: string; hint: string }[] = [
  { value: 'late_arrival', label: 'Опоздание', hint: 'Разрешено прийти позже: ожидаемый приход сдвигается.' },
  { value: 'early_departure', label: 'Ранний уход', hint: 'Разрешено уйти раньше: ожидаемый уход сдвигается.' },
  { value: 'partial_day', label: 'Часть дня', hint: 'Отпущен на несколько часов в течение дня.' },
  { value: 'full_day', label: 'Весь день', hint: 'Отсутствие по разрешению: не считается прогулом.' },
]

export interface PermissionDraft {
  user?: number
  date?: string
  /** Часы по графику из строки посещаемости — подставляются в форму. */
  expectedStart?: string | null
  expectedEnd?: string | null
}

/** Детали «Отпросился» под статусом в строке посещаемости. */
export function PermissionDetails({ permissions }: { permissions?: AttendancePermissionBrief[] }) {
  if (!permissions?.length) return null
  return (
    <span className="mt-0.5 block space-y-0.5">
      {permissions.map((p) => (
        <span key={p.id} className="block text-xs text-ink-muted" title={[p.reason, p.comment, p.approved_by ? `утвердил: ${p.approved_by}` : ''].filter(Boolean).join(' · ')}>
          {p.kind_label}: {p.period_label} — {p.reason}
        </span>
      ))}
    </span>
  )
}

/** Форма «Отпросился». Сервер проверяет права, интервал и пересечения; разрешение сразу утверждается создателем. */
export function PermissionModal({ draft, onClose }: { draft: PermissionDraft; onClose: () => void }) {
  const meta = useOpsMeta()
  const { create } = useAttendancePermissionActions()
  const { user: me } = useAuth()
  const { showToast } = useToast()
  const today = draft.date ?? meta.data?.today ?? new Date().toISOString().slice(0, 10)
  const [kind, setKind] = useState<AttendancePermissionKind>('late_arrival')
  const [form, setForm] = useState({
    user: draft.user ? String(draft.user) : '',
    date: today,
    dateTo: today,
    from: draft.expectedStart ?? '09:00',
    to: draft.expectedEnd ?? '18:00',
    arrival: '',
    departure: '',
    reason: '',
    comment: '',
  })
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))
  const workStart = draft.expectedStart ?? '09:00'
  const workEnd = draft.expectedEnd ?? '18:00'

  const interval = (): [string, string] | null => {
    if (kind === 'full_day') return form.dateTo >= form.date ? [`${form.date}T00:00`, `${form.dateTo}T23:59`] : null
    if (kind === 'late_arrival') return form.arrival > workStart ? [`${form.date}T${workStart}`, `${form.date}T${form.arrival}`] : null
    if (kind === 'early_departure') return form.departure && form.departure < workEnd ? [`${form.date}T${form.departure}`, `${form.date}T${workEnd}`] : null
    return form.to > form.from ? [`${form.date}T${form.from}`, `${form.date}T${form.to}`] : null
  }
  const range = interval()
  const ready = Boolean(form.user && range && form.reason.trim())

  const submit = () => {
    if (!range) return
    create.mutate({ user: Number(form.user), kind, starts_at: range[0], ends_at: range[1], reason: form.reason.trim(), comment: form.comment.trim() }, {
      onSuccess: () => { showToast('Разрешение сохранено', 'success'); onClose() },
      onError: (e) => showToast(extractErrorMessage(e), 'error'),
    })
  }

  const approver = me ? [me.first_name, me.last_name].filter(Boolean).join(' ') || 'вы' : 'вы'
  return (
    <Modal isOpen onClose={onClose} title="Отпросился">
      <div className="space-y-3">
        <label className="block"><span className="field-label">Сотрудник</span>
          <Select value={form.user} placeholder="Выберите сотрудника" options={(meta.data?.employees ?? []).map((e) => ({ value: String(e.id), label: `${e.full_name} — ${e.role_label}` }))} onChange={(e) => set({ user: e.target.value })} /></label>
        <div>
          <span className="field-label">Вид разрешения</span>
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Вид разрешения">
            {KINDS.map((k) => (
              <button key={k.value} type="button" role="radio" aria-checked={kind === k.value} onClick={() => setKind(k.value)}
                className={`rounded-lg border px-3 py-2 text-left text-sm ${kind === k.value ? 'border-brand-600 bg-brand-50 font-semibold text-brand-700' : 'border-border text-ink-secondary hover:border-brand-300'}`}>
                {k.label}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-ink-muted">{KINDS.find((k) => k.value === kind)?.hint}</p>
        </div>
        {kind === 'full_day' ? (
          <div className="grid grid-cols-2 gap-3">
            <label className="block"><span className="field-label">С даты</span><Input type="date" value={form.date} onChange={(e) => set({ date: e.target.value, dateTo: e.target.value > form.dateTo ? e.target.value : form.dateTo })} /></label>
            <label className="block"><span className="field-label">По дату (включительно)</span><Input type="date" value={form.dateTo} min={form.date} onChange={(e) => set({ dateTo: e.target.value })} /></label>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <label className="col-span-2 block md:col-span-1"><span className="field-label">Дата</span><Input type="date" value={form.date} onChange={(e) => set({ date: e.target.value })} /></label>
            {kind === 'late_arrival' ? <>
              <label className="block"><span className="field-label">По графику</span><Input type="time" value={workStart} disabled /></label>
              <label className="block"><span className="field-label">Придёт к</span><Input type="time" value={form.arrival} onChange={(e) => set({ arrival: e.target.value })} /></label>
            </> : null}
            {kind === 'early_departure' ? <>
              <label className="block"><span className="field-label">Уйдёт в</span><Input type="time" value={form.departure} onChange={(e) => set({ departure: e.target.value })} /></label>
              <label className="block"><span className="field-label">По графику</span><Input type="time" value={workEnd} disabled /></label>
            </> : null}
            {kind === 'partial_day' ? <>
              <label className="block"><span className="field-label">С</span><Input type="time" value={form.from} onChange={(e) => set({ from: e.target.value })} /></label>
              <label className="block"><span className="field-label">По</span><Input type="time" value={form.to} onChange={(e) => set({ to: e.target.value })} /></label>
            </> : null}
          </div>
        )}
        {!range && (kind !== 'late_arrival' || form.arrival) && (kind !== 'early_departure' || form.departure)
          ? <p className="text-xs text-danger">{kind === 'late_arrival' ? 'Время прихода должно быть позже начала по графику.' : kind === 'early_departure' ? 'Время ухода должно быть раньше конца по графику.' : 'Окончание должно быть позже начала.'}</p>
          : null}
        <label className="block"><span className="field-label">Причина</span><Input value={form.reason} maxLength={255} placeholder="Например: приём у врача" onChange={(e) => set({ reason: e.target.value })} /></label>
        <label className="block"><span className="field-label">Комментарий (необязательно)</span><Textarea rows={2} value={form.comment} onChange={(e) => set({ comment: e.target.value })} /></label>
        <p className="text-xs text-ink-muted">Статус: утверждено · утвердит: {approver} · время создания запишется автоматически. Отметки по QR не меняются.</p>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Отмена</Button><Button onClick={submit} isLoading={create.isPending} disabled={!ready}>Сохранить</Button></div>
      </div>
    </Modal>
  )
}

function CancelModal({ permission, onClose }: { permission: AttendancePermission; onClose: () => void }) {
  const { cancel } = useAttendancePermissionActions()
  const { showToast } = useToast()
  const [reason, setReason] = useState('')
  const submit = () => cancel.mutate({ id: permission.id, reason: reason.trim() }, {
    onSuccess: () => { showToast('Разрешение отменено', 'success'); onClose() },
    onError: (e) => showToast(extractErrorMessage(e), 'error'),
  })
  return (
    <Modal isOpen onClose={onClose} title="Отменить разрешение">
      <div className="space-y-3">
        <p className="text-sm">{permission.user.full_name}: {permission.kind_label.toLowerCase()}, {permission.period_label}. После отмены посещаемость пересчитается без разрешения; запись останется в истории.</p>
        <label className="block"><span className="field-label">Причина отмены</span><Input value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Назад</Button><Button variant="danger" onClick={submit} isLoading={cancel.isPending} disabled={!reason.trim()}>Отменить разрешение</Button></div>
      </div>
    </Modal>
  )
}

/** История «Отпросился» за выбранный период с аудитом и отменой. */
export function PermissionsHistory({ params }: { params: OpsFiltersParams & Record<string, string | undefined> }) {
  const query = useOpsAttendancePermissions(params)
  const [cancelling, setCancelling] = useState<AttendancePermission | null>(null)
  return (
    <Section title="Разрешения «Отпросился»" padding={false}>
      <QueryView query={query}>
        {(data) => (
          <Table empty={!data.results.length} headers={['Сотрудник', 'Вид', 'Когда', 'Причина', 'Статус', 'Аудит', '']}>
            {data.results.map((p) => (
              <tr key={p.id}>
                <td className="font-medium">{p.user.full_name}<span className="block text-xs text-ink-muted">{p.user.role_label}</span></td>
                <td>{p.kind_label}</td>
                <td className="whitespace-nowrap tabular-nums">{p.period_label}</td>
                <td className="text-sm">{p.reason}{p.comment ? <span className="block text-xs text-ink-muted">{p.comment}</span> : null}</td>
                <td><LevelBadge level={p.status === 'approved' ? 'accepted' : 'dismissed'} label={p.status_label} /></td>
                <td className="text-xs text-ink-muted">
                  создал {p.created_by?.full_name ?? '—'}, {dateTime(p.created_at)}
                  {p.approved_by ? <span className="block">утвердил {p.approved_by.full_name}{p.approved_at ? `, ${dateTime(p.approved_at)}` : ''}</span> : null}
                  {p.cancelled_by ? <span className="block">отменил {p.cancelled_by.full_name}{p.cancelled_at ? `, ${dateTime(p.cancelled_at)}` : ''}: {p.cancel_reason}</span> : null}
                </td>
                <td className="text-right">{data.can_manage && p.status === 'approved' ? <Button variant="ghost" size="sm" onClick={() => setCancelling(p)}>Отменить</Button> : null}</td>
              </tr>
            ))}
          </Table>
        )}
      </QueryView>
      {cancelling ? <CancelModal permission={cancelling} onClose={() => setCancelling(null)} /> : null}
    </Section>
  )
}
