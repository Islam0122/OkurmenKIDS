export interface TrendChartPoint {
  label: string
  value: number
}

export interface TrendChartProps {
  title: string
  points: TrendChartPoint[]
  max: number
  valueSuffix?: string
  color?: string
}

const WIDTH = 320
const HEIGHT = 120
const PADDING = 12
/** At most this many X-axis labels, whatever the number of points — one
 * label per daily snapshot is what used to push the page 2000px wide. */
const MAX_TICKS = 5

function tickIndexes(count: number): number[] {
  if (count <= MAX_TICKS) return Array.from({ length: count }, (_, index) => index)
  const step = (count - 1) / (MAX_TICKS - 1)
  return Array.from({ length: MAX_TICKS }, (_, index) => Math.round(index * step))
}

/** Dependency-free SVG line chart — plots real KPI snapshots only, never interpolated or invented points. */
export function TrendChart({ title, points, max, valueSuffix = '', color = 'var(--color-brand-500)' }: TrendChartProps) {
  const innerWidth = WIDTH - PADDING * 2
  const innerHeight = HEIGHT - PADDING * 2

  const coords = points.map((point, index) => {
    const x = points.length > 1 ? PADDING + (index / (points.length - 1)) * innerWidth : PADDING + innerWidth / 2
    const ratio = max > 0 ? Math.min(1, point.value / max) : 0
    const y = PADDING + innerHeight - ratio * innerHeight
    return { x, y, point }
  })

  const path = coords.map((coord, index) => `${index === 0 ? 'M' : 'L'}${coord.x.toFixed(1)},${coord.y.toFixed(1)}`).join(' ')

  return (
    <div className="card card-body min-w-0">
      <h2 className="section-title mb-3">{title}</h2>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${title}: ${points.map((point) => `${point.label} — ${point.value}${valueSuffix}`).join(', ')}`}
        className="w-full"
      >
        {coords.length > 1 ? <path d={path} fill="none" stroke={color} strokeWidth={2} /> : null}
        {coords.map((coord) => (
          <circle key={coord.point.label} cx={coord.x} cy={coord.y} r={3} fill={color} />
        ))}
      </svg>
      <div className="relative mt-2 h-4 text-xs text-ink-muted" aria-hidden>
        {tickIndexes(coords.length).map((index, position, all) => {
          const coord = coords[index]
          const align =
            position === 0 ? 'translate-x-0' : position === all.length - 1 ? '-translate-x-full' : '-translate-x-1/2'
          return (
            <span
              key={coord.point.label}
              className={`absolute top-0 whitespace-nowrap ${align}`}
              style={{ left: `${(coord.x / WIDTH) * 100}%` }}
            >
              {coord.point.label}
            </span>
          )
        })}
      </div>
    </div>
  )
}
