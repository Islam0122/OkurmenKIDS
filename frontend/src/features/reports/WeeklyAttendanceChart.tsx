import type { MonthlyReportWeekPoint } from '@/types/monthlyReport'
import { formatRuPercent } from '@/utils/format'

// Headroom (in % of the plot height) reserved above the topmost point for
// its value label, and below the lowest gridline before the week-label
// row — keeps points from ever sitting flush against an edge.
const TOP_MARGIN = 22
const BOTTOM_MARGIN = 8

/** A [lo, hi] Y-axis domain, rounded to multiples of 5 and at least 10
 * points wide, that comfortably contains every value — so a strong,
 * stable month (89.8 → 95.9 → 95.9 → 95.9) still reads as visible
 * movement instead of four dots flattened against a fixed 0-100% scale. */
function niceDomain(values: number[]): [number, number] {
  let lo = Math.max(0, Math.floor(Math.min(...values) / 5) * 5)
  let hi = Math.min(100, Math.ceil(Math.max(...values) / 5) * 5)
  if (hi - lo < 10) {
    lo = Math.max(0, lo - 5)
    hi = Math.min(100, hi + 5)
    if (hi - lo < 10) hi = Math.min(100, lo + 10)
  }
  return [lo, hi]
}

function niceTicks(lo: number, hi: number): number[] {
  const step = hi - lo <= 25 ? 5 : 10
  const ticks: number[] = []
  for (let value = lo; value <= hi + 0.001; value += step) ticks.push(Math.round(value))
  return ticks
}

export interface WeeklyAttendanceChartProps {
  weeks: MonthlyReportWeekPoint[]
  /** Tailwind height classes — callers pick the responsive range (spec:
   * ~220-240px mobile, ~280-320px desktop). */
  heightClassName?: string
}

/** A real line chart — line, points, a light grid, axis labels, and a
 * hover tooltip — built with plain SVG + a percentage-positioned HTML
 * overlay (no chart library needed: circular point markers stay round
 * regardless of the container's aspect ratio, which a pure non-uniformly
 * scaled SVG viewBox can't guarantee). */
export function WeeklyAttendanceChart({ weeks, heightClassName = 'h-[230px] sm:h-[300px]' }: WeeklyAttendanceChartProps) {
  if (weeks.length < 2) {
    return <p className="text-sm text-ink-muted">Недостаточно данных для динамики.</p>
  }

  const values = weeks.map((week) => week.percent)
  const [domainLo, domainHi] = niceDomain(values)
  const ticks = niceTicks(domainLo, domainHi)

  const plotTop = TOP_MARGIN
  const plotBottom = 100 - BOTTOM_MARGIN

  function yFor(value: number): number {
    const ratio = domainHi > domainLo ? (value - domainLo) / (domainHi - domainLo) : 0.5
    return plotBottom - ratio * (plotBottom - plotTop)
  }

  function xFor(index: number): number {
    return weeks.length > 1 ? (index / (weeks.length - 1)) * 100 : 50
  }

  const points = weeks.map((week, index) => ({ x: xFor(index), y: yFor(week.percent), week }))
  const pathD = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')

  return (
    <div>
      <div className={`relative w-full ${heightClassName}`} aria-hidden="true">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
          {ticks.map((tick) => (
            <line
              key={tick}
              x1={0}
              x2={100}
              y1={yFor(tick)}
              y2={yFor(tick)}
              stroke="var(--color-border)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <path d={pathD} fill="none" stroke="var(--color-brand-500)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        </svg>

        {/* Y-axis labels — plain HTML so they never get stretched by the SVG's non-uniform scaling. */}
        <div className="pointer-events-none absolute inset-y-0 left-0 flex flex-col justify-between py-0 text-[10px] text-ink-muted" style={{ paddingTop: `${TOP_MARGIN}%`, paddingBottom: `${100 - plotBottom}%` }}>
          {[...ticks].reverse().map((tick) => (
            <span key={tick} className="-translate-y-1/2">
              {tick}%
            </span>
          ))}
        </div>

        {/* Point markers, value labels, and hover tooltips — HTML overlay so circles never distort. */}
        {points.map(({ x, y, week }) => (
          <div key={week.label} className="group absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${x}%`, top: `${y}%` }}>
            <span className="absolute bottom-full left-1/2 mb-1 -translate-x-1/2 whitespace-nowrap text-xs font-semibold text-ink">
              {formatRuPercent(week.percent)}
            </span>
            <span className="block size-2.5 rounded-full border-2 border-surface bg-brand-500 shadow-sm" />
            <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-5 -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2.5 py-1.5 text-xs text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
              <p className="font-semibold">{week.label}</p>
              <p className="text-white/80">Посещаемость: {formatRuPercent(week.percent)}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-1 flex justify-between pl-6 text-xs text-ink-secondary sm:pl-7">
        {weeks.map((week) => (
          <span key={week.label}>{week.label}</span>
        ))}
      </div>
    </div>
  )
}
