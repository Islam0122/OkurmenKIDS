/** One build, five front doors: the LMS (default), the standalone
 * «OkurmenKIDS Schedule» site (VITE_APP_MODE=schedule — e.g. a second
 * deployment at schedule.okurmenkids.com), the public «OkurmenKIDS
 * Leaderboard» site (VITE_APP_MODE=leaderboard), the public careers site
 * (VITE_APP_MODE=careers — vacancies and applications) and the academy
 * statistics site «OkurmenKIDS — Общая статистика» (VITE_APP_MODE=statistics,
 * staff login or a read-only dashboard key). All talk to the same backend
 * API; only the start page differs. */
export const IS_SCHEDULE_SITE = import.meta.env.VITE_APP_MODE === 'schedule'
export const IS_LEADERBOARD_SITE = import.meta.env.VITE_APP_MODE === 'leaderboard'
export const IS_CAREERS_SITE = import.meta.env.VITE_APP_MODE === 'careers'
/** «OkurmenKIDS — Общая статистика» на своём домене (VITE_APP_MODE=statistics). */
export const IS_STATISTICS_SITE = import.meta.env.VITE_APP_MODE === 'statistics'

export const HOME_PATH = IS_SCHEDULE_SITE
  ? '/schedule'
  : IS_LEADERBOARD_SITE
    ? '/leaderboard'
    : IS_CAREERS_SITE
      ? '/careers'
      : IS_STATISTICS_SITE
        ? '/monthly-performance'
        : '/app/dashboard'
