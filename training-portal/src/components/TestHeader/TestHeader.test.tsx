import { render, screen } from '@testing-library/react'

import { EXAM_MODE, TRAINING_MODE } from '@/components/TestScreen/modes'
import { Timer } from '@/components/Timer'
import { QuestionNavigation } from '@/components/QuestionNavigation'

import { TestHeader } from '.'

describe('one header for every mode', () => {
  it('training: logo, back, «Тренировка» badge, title, timer', () => {
    const { container } = render(<TestHeader config={TRAINING_MODE} title="Python" student="Islam" secondsLeft={1200} onLeave={() => {}} />)
    expect(screen.getByRole('button', { name: 'Артка' })).toBeInTheDocument()
    expect(screen.getByText('Тренировка')).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('20:00')
    expect(container.querySelector('.test-header__logo')).not.toBeNull()
  })

  it('exam: the same header, no way back, «Экзамен» badge', () => {
    const { container } = render(<TestHeader config={EXAM_MODE} title="IT" student="Aibek" secondsLeft={2700} onLeave={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Артка' })).not.toBeInTheDocument()
    expect(screen.getByText('Экзамен')).toBeInTheDocument()
    expect(container.querySelector('.test-header')).not.toBeNull()  // same component, same classes
  })
})

describe('timer states', () => {
  it('neutral → warning → danger, with the icon changing too (not colour alone)', () => {
    const { container, rerender } = render(<Timer secondsLeft={2700} warnAt={600} dangerAt={300} />)
    expect(container.querySelector('.timer')?.className).toBe('timer')
    expect(container.querySelector('.bi-clock')).not.toBeNull()
    rerender(<Timer secondsLeft={599} warnAt={600} dangerAt={300} />)
    expect(container.querySelector('.timer--warning .bi-hourglass-split')).not.toBeNull()
    rerender(<Timer secondsLeft={299} warnAt={600} dangerAt={300} />)
    expect(container.querySelector('.timer--low .bi-alarm')).not.toBeNull()
  })
})

describe('question navigation', () => {
  it('names every state for screen readers (not colour alone)', () => {
    render(<QuestionNavigation states={['answered', 'current', 'unanswered']} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'Суроо 1: Жооп берилди' })).toHaveClass('qnav__item--answered')
    expect(screen.getByRole('button', { name: 'Суроо 2: Учурдагы' })).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('button', { name: 'Суроо 3: Жооп жок' })).toBeInTheDocument()
  })
})
