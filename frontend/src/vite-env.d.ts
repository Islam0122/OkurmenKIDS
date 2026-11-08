/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** «schedule» / «leaderboard» / «careers» / «statistics» / «portal» — this build is that standalone public site: «/» opens it. */
  readonly VITE_APP_MODE?: string
  /** OKURMEN DIGITAL launcher (features/portal/config.ts): optional destination overrides —
   * an app route of this build (`/schedule`) or an absolute URL of another deployment. */
  readonly VITE_PORTAL_LMS_URL?: string
  readonly VITE_PORTAL_TRAINING_URL?: string
  readonly VITE_PORTAL_SCHEDULE_URL?: string
  readonly VITE_PORTAL_LEADERBOARD_URL?: string
  readonly VITE_PORTAL_NEWS_URL?: string
  readonly VITE_PORTAL_PERFORMANCE_URL?: string
  readonly VITE_PORTAL_PROGRAMS_URL?: string
  /** «More from Okurmen»: Student Projects, Feedback, the official website, Careers. */
  readonly VITE_PORTAL_PROJECTS_URL?: string
  readonly VITE_PORTAL_FEEDBACK_URL?: string
  readonly VITE_PORTAL_WEBSITE_URL?: string
  readonly VITE_PORTAL_CAREERS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
