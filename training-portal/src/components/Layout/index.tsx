import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { Footer } from '../Footer'
import { Header } from '../Header'

export function Layout() {
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
