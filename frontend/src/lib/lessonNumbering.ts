import type { LessonNumbering } from '@/types/lessonNumbering'

export type { LessonNumbering }

export type NumberingLang = 'ru' | 'ky'

/**
 * The one way a lesson's number is shown: «Месяц 2 · Урок 1» (ru) /
 * «2-ай · 1-сабак» (ky). The educational month comes from the server
 * (lessons per month of the group / program — 12 or 20), so every page shows
 * the same thing. A payload without numbering (an old snapshot) falls back to
 * the plain global number.
 */
export function lessonLabel(
  numbering: LessonNumbering | null | undefined,
  fallbackNumber?: number | null,
  lang: NumberingLang = 'ru',
): string {
  if (numbering) {
    return lang === 'ky' ? `${numbering.month}-ай · ${numbering.lesson}-сабак` : `Месяц ${numbering.month} · Урок ${numbering.lesson}`
  }
  if (!fallbackNumber) return ''
  return lang === 'ky' ? `${fallbackNumber}-сабак` : `Занятие ${fallbackNumber}`
}

/** Short form for tight table cells: «М2 · У1» / «2-ай · 1». */
export function lessonLabelShort(numbering: LessonNumbering | null | undefined, fallbackNumber?: number | null): string {
  if (numbering) return `М${numbering.month} · У${numbering.lesson}`
  return fallbackNumber ? `№${fallbackNumber}` : ''
}
