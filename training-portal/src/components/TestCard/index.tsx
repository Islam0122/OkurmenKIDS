import type { Test } from '@/types'

import { t } from '@/i18n'

import { Button } from '../Button'
import { Icon } from '../Icon'
import './TestCard.css'

const SUBJECT_ICONS: Record<string, string> = { Python: 'filetype-py', 'HTML / CSS': 'filetype-html', JavaScript: 'filetype-js' }

export function TestCard({ test, inProgress = false }: { test: Test; inProgress?: boolean }) {
  return (
    <article className="test-card">
      <div className="test-card__top">
        <span className="test-card__icon"><Icon name={SUBJECT_ICONS[test.subject] ?? 'code-slash'} /></span>
        <span className={`level level--${test.level}`}><Icon name="reception-3" />{t.test.level[test.level]}</span>
      </div>
      <div>
        <div className="test-card__kicker">{t.test.title} · {test.subject}</div>
        <h3 className="test-card__title">{test.title}</h3>
      </div>
      {test.description ? <p className="test-card__desc">{test.description}</p> : null}
      <dl className="test-card__facts">
        <div><dt>{t.test.facts.questions}</dt><Icon name="list-check" /><dd>{t.test.questions(test.questions.length)}</dd></div>
        <div><dt>{t.test.facts.time}</dt><Icon name="clock" /><dd>{test.duration ? t.test.minutes(test.duration) : t.test.noLimit}</dd></div>
        <div><dt>{t.test.attempts}</dt><Icon name="arrow-repeat" /><dd>{t.test.attempts}: {test.maxAttempts ?? t.test.unlimited}</dd></div>
        <div><dt>{t.test.facts.topics}</dt><Icon name="bookmarks" /><dd>{test.topics ?? test.subject}</dd></div>
      </dl>
      <div className="test-card__foot">
        <Button to={`/training/${test.id}`} block icon={inProgress ? 'arrow-clockwise' : 'play-circle'}>
          {inProgress ? t.test.continue : t.test.start}
        </Button>
      </div>
    </article>
  )
}
