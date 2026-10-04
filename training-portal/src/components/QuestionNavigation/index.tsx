import { useEffect, useRef } from 'react'

import type { NavState } from '@/hooks/useTraining'
import { t } from '@/i18n'

import './QuestionNavigation.css'

const LABELS: Record<NavState, string> = {
  current: t.training.legend.current,
  answered: t.training.legend.answered,
  unanswered: t.training.legend.unanswered,
  correct: t.training.legend.correct,
  incorrect: t.training.legend.incorrect,
}

export function QuestionNavigation({ states, onSelect, showLegend = true }: {
  states: NavState[]
  onSelect: (index: number) => void
  showLegend?: boolean
}) {
  const list = useRef<HTMLDivElement>(null)
  const current = states.indexOf('current')

  useEffect(() => {
    // Keep the current question in view on phones (the row scrolls sideways).
    const item = list.current?.children[current] as HTMLElement | undefined
    item?.scrollIntoView?.({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [current])

  return (
    <div>
      <div ref={list} className="qnav" role="navigation" aria-label={t.training.navLabel}>
        {states.map((state, i) => (
          <button
            key={i}
            type="button"
            className={`qnav__item qnav__item--${state}`}
            aria-current={state === 'current' ? 'step' : undefined}
            aria-label={`${t.training.question} ${i + 1}: ${LABELS[state]}`}
            onClick={() => onSelect(i)}
          >
            {i + 1}
          </button>
        ))}
      </div>
      {showLegend ? (
        <div className="qnav-legend" aria-hidden="true">
          {(['current', 'answered', 'unanswered', 'correct', 'incorrect'] as NavState[]).map((state) => (
            <span key={state}><i className={`qnav__item--${state}`} />{LABELS[state]}</span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
