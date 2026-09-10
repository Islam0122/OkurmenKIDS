import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'

import { Header } from '@/components/layout/Header'
import { LoadingState } from '@/components/ui/LoadingState'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { Sidebar } from '@/components/layout/Sidebar'

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-surface-muted">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 px-4 pt-6 pb-24 lg:px-8 lg:pb-8">
          <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <MobileNavigation />
    </div>
  )
}
