import { t } from '@/i18n'
import { formatClock } from '@/lib/format'

import { Icon } from '../Icon'
import './Timer.css'

/** The countdown chip. `secondsLeft` null = no time limit. */
export function Timer({ secondsLeft }: { secondsLeft: number | null }) {
  if (secondsLeft === null) {
    return <span className="timer timer--none"><Icon name="infinity" /><span>{t.test.noLimit}</span></span>
  }
  // Calm by default; amber in the last 5 minutes, red in the last minute.
  const tone = secondsLeft <= 60 ? ' timer--low' : secondsLeft <= 300 ? ' timer--warning' : ''
  return (
    <span className={`timer${tone}`} role="timer" aria-label={t.training.timer}>
      <Icon name="clock" />
      <span className="timer__value">{formatClock(secondsLeft)}</span>
    </span>
  )
}
