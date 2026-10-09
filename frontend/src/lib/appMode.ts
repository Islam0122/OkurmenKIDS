/** One build, two front doors: the LMS (default) and the standalone
 * «OkurmenKIDS Schedule» site (VITE_APP_MODE=schedule — e.g. a second
 * deployment at schedule.okurmenkids.com). Both talk to the same backend
 * API and the same login; only the start page differs. */
export const IS_SCHEDULE_SITE = import.meta.env.VITE_APP_MODE === 'schedule'

export const HOME_PATH = IS_SCHEDULE_SITE ? '/schedule' : '/app/dashboard'
