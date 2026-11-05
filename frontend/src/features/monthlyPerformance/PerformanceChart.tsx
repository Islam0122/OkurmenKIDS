import { useId, useState } from 'react'
import type { MouseEvent } from 'react'

import type { TrendPoint } from '@/api/monthlyPerformance'
import { cn } from '@/utils/cn'

import { dayMonthLabel, formatPct } from './format'

/** Динамика процента по дням месяца — SVG без внешних библиотек.
 * Дни без данных — разрыв линии (ничего не придумывается и не
 * интерполируется), шкала 0–100 %, пунктир — среднее за месяц. */
export interface PerformanceChartProps {
  title: string
  points: TrendPoint[]
  /** Всего дней в месяце — ось X всегда на весь месяц. */
  daysInMonth: number
  average: number | null
  tv?: boolean
}

const WIDTH = 800
const PAD = { top: 16, right: 16, bottom: 34, left: 60 }
const GRID = [0, 25, 50, 75, 100]

export function PerformanceChart({ title, points, daysInMonth, average, tv = false }: PerformanceChartProps) {
  const titleId = useId()
  const [hover, setHover] = useState<number | null>(null)
  // На телевизоре график ниже (вся панель — в один экран 1920×1080), подписи осей — крупные везде.
  const HEIGHT = tv ? 210 : 260
  const font = tv ? 15 : 18
  const innerW = WIDTH - PAD.left - PAD.right
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const x = (day: number) => PAD.left + (daysInMonth > 1 ? ((day - 1) / (daysInMonth - 1)) * innerW : innerW / 2)
  const y = (value: number) => PAD.top + innerH - (Math.max(0, Math.min(100, value)) / 100) * innerH

  // Отрезки линии: подряд идущие дни с данными.
  const segments: TrendPoint[][] = []
  let current: TrendPoint[] = []
  for (const point of points) {
    if (point.value === null) {
      if (current.length) segments.push(current)
      current = []
    } else current.push(point)
  }
  if (current.length) segments.push(current)
  const withValues = points.filter((p) => p.value !== null)
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
    <section className={cn('card min-w-0', tv ? 'px-6 py-4' : 'card-body')} aria-labelledby={titleId}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={titleId} className={cn('font-semibold text-ink', tv ? 'text-3xl' : 'section-title')}>{title}</h2>
        {average !== null ? (
          <span className={cn('text-ink-secondary', tv ? 'text-2xl' : 'text-sm')}>
            Среднее: <b className="text-ink">{formatPct(average)}</b>
          </span>
        ) : null}
      </div>
      {withValues.length === 0 ? (
        <p className={cn('flex items-center justify-center text-ink-muted', tv ? 'h-52 text-2xl' : 'h-40 text-sm')}>
          Нет данных за этот месяц
        </p>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="w-full"
            role="img"
            aria-label={`${title}: ${withValues.map((p) => `${p.day} — ${formatPct(p.value)}`).join(', ')}`}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          >
            {GRID.map((g) => (
              <g key={g}>
                <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(g)} y2={y(g)} stroke="var(--color-border)" strokeWidth={1} />
                <text x={PAD.left - 8} y={y(g)} textAnchor="end" dominantBaseline="middle" fontSize={font} fill="var(--color-ink-muted)">
                  {g}%
                </text>
              </g>
            ))}
            {ticks.map((d) => (
              <text key={d} x={x(d)} y={HEIGHT - 10} textAnchor="middle" fontSize={font} fill="var(--color-ink-muted)">
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
                fill="none" stroke="var(--color-brand-500)" strokeWidth={tv ? 4 : 2.5} strokeLinejoin="round" strokeLinecap="round"
              />
            ))}
            {hovered ? (
              <line x1={x(hovered.day)} x2={x(hovered.day)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--color-border-strong)" strokeWidth={1} />
            ) : null}
            {withValues.map((p) => (
              <circle key={p.day} cx={x(p.day)} cy={y(p.value as number)} r={hover === p.day ? (tv ? 8 : 6) : tv ? 6 : 4}
                fill="var(--color-brand-500)" stroke="var(--color-surface)" strokeWidth={2} />
            ))}
          </svg>
          {hovered ? (
            <div
              className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm shadow-md"
              style={{ left: `${(x(hovered.day) / WIDTH) * 100}%` }}
              role="status"
            >
              <span className="text-ink-secondary">{dayMonthLabel(hovered.date)}: </span>
              <b className="text-ink">{hovered.value === null ? 'нет данных' : formatPct(hovered.value)}</b>
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}
