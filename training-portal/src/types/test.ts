/** GET /api/v1/training/tests/ and tests/<id>/ */
export type TestLevel = 'easy' | 'medium' | 'hard'

export interface TrainingTest {
  id: string
  title: string
  description: string
  subject: string
  level: TestLevel
  level_display: string
  image_url: string | null
  /** minutes; null — no time limit */
  duration: number | null
  questions_count: number
  /** null — unlimited */
  max_attempts: number | null
  passing_score: number
  /** «Текшерүү» with the correct answer + explanation after each answer */
  show_explanation: boolean
  show_result: boolean
  published: boolean
}
