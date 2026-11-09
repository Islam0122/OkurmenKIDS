import { Navigate } from 'react-router-dom'

import { HOME_PATH, PORTAL_PATH } from '@/lib/appMode'
import { isStandalone } from '@/pwa/platform'

/**
 * «/». In a browser tab: this build's home (the LMS dashboard, or the
 * standalone site of VITE_APP_MODE), as before.
 *
 * In the installed app: always the public portal. The manifest's start_url is
 * `/portal`, but Chrome keeps the start_url an app was INSTALLED with until
 * its manifest-update check runs (throttled to about once a day on desktop;
 * on Android a WebAPK update can take days). Apps installed while start_url was
 * still «/» therefore launch here, and used to land in the LMS. Only «/» is
 * affected: refreshes and deep links (/app/…, /tasks/…) keep their URL.
 */
export function RootRedirect() {
  return <Navigate to={isStandalone() ? PORTAL_PATH : HOME_PATH} replace />
}
