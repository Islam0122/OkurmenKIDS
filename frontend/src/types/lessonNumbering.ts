/** «Месяц 2 · Урок 1» — `apps.academic_progress.numbering`: the educational
 * month and the lesson in it, derived from the lesson's global number
 * (`number`) with 12 or 20 lessons per month. Not a calendar month. */
export interface LessonNumbering {
  number: number
  month: number
  lesson: number
  per_month: number
  /** Russian label, e.g. «Месяц 2 · Урок 1». */
  label: string
}
