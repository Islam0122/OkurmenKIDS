import { useEffect, useState } from 'react'

import type { TrainingResult } from '@/types'

import { t } from '@/i18n'
import { formatDuration } from '@/lib/format'

import { Icon } from '../Icon'
import './ResultCard.css'

export function resultMessage(percent: number): string {
  if (percent >= 90) return t.result.messages.excellent
  if (percent >= 70) return t.result.messages.good
  if (percent >= 50) return t.result.messages.fair
  return t.result.messages.low
}

/** Counts up to `target` once (respects reduced motion). */
function useCountUp(target: number, durationMs = 1200): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setValue(target); return }
    let frame = 0
    const started = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - started) / durationMs)
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])
  return value
}

const RADIUS = 52
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function ResultCard({ result }: { result: TrainingResult }) {
  const shown = useCountUp(result.percent)
  const [drawn, setDrawn] = useState(false)
  useEffect(() => { const id = requestAnimationFrame(() => setDrawn(true)); return () => cancelAnimationFrame(id) }, [])
  const graded = result.total - result.ungraded
  const seconds = (result.finishedAt - result.startedAt) / 1000

  return (
    <section className="result-card" aria-label={t.result.title}>
      <div className="score-ring">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <defs>
            <linearGradient id="scoreGradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#fbbf4a" />
              <stop offset="100%" stopColor="#f5a524" />
            </linearGradient>
          </defs>
          <circle className="score-ring__track" cx="60" cy="60" r={RADIUS} fill="none" strokeWidth="10" />
          <circle
            className="score-ring__value" cx="60" cy="60" r={RADIUS} fill="none" strokeWidth="10"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={drawn ? CIRCUMFERENCE * (1 - result.percent / 100) : CIRCUMFERENCE}
          />
        </svg>
        <div className="score-ring__label">
          <span className="score-ring__percent">{shown}%</span>
          <span className="score-ring__fraction">{result.correct} / {graded}</span>
        </div>
      </div>
      <div>
        <span className="result-card__name"><Icon name="person-fill" />{result.studentName}</span>
        <h1 className="result-card__message">{resultMessage(result.percent)}</h1>
        <p className="result-card__test">{result.testTitle}</p>
        <dl className="result-stats">
          <div className="result-stat result-stat--good"><dt className="result-stat__label"><Icon name="check-circle-fill" />{t.result.correct}</dt><dd className="result-stat__value" style={{ margin: 0 }}>{result.correct}</dd></div>
          <div className="result-stat result-stat--bad"><dt className="result-stat__label"><Icon name="x-circle-fill" />{t.result.incorrect}</dt><dd className="result-stat__value" style={{ margin: 0 }}>{result.incorrect}</dd></div>
          <div className="result-stat result-stat--skip"><dt className="result-stat__label"><Icon name="dash-circle-fill" />{t.result.skipped}</dt><dd className="result-stat__value" style={{ margin: 0 }}>{result.skipped}</dd></div>
          <div className="result-stat result-stat--time"><dt className="result-stat__label"><Icon name="stopwatch-fill" />{t.result.time}</dt><dd className="result-stat__value" style={{ margin: 0 }}>{formatDuration(seconds)}</dd></div>
        </dl>
      </div>
    </section>
  )
}
