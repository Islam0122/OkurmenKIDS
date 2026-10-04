import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'

import './ExamLayout.css'

/**
 * The training / exam screen: nothing but the test. No site header, menu
 * or footer — the page fills the viewport (and, once started, the browser
 * goes fullscreen through the Fullscreen API, see useExamGuard). Leaving
 * this layout unmounts the guard, which removes every restriction.
 */
export function ExamLayout() {
  useEffect(() => {
    document.body.classList.add('is-exam-layout')
    window.scrollTo({ top: 0 })
    return () => document.body.classList.remove('is-exam-layout')
  }, [])
  return (
    <main className="exam-layout page-enter">
      <Outlet />
    </main>
  )
}
