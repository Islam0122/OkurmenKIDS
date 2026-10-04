import { t } from '@/i18n'
import { formatClock } from '@/lib/format'

import { Icon } from '../Icon'
import './Timer.css'

/** The countdown chip. `secondsLeft` null = no time limit. */
export function Timer({ secondsLeft }: { secondsLeft: number | null }) {
  if (secondsLeft === null) {
    return <span className="timer timer--none"><Icon name="infinity" /><span>{t.test.noLimit}</span></span>
  }
  const low = secondsLeft <= 60
  return (
    <span className={`timer${low ? ' timer--low' : ''}`} role="timer" aria-label={t.training.timer}>
      <Icon name="clock" />
      <span className="timer__value">{formatClock(secondsLeft)}</span>
    </span>
  )
}
