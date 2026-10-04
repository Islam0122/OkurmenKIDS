import type { KeyboardEvent } from 'react'

import type { Answer, Question, QuestionOutcome } from '@/types'

import { t } from '@/i18n'
import { correctAnswerText, gradeQuestion } from '@/lib/grading'

import { Icon } from '../Icon'
import './QuestionCard.css'

const TYPE_TAGS: Record<Question['type'], { icon: string; label: string }> = {
  single: { icon: 'record-circle', label: t.training.single },
  multiple: { icon: 'check2-square', label: t.training.multiple },
  text: { icon: 'input-cursor-text', label: 'Текст' },
  code: { icon: 'code-slash', label: 'Код' },
}

/** Question text; a block after an empty line is shown as code. */
function QuestionText({ text }: { text: string }) {
  const [lead, ...blocks] = text.split('\n\n')
  return (
    <>
      <h2 className="qcard__text">{lead}</h2>
      {blocks.length ? <pre className="qcard__code">{blocks.join('\n\n')}</pre> : null}
    </>
  )
}

export function Feedback({ question, outcome }: { question: Question; outcome: QuestionOutcome }) {
  if (question.type === 'code') {
    return (
      <div className="feedback feedback--self" role="status">
        <p className="feedback__title"><Icon name="lightbulb" />{t.training.selfCheck}</p>
        <p className="feedback__row">{t.training.selfCheckText}</p>
        {question.correctAnswer ? (
          <div className="feedback__row"><strong>{t.training.sample}</strong><pre>{correctAnswerText(question)}</pre></div>
        ) : null}
        {question.explanation ? <div className="feedback__row"><strong>{t.training.explanation}</strong>{question.explanation}</div> : null}
      </div>
    )
  }
  const right = outcome === 'correct'
  return (
    <div className={`feedback feedback--${right ? 'correct' : 'incorrect'}`} role="status">
      <p className="feedback__title">
        <Icon name={right ? 'check-circle-fill' : 'x-circle-fill'} />
        {right ? t.training.correct : t.training.incorrect}
      </p>
      {!right ? <div className="feedback__row"><strong>{t.training.correctAnswer}</strong>{correctAnswerText(question)}</div> : null}
      {question.explanation ? <div className="feedback__row"><strong>{t.training.explanation}</strong>{question.explanation}</div> : null}
    </div>
  )
}

interface QuestionCardProps {
  question: Question
  index: number
  total: number
  answer: Answer | undefined
  onChange: (answer: Answer) => void
  /** answer checked: locked, correct/incorrect marks visible */
  revealed: boolean
  /** show the feedback panel (test.showExplanation) */
  showFeedback: boolean
}

export function QuestionCard({ question, index, total, answer, onChange, revealed, showFeedback }: QuestionCardProps) {
  const chosen = answer?.options ?? []
  const correct = Array.isArray(question.correctAnswer) ? question.correctAnswer : [question.correctAnswer]
  const outcome = gradeQuestion(question, answer)
  const tag = TYPE_TAGS[question.type]

  const toggle = (id: string) => {
    if (revealed) return
    if (question.type === 'single') onChange({ options: [id] })
    else onChange({ options: chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id] })
  }

  const onCodeKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Tab') return
    event.preventDefault()
    const el = event.currentTarget
    const { selectionStart: start, selectionEnd: end, value } = el
    const next = `${value.slice(0, start)}    ${value.slice(end)}`
    onChange({ text: next })
    requestAnimationFrame(() => el.setSelectionRange(start + 4, start + 4))
  }

  return (
    <section className="qcard" key={question.id} aria-labelledby={`q-${question.id}`}>
      <div className="qcard__meta">
        <span className="qcard__num" id={`q-${question.id}`}>{t.training.question} {index + 1} / {total}</span>
        <span className="qcard__tag"><Icon name={tag.icon} />{tag.label}</span>
        {question.language ? <span className="qcard__tag"><Icon name="terminal" />{question.language}</span> : null}
      </div>
      <QuestionText text={question.question} />
      {question.imageUrl ? <img className="qcard__image" src={question.imageUrl} alt="" loading="lazy" /> : null}

      <div className="qcard__body">
        {question.type === 'single' || question.type === 'multiple' ? (
          <>
            <p className="options__hint"><Icon name={tag.icon} />{tag.label}</p>
            <div className="options" role={question.type === 'single' ? 'radiogroup' : 'group'} aria-labelledby={`q-${question.id}`}>
              {(question.options ?? []).map((option, i) => {
                const selected = chosen.includes(option.id)
                const isRight = correct.includes(option.id)
                const state = revealed && isRight ? 'is-correct' : revealed && selected ? 'is-wrong' : selected ? 'is-selected' : ''
                const stateIcon = state === 'is-correct' ? 'check-circle-fill' : state === 'is-wrong' ? 'x-circle-fill' : 'check-circle-fill'
                return (
                  <button
                    key={option.id}
                    type="button"
                    role={question.type === 'single' ? 'radio' : 'checkbox'}
                    aria-checked={selected}
                    className={`option${question.type === 'multiple' ? ' option--multi' : ''} ${state}`}
                    disabled={revealed}
                    onClick={() => toggle(option.id)}
                  >
                    <span className="option__letter">{String.fromCharCode(65 + i)}</span>
                    <span className="option__text">{option.text}</span>
                    <Icon name={stateIcon} className="option__state" />
                  </button>
                )
              })}
            </div>
          </>
        ) : (
          <>
            <label className="visually-hidden" htmlFor={`answer-${question.id}`}>{t.training.textPlaceholder}</label>
            <textarea
              id={`answer-${question.id}`}
              className={[
                'answer-input',
                question.type === 'code' && 'answer-input--code',
                revealed && question.type === 'text' && (outcome === 'correct' ? 'is-correct' : 'is-wrong'),
              ].filter(Boolean).join(' ')}
              value={answer?.text ?? (question.type === 'code' ? question.starterCode ?? '' : '')}
              placeholder={question.type === 'code' ? t.training.codePlaceholder : t.training.textPlaceholder}
              spellCheck={question.type !== 'code'}
              rows={question.type === 'code' ? 10 : 3}
              disabled={revealed}
              onKeyDown={question.type === 'code' ? onCodeKey : undefined}
              onChange={(e) => onChange({ text: e.target.value })}
            />
          </>
        )}
      </div>

      {revealed && showFeedback ? <Feedback question={question} outcome={outcome} /> : null}
    </section>
  )
}
