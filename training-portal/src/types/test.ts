/** A question type — the same four the Okurmen Kids testing system has
 * (single_choice / multiple_choice / text / code). */
export type QuestionType = 'single' | 'multiple' | 'text' | 'code'

export type Difficulty = 'easy' | 'medium' | 'hard'

export interface QuestionOption {
  id: string
  text: string
}

export interface Question {
  id: string
  type: QuestionType
  question: string
  imageUrl?: string
  options?: QuestionOption[]
  /**
   * single: option id · multiple: option ids · text: accepted answers
   * (any of them counts, case- and space-insensitive) · code: a reference
   * solution shown after the answer (code is not auto-graded).
   */
  correctAnswer?: string | string[]
  explanation?: string
  /** code questions */
  language?: string
  starterCode?: string
}

export interface Test {
  id: string
  title: string
  description?: string
  subject: string
  level: Difficulty
  /** e.g. «Бардык темалар» */
  topics?: string
  /** minutes; 0 = no time limit */
  duration: number
  /** attempts per student name on this device; null = unlimited */
  maxAttempts: number | null
  /** training feedback (correct answer + explanation) right after «Текшерүү» */
  showExplanation: boolean
  questions: Question[]
  published: boolean
}

/** What the student gave for one question. */
export interface Answer {
  options?: string[]
  text?: string
}

export type QuestionOutcome = 'correct' | 'incorrect' | 'skipped' | 'ungraded'
