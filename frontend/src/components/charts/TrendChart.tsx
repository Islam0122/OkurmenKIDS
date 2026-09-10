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
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="mb-3 text-sm font-medium text-ink-secondary">{title}</p>
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
      <div className="mt-2 flex justify-between text-xs text-ink-muted">
        {points.map((point) => (
          <span key={point.label}>{point.label}</span>
        ))}
      </div>
    </div>
  )
}
