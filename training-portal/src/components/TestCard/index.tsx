import type { TrainingTest } from '@/types'

import { t } from '@/i18n'

import { Button } from '../Button'
import { Icon } from '../Icon'
import './TestCard.css'

/** Trainer card. Same structure for every card, so cards in a row line up:
 * icon + level, kicker, title (max 2 lines), four facts, button at the bottom. */
export function TestCard({ test, inProgress = false }: { test: TrainingTest; inProgress?: boolean }) {
  return (
    <article className="test-card">
      <div className="test-card__top">
        <span className="test-card__icon" aria-hidden="true"><Icon name="journal-code" /></span>
        <span className={`level level--${test.level}`}>{t.test.level[test.level] ?? test.level_display}</span>
      </div>
      <div className="test-card__heading">
        <div className="test-card__kicker">{t.test.title}</div>
        <h3 className="test-card__title" title={test.title}>{test.title}</h3>
      </div>
      <dl className="test-card__facts">
        <div><dt><Icon name="list-check" /><span className="visually-hidden">{t.test.facts.questions}</span></dt><dd>{t.test.questions(test.questions_count)}</dd></div>
        <div><dt><Icon name="clock" /><span className="visually-hidden">{t.test.facts.time}</span></dt><dd>{test.duration ? t.test.minutes(test.duration) : t.test.noLimit}</dd></div>
        <div><dt><Icon name="arrow-repeat" /><span className="visually-hidden">{t.test.attempts}</span></dt><dd>{t.test.attempts}: {test.max_attempts ?? t.test.unlimited}</dd></div>
        <div><dt><Icon name="trophy" /><span className="visually-hidden">{t.test.facts.passing}</span></dt><dd>{t.test.passing(test.passing_score)}</dd></div>
      </dl>
      <Button className="test-card__cta" to={`/training/${test.id}`} block variant={inProgress ? 'outline' : 'primary'}
        icon={inProgress ? 'arrow-clockwise' : 'play-fill'}>
        {inProgress ? t.test.continue : t.test.start}
      </Button>
    </article>
  )
}
