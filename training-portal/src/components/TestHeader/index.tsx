import { Icon } from '@/components/Icon'
import { Timer } from '@/components/Timer'
import type { TestModeConfig } from '@/components/TestScreen/modes'
import { t } from '@/i18n'

import './TestHeader.css'

/**
 * The one header of every test screen — Training and Exam alike: the logo,
 * «back» (only where the mode allows leaving), the mode badge, the test and
 * the student, the timer. A mode changes which pieces show, never the look.
 */
export function TestHeader({ config, title, student, secondsLeft, onLeave }: {
  config: TestModeConfig
  title: string
  student: string
  /** undefined: no timer (the result screen) */
  secondsLeft?: number | null
  /** asks before leaving; shown only when `config.header.canLeave` */
  onLeave?: () => void
}) {
  const { header, timer } = config
  return (
    <header className="test-header">
      <div className="test-header__inner">
        <div className="test-header__start">
          <img className="test-header__logo" src="/logo.png" alt="Okurmen Kids" width="32" height="32" />
          {header.canLeave && onLeave ? (
            <button type="button" className="test-header__back" aria-label={t.training.leave} onClick={onLeave}>
              <Icon name="chevron-left" /><span>{t.training.leave}</span>
            </button>
          ) : null}
          <span className="test-header__badge" title={header.label}><Icon name={header.icon} /><span>{header.label}</span></span>
        </div>
        <div className="test-header__title">
          <strong title={title}>{title}</strong>
          <span className="test-header__student"><Icon name="person" /><span>{student}</span></span>
        </div>
        {secondsLeft !== undefined ? <Timer secondsLeft={secondsLeft} warnAt={timer.warnAt} dangerAt={timer.dangerAt} /> : <span aria-hidden="true" />}
      </div>
    </header>
  )
}
