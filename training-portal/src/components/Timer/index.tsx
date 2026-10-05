import { t } from '@/i18n'
import { formatClock } from '@/lib/format'

import { Icon } from '../Icon'
import './Timer.css'

/** The countdown chip. `secondsLeft` null = no time limit. */
export function Timer({ secondsLeft, warnAt = 300, dangerAt = 60 }: {
  secondsLeft: number | null
  /** warning at or below this many seconds */
  warnAt?: number
  /** danger at or below this many seconds */
  dangerAt?: number
}) {
  if (secondsLeft === null) {
    return <span className="timer timer--none"><Icon name="infinity" /><span>{t.test.noLimit}</span></span>
  }
  // The icon changes with the colour, so the state never depends on colour alone.
  const tone = secondsLeft <= dangerAt ? ' timer--low' : secondsLeft <= warnAt ? ' timer--warning' : ''
  const icon = secondsLeft <= dangerAt ? 'alarm' : secondsLeft <= warnAt ? 'hourglass-split' : 'clock'
  return (
    <span className={`timer${tone}`} role="timer" aria-label={t.training.timer}>
      <Icon name={icon} />
      <span className="timer__value">{formatClock(secondsLeft)}</span>
    </span>
  )
}
