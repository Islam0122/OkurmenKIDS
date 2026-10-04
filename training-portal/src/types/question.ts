/** Question types of the Okurmen Kids testing system (backend values). */
export type QuestionType = 'single_choice' | 'multiple_choice' | 'text' | 'code'

export interface QuestionOption {
  id: string
  text: string
  image_url: string | null
}

export interface AnswerValue {
  options: string[]
  text: string
}

/** POST …/answers/<question_id>/check/ */
export interface AnswerFeedback {
  /** pending — code (and text without accepted answers) is reviewed by a teacher */
  status: 'correct' | 'incorrect' | 'pending'
  correct_option_ids: string[]
  correct_answers: string[]
  code_examples: { input: string; expected_output: string }[]
  explanation: string
}

export interface Question {
  id: string
  type: QuestionType
  text: string
  image_url: string | null
  hint: string
  language: string | null
  starter_code: string
  points: number
  is_required: boolean
  options: QuestionOption[]
  answer: AnswerValue | null
  checked: boolean
  feedback: AnswerFeedback | null
}
