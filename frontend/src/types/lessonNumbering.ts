/** «3 месяц · 5 урок» — `apps.academic_progress.numbering`: the educational
 * month and the lesson in it, from the lesson's place in its OWN subject's
 * plan (IT, English, Soft Skills… are separate sequences) and the
 * curriculum's study months / 12 or 20 lessons per month. Not a calendar
 * month, not the course-wide plan row. Absent when the curriculum does not
 * say — then no number is shown. */
export interface LessonNumbering {
  /** Position in the subject's own sequence. */
  number: number
  month: number
  lesson: number
  per_month: number
  subject_id?: number | null
  /** Russian label, «3 месяц · 5 урок». */
  label: string
  labels?: { ru: string; ky: string; en: string }
}
