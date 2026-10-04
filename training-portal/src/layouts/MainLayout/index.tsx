/** Regular pages: header, content, footer. */
import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { Footer } from '@/components/Footer'
import { Header } from '@/components/Header'

export function MainLayout() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo({ top: 0 }) }, [pathname])
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <main key={pathname} className="page-enter" style={{ flex: 1 }}>
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
