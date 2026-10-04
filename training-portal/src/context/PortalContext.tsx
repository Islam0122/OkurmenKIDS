import { createContext, useContext, type ReactNode } from 'react'

import type { PortalSettings } from '@/types'

import { getPortal } from '@/api/portal'
import { useAsync, type AsyncState } from '@/hooks/useAsync'

/** Portal settings from the backend (hero texts, the real exam link). */
const PortalContext = createContext<AsyncState<PortalSettings> | null>(null)

export function PortalProvider({ children }: { children: ReactNode }) {
  const state = useAsync(getPortal)
  return <PortalContext.Provider value={state}>{children}</PortalContext.Provider>
}

export function usePortal(): AsyncState<PortalSettings> {
  const value = useContext(PortalContext)
  if (!value) throw new Error('usePortal must be used inside <PortalProvider>')
  return value
}
