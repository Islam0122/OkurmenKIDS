import type { TrainingTest } from '@/types'

import { t } from '@/i18n'

import { Button } from '../Button'
import { Icon } from '../Icon'
import './TestCard.css'

/** Compact trainer card: title, level, a one-line summary and the start button. */
export function TestCard({ test, inProgress = false }: { test: TrainingTest; inProgress?: boolean }) {
  return (
    <article className="test-card">
      <div className="test-card__head">
        <span className="test-card__icon" aria-hidden="true"><Icon name="journal-code" /></span>
        <h3 className="test-card__title">{test.title}</h3>
        <span className={`level level--${test.level}`}>{t.test.level[test.level] ?? test.level_display}</span>
      </div>
      {test.description ? <p className="test-card__desc">{test.description}</p> : null}
      <ul className="test-card__meta" aria-label={t.test.title}>
        <li><Icon name="list-check" />{t.test.questions(test.questions_count)}</li>
        <li><Icon name="clock" />{test.duration ? t.test.minutes(test.duration) : t.test.noLimit}</li>
        <li title={t.test.facts.passing}><Icon name="trophy" />{test.passing_score}%</li>
      </ul>
      <Button to={`/training/${test.id}`} size="sm" block variant={inProgress ? 'outline' : 'primary'}
        icon={inProgress ? 'arrow-clockwise' : 'play-fill'}>
        {inProgress ? t.test.continue : t.test.start}
      </Button>
    </article>
  )
}
