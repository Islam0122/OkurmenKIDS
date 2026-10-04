import type { Question, Test } from '@/types'

import { correctAnswerText, gradeQuestion, normalizeText, scoreTest } from './grading'

const single: Question = { id: 's', type: 'single', question: '?', options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }], correctAnswer: 'b' }
const multi: Question = { id: 'm', type: 'multiple', question: '?', options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }, { id: 'c', text: 'C' }], correctAnswer: ['a', 'c'] }
const text: Question = { id: 't', type: 'text', question: '?', correctAnswer: ['Язык программирования', 'language'] }
const code: Question = { id: 'c', type: 'code', question: '?', correctAnswer: 'return a + b' }

describe('gradeQuestion', () => {
  it('single choice needs exactly the right option', () => {
    expect(gradeQuestion(single, { options: ['b'] })).toBe('correct')
    expect(gradeQuestion(single, { options: ['a'] })).toBe('incorrect')
    expect(gradeQuestion(single, { options: ['a', 'b'] })).toBe('incorrect')
    expect(gradeQuestion(single, undefined)).toBe('skipped')
  })

  it('multiple choice needs the exact set', () => {
    expect(gradeQuestion(multi, { options: ['c', 'a'] })).toBe('correct')
    expect(gradeQuestion(multi, { options: ['a'] })).toBe('incorrect')
    expect(gradeQuestion(multi, { options: ['a', 'b', 'c'] })).toBe('incorrect')
  })

  it('text ignores case and extra spaces, accepts any listed answer', () => {
    expect(gradeQuestion(text, { text: '  язык   ПРОГРАММИРОВАНИЯ ' })).toBe('correct')
    expect(gradeQuestion(text, { text: 'Language' })).toBe('correct')
    expect(gradeQuestion(text, { text: 'nope' })).toBe('incorrect')
    expect(gradeQuestion(text, { text: '   ' })).toBe('skipped')
  })

  it('code is never auto-graded', () => {
    expect(gradeQuestion(code, { text: 'return a + b' })).toBe('ungraded')
    expect(gradeQuestion(code, { text: '' })).toBe('skipped')
  })
})

describe('scoreTest', () => {
  const test: Test = {
    id: 'x', title: 'X', subject: 'Python', level: 'easy', duration: 10, maxAttempts: null,
    showExplanation: true, published: true, questions: [single, multi, text, code],
  }

  it('leaves code out of the percentage', () => {
    const score = scoreTest(test, { s: { options: ['b'] }, m: { options: ['a'] }, c: { text: 'x' } })
    expect(score).toMatchObject({ total: 4, correct: 1, incorrect: 1, skipped: 1, ungraded: 1, graded: 3, percent: 33 })
  })
})

it('normalizeText and correctAnswerText', () => {
  expect(normalizeText('  A   b ')).toBe('a b')
  expect(correctAnswerText(multi)).toBe('A, C')
  expect(correctAnswerText(text)).toBe('Язык программирования')
})
