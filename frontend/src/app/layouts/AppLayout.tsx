import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'

import { Header } from '@/components/layout/Header'
import { LoadingState } from '@/components/ui/LoadingState'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { Sidebar } from '@/components/layout/Sidebar'

/**
 * The one page shell every /app route renders in:
 *
 *   Sidebar (desktop, fixed 240px) │ Header (sticky, 64px)
 *                                  │ main → page container (max 1280px)
 *   MobileNavigation (phone, fixed 64px + safe-area)
 *
 * Pages only render their content — never their own outer padding or
 * max-width — so every page gets the same gutters at every breakpoint.
 */
export function AppLayout() {
  return (
    <div className="flex min-h-dvh bg-surface-muted">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 pb-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1.5rem)] lg:pb-8">
          <div className="mx-auto w-full max-w-page px-4 pt-6 sm:px-6 lg:px-8">
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
      <MobileNavigation />
    </div>
  )
}
