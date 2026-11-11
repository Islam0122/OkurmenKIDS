import { isRouteErrorResponse, useRouteError } from 'react-router-dom'

import { ButtonLink } from '@/components/shared/Button'
import { useI18n } from '@/i18n'

/** Last-resort screen (e.g. a page chunk failed to load after a new deploy). */
export function RouteError() {
  const error = useRouteError()
  const { t } = useI18n()
  const chunkFailed = error instanceof Error && /dynamically imported module|Failed to fetch/i.test(error.message)
  if (chunkFailed && !sessionStorage.getItem('okurmen_reloaded')) {
    sessionStorage.setItem('okurmen_reloaded', '1')
    window.location.reload()
    return null
  }
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="font-display text-6xl font-black text-brand-100">{isRouteErrorResponse(error) ? error.status : 'Oops'}</p>
      <h1 className="text-2xl font-extrabold">{t('state.error.title')}</h1>
      <p className="max-w-md text-muted">{t('state.error.server')}</p>
      <ButtonLink to="/">{t('cta.home')}</ButtonLink>
    </div>
  )
}
