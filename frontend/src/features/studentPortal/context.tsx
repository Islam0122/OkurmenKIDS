import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import { studentPortalApi } from '@/api/studentPortal'
import type { PortalMe, PortalStudent } from '@/types/studentPortal'

/** The signed-in family account and the child currently shown. Which
 * children exist is the server's answer (`/portal/me/`) — the switcher can
 * only pick among them, and every request is re-checked server-side. */

export const PORTAL_KEY = ['student-portal'] as const

/** Homework results are saved by the trainer in the existing grading form
 * (offline checking in class). The family's pages therefore never trust a
 * cached copy: they refetch on every visit, when the tab regains focus, and
 * every minute while open — a saved status, grade or comment shows up
 * without a reload. */
export const LIVE_QUERY = {
  staleTime: 0,
  refetchOnMount: 'always',
  refetchOnWindowFocus: 'always',
  refetchInterval: 60_000,
} as const
const SELECTED_KEY = 'okk-student-portal-child'

interface PortalValue {
  me: PortalMe
  student: PortalStudent
  selectStudent: (id: number) => void
}

const PortalContext = createContext<PortalValue | null>(null)

export function usePortalMe() {
  return useQuery({ queryKey: [...PORTAL_KEY, 'me'], queryFn: studentPortalApi.me, staleTime: 60_000 })
}

function readSelected(): number | null {
  try {
    const value = Number(window.localStorage.getItem(SELECTED_KEY))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

export function PortalProvider({ me, children }: { me: PortalMe; children: ReactNode }) {
  const [selected, setSelected] = useState<number | null>(readSelected)
  const student = me.students.find((s) => s.id === selected) ?? me.students[0]
  const selectStudent = useCallback((id: number) => {
    setSelected(id)
    try {
      window.localStorage.setItem(SELECTED_KEY, String(id))
    } catch {
      /* not remembered — fine */
    }
  }, [])
  const value = useMemo(() => ({ me, student, selectStudent }), [me, student, selectStudent])
  return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>
}

export function usePortal(): PortalValue {
  const value = useContext(PortalContext)
  if (!value) throw new Error('usePortal must be used inside PortalProvider')
  return value
}
