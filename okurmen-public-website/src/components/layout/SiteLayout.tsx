import { Suspense, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'

import { env } from '@/app/config/env'
import { PageSkeleton } from '@/components/shared/States'
import { EnrollmentProvider } from '@/features/enrollment/EnrollmentProvider'
import { captureUtm } from '@/features/enrollment/utm'
import { useI18n } from '@/i18n'

import { Footer } from './Footer'
import { Header } from './Header'
import { MobileCta } from './MobileCta'

export function SiteLayout() {
  const { t } = useI18n()
  const location = useLocation()

  useEffect(() => captureUtm(location.search), [location.search])
  useEffect(() => {
    if (!location.hash) window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
  }, [location.pathname, location.hash])

  return (
    <EnrollmentProvider>
      {env.useMocks ? (
        <div role="note" className="flex items-center justify-center gap-2 bg-gold-100 px-4 py-2 text-center text-xs font-bold text-gold-700">
          <FlaskConical className="size-4 shrink-0" aria-hidden /> {t('state.mocks')}
        </div>
      ) : null}
      <Header />
      <main id="main" tabIndex={-1} className="min-h-[60vh] outline-none">
        <Suspense fallback={<PageSkeleton />}>
          <Outlet />
        </Suspense>
      </main>
      <Footer />
      <MobileCta />
    </EnrollmentProvider>
  )
}
