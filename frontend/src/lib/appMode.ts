/** One build, three front doors: the LMS (default), the standalone
 * «OkurmenKIDS Schedule» site (VITE_APP_MODE=schedule — e.g. a second
 * deployment at schedule.okurmenkids.com) and the public «OkurmenKIDS
 * Leaderboard» site (VITE_APP_MODE=leaderboard). All talk to the same
 * backend API; only the start page differs. */
export const IS_SCHEDULE_SITE = import.meta.env.VITE_APP_MODE === 'schedule'
export const IS_LEADERBOARD_SITE = import.meta.env.VITE_APP_MODE === 'leaderboard'

export const HOME_PATH = IS_SCHEDULE_SITE ? '/schedule' : IS_LEADERBOARD_SITE ? '/leaderboard' : '/app/dashboard'
