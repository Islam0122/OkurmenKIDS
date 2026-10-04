/** Exam Mode settings of a trainer (the test's security settings). */
export interface SecuritySettings {
  require_fullscreen: boolean
  track_tab_switches: boolean
  /** null — tab switches are only logged */
  max_tab_switches: number | null
  block_copy_paste: boolean
}

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
  allow_retry: boolean
  /** program (Course) name, may be empty */
  course: string
  /** this trainer's exam link, else the portal's; empty — no exam button */
  exam_url: string
  security: SecuritySettings
  published: boolean
}
