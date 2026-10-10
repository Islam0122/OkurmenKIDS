import { useState } from 'react'

import { som } from './shared'

/** Начислено — бренд, выплачено — info: пара прошла проверку на различимость при дальтонизме. */
export const SERIES = [
  { key: 'accrued', label: 'Начислено', color: 'var(--color-brand-500)' },
  { key: 'paid', label: 'Выплачено', color: 'var(--color-info)' },
] as const

export interface MonthBar {
  label: string
  accrued: number
  paid: number
}

const H = 160
const PAD_TOP = 8
const PAD_BOTTOM = 20

/**
 * Начислено и выплачено по месяцам — сгруппированные столбцы на одной оси.
 * Подсказка при наведении/фокусе; легенда всегда видна; значения дублируются
 * таблицей под графиком, поэтому цвет — не единственный носитель смысла.
 */
export function MonthlyBarsChart({ title, points }: { title: string; points: MonthBar[] }) {
  const [active, setActive] = useState<number | null>(null)
  const max = Math.max(1, ...points.flatMap((p) => [p.accrued, p.paid]))
  const slot = 36
  const width = Math.max(points.length * slot, 200)
  const bar = 12
  const inner = H - PAD_TOP - PAD_BOTTOM
  const y = (v: number) => PAD_TOP + inner - (v / max) * inner
  const hovered = active !== null ? points[active] : null

  return (
    <div className="card card-body min-w-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">{title}</h2>
        <ul className="flex gap-3 text-xs text-ink-secondary" aria-label="Легенда">
          {SERIES.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />{s.label}
            </li>
          ))}
        </ul>
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${H}`} className="w-full" role="img"
          aria-label={`${title}: ${points.map((p) => `${p.label} — начислено ${p.accrued}, выплачено ${p.paid}`).join('; ')}`}>
          <line x1={0} x2={width} y1={PAD_TOP + inner} y2={PAD_TOP + inner} stroke="var(--color-border)" />
          {points.map((p, i) => {
            const x0 = i * slot + (slot - bar * 2 - 2) / 2
            return (
              <g key={p.label} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)} onBlur={() => setActive(null)} tabIndex={0}>
                <rect x={i * slot} y={0} width={slot} height={H} fill={active === i ? 'var(--color-surface-hover)' : 'transparent'} />
                {SERIES.map((s, k) => {
                  const value = p[s.key]
                  const top = y(value)
                  return (
                    <rect key={s.key} x={x0 + k * (bar + 2)} y={top} width={bar}
                      height={Math.max(0, PAD_TOP + inner - top)} rx={3} fill={s.color} />
                  )
                })}
                <text x={i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize={9} fill="var(--color-ink-muted)">{p.label}</text>
              </g>
            )
          })}
        </svg>
        {hovered ? (
          <div className="pointer-events-none absolute right-0 top-0 rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-sm" role="status">
            <p className="font-medium text-ink">{hovered.label}</p>
            <p className="text-ink-secondary">Начислено: {som(hovered.accrued)}</p>
            <p className="text-ink-secondary">Выплачено: {som(hovered.paid)}</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}

/** Горизонтальные столбцы одной величины (расходы по направлениям) с подписью значения. */
export function HorizontalBars({ title, rows }: { title: string; rows: { label: string; value: number; hint?: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="card card-body min-w-0">
      <h2 className="section-title mb-3">{title}</h2>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.label} title={r.hint}>
            <div className="flex justify-between gap-2 text-sm">
              <span className="text-ink-secondary">{r.label}</span>
              <span className="tabular-nums text-ink">{som(r.value)}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-hover">
              <div className="h-full rounded-full bg-brand-500" style={{ width: `${(r.value / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
