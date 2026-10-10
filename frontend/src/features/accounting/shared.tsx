import { useState } from 'react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import type { PayrollStatus, PeriodSelection } from '@/types/accounting'

const NBSP = ' '

/** «12 345,50 сом» — суммы приходят строками Decimal, без float-округления по пути. */
export function som(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const text = typeof value === 'number' ? value.toFixed(2) : value
  const negative = text.startsWith('-')
  const [whole, frac = ''] = text.replace('-', '').split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
  const cents = frac.padEnd(2, '0').slice(0, 2)
  return `${negative ? '−' : ''}${grouped}${cents === '00' ? '' : `,${cents}`}${NBSP}сом`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-')
  return `${d}.${m}.${y}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const STATUS_TONE: Record<PayrollStatus, BadgeTone> = {
  DRAFT: 'muted',
  CALCULATED: 'info',
  RETURNED: 'warning',
  APPROVED: 'brand',
  PARTIALLY_PAID: 'warning',
  PAID: 'success',
  VOID: 'muted',
}

export function PayrollStatusBadge({ status, label }: { status: PayrollStatus | 'MIXED' | null; label?: string | null }) {
  if (!status) return <Badge>Не рассчитан</Badge>
  if (status === 'MIXED') return <Badge tone="info">Разные статусы</Badge>
  return <Badge tone={STATUS_TONE[status]}>{label ?? status}</Badge>
}

export const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

export function currentSelection(): PeriodSelection {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1, half: now.getDate() <= 15 ? 'FIRST_HALF' : 'SECOND_HALF' }
}

/** Месяц, год и расчётный период (1–15, 16–конец, или полный месяц для сводки). */
export function PeriodPicker({ value, onChange, allowMonth = true }: {
  value: PeriodSelection
  onChange: (next: PeriodSelection) => void
  allowMonth?: boolean
}) {
  const year = new Date().getFullYear()
  const years = [year - 2, year - 1, year, year + 1].map((y) => ({ value: String(y), label: String(y) }))
  const halves = [
    { value: 'FIRST_HALF', label: '1–15 число' },
    { value: 'SECOND_HALF', label: '16 – конец месяца' },
    ...(allowMonth ? [{ value: 'MONTH', label: 'Весь месяц: оклады и сводка' }] : []),
  ]
  return (
    <div className="flex flex-wrap gap-2">
      <Select aria-label="Месяц" className="w-36" value={String(value.month)}
        options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
        onChange={(e) => onChange({ ...value, month: Number(e.target.value) })} />
      <Select aria-label="Год" className="w-24" value={String(value.year)} options={years}
        onChange={(e) => onChange({ ...value, year: Number(e.target.value) })} />
      <Select aria-label="Период" className="w-48" value={value.half} options={halves}
        onChange={(e) => onChange({ ...value, half: e.target.value as PeriodSelection['half'] })} />
    </div>
  )
}

/** Runs an action with a toast for its result; returns whether it succeeded. */
export function useRunner() {
  const { showToast } = useToast()
  const [busy, setBusy] = useState(false)
  async function run(action: () => Promise<unknown>, success?: string): Promise<boolean> {
    setBusy(true)
    try {
      await action()
      if (success) showToast(success, 'success')
      return true
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
      return false
    } finally {
      setBusy(false)
    }
  }
  return { run, busy }
}

/** A required-reason prompt (return, reopen, void…) — every such action is audited with its reason. */
export function ReasonModal({ isOpen, title, description, confirmLabel, tone = 'primary', onClose, onConfirm }: {
  isOpen: boolean
  title: string
  description?: string
  confirmLabel: string
  tone?: 'primary' | 'danger'
  onClose: () => void
  onConfirm: (reason: string) => Promise<boolean>
}) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title}>
      {description ? <p className="mb-3 text-sm text-ink-secondary">{description}</p> : null}
      <label htmlFor="reason" className="mb-1.5 block field-label">Причина <span className="text-danger">*</span></label>
      <Textarea id="reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button
          variant={tone === 'danger' ? 'danger' : 'primary'}
          disabled={!reason.trim()}
          isLoading={busy}
          onClick={async () => {
            setBusy(true)
            const ok = await onConfirm(reason.trim())
            setBusy(false)
            if (ok) {
              setReason('')
              onClose()
            }
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}

export function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  )
}

export function Notice({ tone, items }: { tone: 'warning' | 'danger'; items: string[] }) {
  if (items.length === 0) return null
  return (
    <ul className={tone === 'danger'
      ? 'space-y-1 rounded-xl border border-danger/20 bg-danger-soft p-3 text-sm text-danger'
      : 'space-y-1 rounded-xl border border-warning/20 bg-warning-soft p-3 text-sm text-warning'}>
      {items.map((item) => <li key={item}>• {item}</li>)}
    </ul>
  )
}
