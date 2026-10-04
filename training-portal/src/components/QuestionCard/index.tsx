import type { KeyboardEvent } from 'react'

import type { AnswerFeedback, AnswerValue, Question } from '@/types'

import { t } from '@/i18n'

import { Icon } from '../Icon'
import './QuestionCard.css'

// label — the question type (badge); hint — what to do (above the options).
const TYPE_TAGS: Record<Question['type'], { icon: string; label: string; hint?: string }> = {
  single_choice: { icon: 'record-circle', label: t.training.typeSingle, hint: t.training.single },
  multiple_choice: { icon: 'check2-square', label: t.training.typeMultiple, hint: t.training.multiple },
  text: { icon: 'input-cursor-text', label: 'Текст' },
  code: { icon: 'code-slash', label: 'Код' },
}

const EMPTY: AnswerValue = { options: [], text: '' }

/** The backend's verdict for a checked answer. */
export function Feedback({ question, feedback }: { question: Question; feedback: AnswerFeedback }) {
  if (feedback.status === 'pending') {
    return (
      <div className="feedback feedback--self" role="status">
        <p className="feedback__title"><Icon name="hourglass-split" />{t.training.pending}</p>
        <p className="feedback__row">{t.training.pendingText}</p>
        {feedback.code_examples.length ? (
          <div className="feedback__row">
            <strong>{t.training.examples}</strong>
            <pre>{feedback.code_examples.map((ex) => `${ex.input || '—'}  →  ${ex.expected_output}`).join('\n')}</pre>
          </div>
        ) : null}
        {feedback.explanation ? <div className="feedback__row"><strong>{t.training.explanation}</strong>{feedback.explanation}</div> : null}
      </div>
    )
  }
  const right = feedback.status === 'correct'
  const correctText = question.options.length
    ? question.options.filter((o) => feedback.correct_option_ids.includes(o.id)).map((o) => o.text || '—').join(', ')
    : feedback.correct_answers[0] ?? ''
  return (
    <div className={`feedback feedback--${right ? 'correct' : 'incorrect'}`} role="status">
      <p className="feedback__title">
        <Icon name={right ? 'check-circle-fill' : 'x-circle-fill'} />
        {right ? t.training.correct : t.training.incorrect}
      </p>
      {!right && correctText ? <div className="feedback__row"><strong>{t.training.correctAnswer}</strong>{correctText}</div> : null}
      {feedback.explanation ? <div className="feedback__row"><strong>{t.training.explanation}</strong>{feedback.explanation}</div> : null}
    </div>
  )
}

interface QuestionCardProps {
  question: Question
  index: number
  total: number
  answer: AnswerValue | undefined
  onChange: (answer: AnswerValue) => void
  /** checked: the answer is locked; the feedback (if the test shows it) is drawn */
  locked: boolean
  feedback: AnswerFeedback | null
}

export function QuestionCard({ question, index, total, answer, onChange, locked, feedback }: QuestionCardProps) {
  const value = answer ?? EMPTY
  const tag = TYPE_TAGS[question.type]
  const isChoice = question.type === 'single_choice' || question.type === 'multiple_choice'
  const [lead, ...codeBlocks] = question.text.split('\n\n')

  const toggle = (id: string) => {
    if (locked) return
    if (question.type === 'single_choice') onChange({ options: [id], text: '' })
    else onChange({ options: value.options.includes(id) ? value.options.filter((x) => x !== id) : [...value.options, id], text: '' })
  }

  const onCodeKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Tab') return
    event.preventDefault()
    const el = event.currentTarget
    const { selectionStart: start, selectionEnd: end, value: text } = el
    onChange({ options: [], text: `${text.slice(0, start)}    ${text.slice(end)}` })
    requestAnimationFrame(() => el.setSelectionRange(start + 4, start + 4))
  }

  return (
    <section className="qcard" aria-labelledby={`q-${question.id}`}>
      <div className="qcard__meta">
        <span className="qcard__num" id={`q-${question.id}`}>{t.training.question} {index + 1} / {total}</span>
        <span className="qcard__tag"><Icon name={tag.icon} />{tag.label}</span>
        {question.language ? <span className="qcard__tag"><Icon name="terminal" />{question.language}</span> : null}
      </div>
      <h2 className="qcard__text">{lead}</h2>
      {codeBlocks.length ? <pre className="qcard__code">{codeBlocks.join('\n\n')}</pre> : null}
      {question.image_url ? <img className="qcard__image" src={question.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : null}
      {question.hint ? <p className="qcard__hint"><Icon name="lightbulb" /><span><strong>{t.training.hint}</strong> {question.hint}</span></p> : null}

      <div className="qcard__body">
        {isChoice ? (
          <>
            <p className="options__hint">{tag.hint}</p>
            <div className="options" role={question.type === 'single_choice' ? 'radiogroup' : 'group'} aria-labelledby={`q-${question.id}`}>
              {question.options.map((option, i) => {
                const selected = value.options.includes(option.id)
                const isRight = Boolean(feedback && feedback.correct_option_ids.includes(option.id))
                const state = feedback && isRight ? 'is-correct' : feedback && selected ? 'is-wrong' : selected ? 'is-selected' : ''
                return (
                  <button
                    key={option.id}
                    type="button"
                    role={question.type === 'single_choice' ? 'radio' : 'checkbox'}
                    aria-checked={selected}
                    className={`option${question.type === 'multiple_choice' ? ' option--multi' : ''} ${state}`}
                    disabled={locked}
                    onClick={() => toggle(option.id)}
                  >
                    <span className="option__letter">{String.fromCharCode(65 + i)}</span>
                    <span className="option__text">
                      {option.image_url ? <img className="option__img" src={option.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : null}
                      {option.text}
                    </span>
                    <Icon name={state === 'is-wrong' ? 'x-circle-fill' : 'check-circle-fill'} className="option__state" />
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
                feedback && feedback.status !== 'pending' && (feedback.status === 'correct' ? 'is-correct' : 'is-wrong'),
              ].filter(Boolean).join(' ')}
              value={answer ? value.text : question.type === 'code' ? question.starter_code : ''}
              placeholder={question.type === 'code' ? t.training.codePlaceholder : t.training.textPlaceholder}
              spellCheck={question.type !== 'code'}
              rows={question.type === 'code' ? 10 : 3}
              disabled={locked}
              onKeyDown={question.type === 'code' ? onCodeKey : undefined}
              onChange={(e) => onChange({ options: [], text: e.target.value })}
            />
          </>
        )}
      </div>

      {feedback ? <Feedback question={question} feedback={feedback} /> : null}
    </section>
  )
}
