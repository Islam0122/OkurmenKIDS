import { CalendarClock, Hourglass, TriangleAlert } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { EstimateStatus, MyEstimate } from '@/types/accounting'

import { formatDate, som } from './shared'

const ESTIMATE_TONE: Record<EstimateStatus, BadgeTone> = {
  ESTIMATED: 'muted',
  BLOCK_IN_PROGRESS: 'info',
  READY_FOR_ACCRUAL: 'brand',
}

/** Статус предварительного расчёта — всегда текстом и с иконкой, не только цветом. */
export function EstimateStatusBadge({ status, label }: { status: EstimateStatus; label: string }) {
  return (
    <Badge tone={ESTIMATE_TONE[status]}>
      <Hourglass className="mr-1 inline size-3" aria-hidden />{label}
    </Badge>
  )
}

export function LessonProgress({ done, total }: { done: number; total: number }) {
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-ink-secondary">Прогресс</span>
        <span className="font-medium tabular-nums text-ink">{done} из {total} уроков</span>
      </div>
      <div
        role="progressbar"
        aria-label={`Проведено ${done} из ${total} уроков`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-hover"
      >
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

/**
 * Карточка блока с предварительной зарплатой. Визуально отделена от
 * начислений (пунктирная рамка, пометка «предварительно»): это оценка по
 * текущим условиям, а не долг и не начисление.
 */
export function EstimateCard({ estimate: e }: { estimate: MyEstimate }) {
  return (
    <article className="rounded-xl border border-dashed border-border bg-surface p-4" aria-label={`Блок группы ${e.group_name}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-ink">{e.group_name}</h3>
          <p className="text-xs text-ink-muted">
            {e.course_name}{e.subjects.length ? ` · ${e.subjects.join(', ')}` : ''} · блок №{e.cycle_number}
          </p>
        </div>
        <EstimateStatusBadge status={e.status} label={e.status_display} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <dt className="text-ink-secondary">Ученики</dt><dd className="text-right tabular-nums">{e.student_count}</dd>
        <dt className="text-ink-secondary">Цена за ученика</dt><dd className="text-right tabular-nums">{som(e.price_per_student)}/мес</dd>
        <dt className="text-ink-secondary">Процент тренера</dt><dd className="text-right tabular-nums">{Number(e.percentage)}%</dd>
      </dl>

      <div className="mt-3"><LessonProgress done={e.lessons_done} total={e.required_lessons} /></div>
      <p className="mt-1 text-xs text-ink-muted">
        {e.lessons_remaining > 0 ? `Осталось провести: ${e.lessons_remaining}` : 'Все уроки блока проведены'}
      </p>

      <div className="mt-3 border-t border-border pt-3">
        <p className="text-xs text-ink-secondary">Предварительная зарплата</p>
        <p className="text-xl font-semibold tabular-nums text-ink">{som(e.expected_amount)}</p>
        <p className="mt-1 flex items-center gap-1 text-xs text-ink-secondary">
          <CalendarClock className="size-3.5 shrink-0" aria-hidden />
          {e.expected_payment_date ? `ожидаемая выплата ${formatDate(e.expected_payment_date)}` : 'дата выплаты — после завершения блока'}
        </p>
      </div>
      {e.warnings.map((w) => (
        <p key={w} className="mt-2 flex gap-1 text-xs text-warning"><TriangleAlert className="size-3.5 shrink-0" aria-hidden />{w}</p>
      ))}
    </article>
  )
}
