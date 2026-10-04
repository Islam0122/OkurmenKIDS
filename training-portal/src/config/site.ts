/**
 * Site settings an administrator changes — no component hard-codes them.
 * Values can be overridden at build time with Vite env variables
 * (VITE_EXAM_URL, VITE_EXAM_OPEN_IN_NEW_TAB), and later come from the
 * Django API without touching the UI.
 */
const env = import.meta.env

export interface SiteConfig {
  brand: string
  /** The real exam lives in the LMS — this portal only links to it. */
  examUrl: string
  openInNewTab: boolean
  /** the test «Тренировка баштоо» opens */
  defaultTestId: string
  /** how many leaders the home page shows */
  leaderboardPreviewSize: number
  contacts: { phone?: string; instagram?: string; website?: string }
}

export const siteConfig: SiteConfig = {
  brand: 'Okurmen Kids',
  examUrl: env.VITE_EXAM_URL || 'https://lms.okurmen.kg/student/exams/',
  openInNewTab: env.VITE_EXAM_OPEN_IN_NEW_TAB === 'true',
  defaultTestId: 'python-basics',
  leaderboardPreviewSize: 5,
  // Filled in by the administrator; empty values are simply not shown.
  contacts: {},
}
