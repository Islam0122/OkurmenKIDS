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
    // Only the row itself scrolls — scrollIntoView would also move the page.
    const row = list.current
    const item = row?.children[current] as HTMLElement | undefined
    if (!row || !item || row.scrollWidth <= row.clientWidth) return
    const left = item.offsetLeft - row.offsetLeft - (row.clientWidth - item.offsetWidth) / 2
    row.scrollTo?.({ left: Math.max(0, left), behavior: 'smooth' })
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
