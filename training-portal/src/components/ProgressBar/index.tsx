import './ProgressBar.css'

export function ProgressBar({ value, max, label }: { value: number; max: number; label?: string }) {
  const percent = max ? Math.round((value / max) * 100) : 0
  return (
    <div className="progress">
      {label ? (
        <div className="progress__labels"><strong>{label}</strong><span>{percent}%</span></div>
      ) : null}
      <div className="progress__track" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
        <div className="progress__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
