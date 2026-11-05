import { useId, useState } from 'react'
import type { MouseEvent } from 'react'

import type { TrendPoint } from '@/api/monthlyPerformance'
import { cn } from '@/utils/cn'

import { dayMonthLabel, formatCount, formatPct } from './format'

/** Динамика показателя по дням месяца — SVG без внешних библиотек.
 * Дни без данных — разрыв линии (ничего не придумывается и не
 * интерполируется). Проценты — шкала 0–100 %, количество — от 0 до
 * «круглого» максимума. Пунктир — среднее за месяц. */
export interface PerformanceChartProps {
  title: string
  points: TrendPoint[]
  /** Всего дней в месяце — ось X всегда на весь месяц. */
  daysInMonth: number
  average: number | null
  kind: 'percent' | 'count'
  /** Соединять точки через дни без значения (для количества — дни без занятий). */
  connectGaps?: boolean
  tv?: boolean
}

const PAD = { top: 16, right: 16, bottom: 34, left: 60 }

/** Верх шкалы для количества: 1, 2, 5 × 10ⁿ на деление, 4 деления. */
export function niceMax(value: number): number {
  if (value <= 0) return 4
  const raw = (value * 1.1) / 4
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power
  return Math.max(4, Math.ceil(step) * 4)
}

export function PerformanceChart({ title, points, daysInMonth, average, kind, connectGaps = false, tv = false }: PerformanceChartProps) {
  const titleId = useId()
  const [hover, setHover] = useState<number | null>(null)
  // На телевизоре график ниже (вся панель — в один экран 1920×1080); подписи осей крупные везде.
  // На телевизоре четыре графика в ряд — узкий viewBox, чтобы подписи осей оставались крупными.
  const WIDTH = tv ? 480 : 800
  const HEIGHT = tv ? 210 : 280
  const font = tv ? 20 : 18
  const percent = kind === 'percent'
  const format = (value: number | null) => (percent ? formatPct(value) : formatCount(value))

  const withValues = points.filter((p) => p.value !== null)
  const max = percent ? 100 : niceMax(Math.max(0, ...withValues.map((p) => p.value as number)))
  const grid = [0, 0.25, 0.5, 0.75, 1].map((r) => r * max)
  const innerW = WIDTH - PAD.left - PAD.right
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const x = (day: number) => PAD.left + (daysInMonth > 1 ? ((day - 1) / (daysInMonth - 1)) * innerW : innerW / 2)
  const y = (value: number) => PAD.top + innerH - (Math.max(0, Math.min(max, value)) / max) * innerH

  // Отрезки линии: подряд идущие дни с данными.
  const segments: TrendPoint[][] = []
  let current: TrendPoint[] = []
  for (const point of points) {
    if (point.value === null) {
      if (connectGaps) continue
      if (current.length) segments.push(current)
      current = []
    } else current.push(point)
  }
  if (current.length) segments.push(current)
  const tickEvery = daysInMonth > 20 ? 5 : 2
  const ticks = Array.from({ length: daysInMonth }, (_, i) => i + 1).filter((d) => d === 1 || d % tickEvery === 0)

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const svgX = ((event.clientX - rect.left) / rect.width) * WIDTH
    const day = Math.round(((svgX - PAD.left) / innerW) * (daysInMonth - 1)) + 1
    const nearest = points.find((p) => p.day === Math.max(1, Math.min(daysInMonth, day)))
    setHover(nearest ? nearest.day : null)
  }
  const hovered = hover !== null ? points.find((p) => p.day === hover) : undefined

  return (
    <section className={cn('card min-w-0', tv ? 'px-5 py-3' : 'card-body')} aria-labelledby={titleId}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id={titleId} className={cn('font-semibold text-ink', tv ? 'text-2xl' : 'section-title')}>{title}</h2>
        {average !== null ? (
          <span className={cn('text-ink-secondary', tv ? 'text-xl' : 'text-sm')}>
            Среднее: <b className="text-ink">{format(average)}</b>
          </span>
        ) : null}
      </div>
      {withValues.length === 0 ? (
        <p className={cn('flex items-center justify-center text-ink-muted', tv ? 'h-44 text-xl' : 'h-40 text-sm')}>
          Нет данных за этот месяц
        </p>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="w-full"
            role="img"
            aria-label={`${title}: ${withValues.map((p) => `${p.day} — ${format(p.value)}`).join(', ')}`}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          >
            {grid.map((g) => (
              <g key={g}>
                <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(g)} y2={y(g)} stroke="var(--color-border)" strokeWidth={1} />
                <text x={PAD.left - 8} y={y(g)} textAnchor="end" dominantBaseline="middle" fontSize={font} fill="var(--color-ink-muted)">
                  {percent ? `${g}%` : Math.round(g)}
                </text>
              </g>
            ))}
            {ticks.map((d) => (
              <text key={d} x={x(d)} y={HEIGHT - 8} textAnchor="middle" fontSize={font} fill="var(--color-ink-muted)">
                {d}
              </text>
            ))}
            {average !== null ? (
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(average)} y2={y(average)}
                stroke="var(--color-brand-200)" strokeWidth={2} strokeDasharray="6 6" />
            ) : null}
            {segments.map((segment) => (
              <path
                key={segment[0].day}
                d={segment.map((p, i) => `${i ? 'L' : 'M'}${x(p.day).toFixed(1)},${y(p.value as number).toFixed(1)}`).join(' ')}
                fill="none" stroke="var(--color-brand-500)" strokeWidth={tv ? 3 : 2.5} strokeLinejoin="round" strokeLinecap="round"
              />
            ))}
            {hovered ? (
              <line x1={x(hovered.day)} x2={x(hovered.day)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--color-border-strong)" strokeWidth={1} />
            ) : null}
            {withValues.map((p) => (
              <circle key={p.day} cx={x(p.day)} cy={y(p.value as number)} r={hover === p.day ? (tv ? 7 : 6) : tv ? 5 : 4}
                fill="var(--color-brand-500)" stroke="var(--color-surface)" strokeWidth={2} />
            ))}
          </svg>
          {hovered ? (
            <div
              className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-surface px-3 py-1.5 text-sm shadow-md"
              style={{ left: `${Math.min(85, Math.max(15, (x(hovered.day) / WIDTH) * 100))}%` }}
              role="status"
            >
              <span className="text-ink-secondary">{dayMonthLabel(hovered.date)}: </span>
              <b className="text-ink">{hovered.value === null ? 'нет данных' : format(hovered.value)}</b>
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}
