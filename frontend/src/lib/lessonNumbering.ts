import type { LessonNumbering } from '@/types/lessonNumbering'

export type { LessonNumbering }

export type NumberingLang = 'ru' | 'ky' | 'en'

const FORMAT: Record<NumberingLang, (month: number, lesson: number) => string> = {
  ru: (month, lesson) => `${month} месяц · ${lesson} урок`,
  ky: (month, lesson) => `${month}-ай · ${lesson}-сабак`,
  en: (month, lesson) => `Month ${month} · Lesson ${lesson}`,
}

/**
 * The one way a lesson's number is shown: «3 месяц · 5 урок» (ru),
 * «3-ай · 5-сабак» (ky), «Month 3 · Lesson 5» (en). The month and lesson come
 * from the server's single numbering service. Without them the result is
 * empty: the stored lesson_number is a course-wide plan row (IT lesson 29 can
 * be row 85) and is never shown as the lesson's number.
 */
export function lessonLabel(numbering: LessonNumbering | null | undefined, _legacyNumber?: number | null, lang: NumberingLang = 'ru'): string {
  if (!numbering) return ''
  return FORMAT[lang](numbering.month, numbering.lesson)
}

/** Same in tight table cells. */
export function lessonLabelShort(numbering: LessonNumbering | null | undefined, _legacyNumber?: number | null): string {
  return lessonLabel(numbering)
}
