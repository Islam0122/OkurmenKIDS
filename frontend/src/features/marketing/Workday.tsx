import { useState } from 'react'
import { ChevronRight, LogIn, LogOut, ScanLine, ScanQrCode, Timer } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { useMyAttendanceStatus } from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import { DEFAULT_TZ, formatDuration, formatTime } from '@/features/staffAttendance/format'
import { MarkFlow } from '@/features/staffAttendance/MarkFlow'
import type { MarkKind, WorkdayState } from '@/types/staffAttendance'
import { cn } from '@/utils/cn'

/** Приход и уход в кабинете маркетинга — тот же механизм, что на странице
 * /attendance: статус с сервера (apps.staff_attendance), отметка — MarkFlow
 * (QR-код офиса → свежая геолокация → проверки сервера). Здесь только вход
 * в этот поток, без своей логики посещаемости. */

const STATE: Record<WorkdayState, { label: string; tone: BadgeTone }> = {
  not_arrived: { label: 'Ещё не пришёл', tone: 'muted' },
  at_work: { label: 'На работе', tone: 'success' },
  day_finished: { label: 'Рабочий день завершён', tone: 'info' },
}

/** Кнопка в шапке кабинета: следующая отметка по статусу с сервера. */
export function WorkdayButton() {
  const status = useMyAttendanceStatus()
  const [action, setAction] = useState<MarkKind | null>(null)

  if (!status.data) return null
  const data = status.data
  const atWork = data.state === 'at_work'
  const tz = data.timezone || DEFAULT_TZ
  const label = data.next_action === 'check_in' ? 'Отметить приход' : 'Отметить уход'

  return (
    <>
      <button
        type="button"
        onClick={() => setAction(data.next_action)}
        aria-label={label}
        className={cn(
          'flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium transition-colors',
          atWork ? 'border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100' : 'border-brand-500 bg-brand-500 text-white hover:bg-brand-600',
        )}
      >
        {atWork ? (
          <span className="relative flex size-2" aria-hidden>
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-500 opacity-60 motion-reduce:animate-none" />
            <span className="relative inline-flex size-2 rounded-full bg-brand-500" />
          </span>
        ) : (
          <ScanQrCode className="size-4 shrink-0" aria-hidden />
        )}
        <span className="whitespace-nowrap">
          {atWork ? <><span className="hidden sm:inline">На работе с </span>{formatTime(data.today.check_in, tz)}</> : <><span className="sm:hidden">{data.next_action === 'check_in' ? 'Приход' : 'Уход'}</span><span className="hidden sm:inline">{label}</span></>}
        </span>
      </button>
      <Modal
        isOpen={action !== null}
        onClose={() => setAction(null)}
        title={action === 'check_in' ? 'Отметить приход' : 'Отметить уход'}
        icon={<ScanLine className="size-5 text-brand-600" aria-hidden />}
      >
        {action ? <MarkFlow action={action} onDone={() => setAction(null)} /> : null}
      </Modal>
    </>
  )
}

/** Карточка «Рабочий день» на обзоре: только статус и время из backend. */
export function WorkdayCard() {
  const status = useMyAttendanceStatus()

  return (
    <Card
      title="Рабочий день"
      actions={
        <Link to="/attendance/staff" className="inline-flex items-center gap-0.5 text-sm font-medium text-brand-700 hover:underline">
          История
          <ChevronRight className="size-4" aria-hidden />
        </Link>
      }
    >
      {status.isPending ? (
        <p className="text-sm text-ink-secondary">Загружаем статус…</p>
      ) : status.isError ? (
        <p className="text-sm text-danger">{extractErrorMessage(status.error, 'Статус рабочего дня недоступен.')}</p>
      ) : (
        <WorkdayFacts />
      )}
    </Card>
  )
}

function WorkdayFacts() {
  const { data } = useMyAttendanceStatus()
  if (!data) return null
  const tz = data.timezone || DEFAULT_TZ
  const state = STATE[data.state]
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-surface-muted px-3 py-2">
          <dt className="flex items-center gap-1 text-xs text-ink-secondary"><LogIn className="size-3.5" aria-hidden />Приход</dt>
          <dd className="mt-0.5 font-semibold tabular-nums text-ink">{formatTime(data.today.check_in, tz)}</dd>
        </div>
        <div className="rounded-xl bg-surface-muted px-3 py-2">
          <dt className="flex items-center gap-1 text-xs text-ink-secondary"><LogOut className="size-3.5" aria-hidden />Уход</dt>
          <dd className="mt-0.5 font-semibold tabular-nums text-ink">{formatTime(data.today.check_out, tz)}</dd>
        </div>
        <div className="rounded-xl bg-surface-muted px-3 py-2">
          <dt className="flex items-center gap-1 text-xs text-ink-secondary"><Timer className="size-3.5" aria-hidden />На работе</dt>
          <dd className="mt-0.5 truncate font-semibold tabular-nums text-ink">{formatDuration(data.today.duration_seconds)}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
        <Badge tone={state.tone}>{state.label}</Badge>
        {data.today.is_late ? <span className="text-warning">Опоздание</span> : null}
        {data.stale_session ? <span className="text-warning">Прошлый уход не отмечен — исправит администратор.</span> : null}
      </div>
    </div>
  )
}
