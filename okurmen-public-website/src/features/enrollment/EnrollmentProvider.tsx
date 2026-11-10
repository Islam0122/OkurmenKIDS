import { createContext, lazy, Suspense, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/i18n'

// The form (react-hook-form + zod) loads only when the dialog is first opened.
const EnrollmentForm = lazy(() => import('./EnrollmentForm').then((m) => ({ default: m.EnrollmentForm })))

interface EnrollContext {
  /** Opens the enrollment form, optionally with a course pre-selected. */
  openEnroll: (course?: string) => void
}

const Context = createContext<EnrollContext>({ openEnroll: () => undefined })

export function EnrollmentProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [state, setState] = useState<{ open: boolean; course?: string }>({ open: false })
  const openEnroll = useCallback((course?: string) => setState({ open: true, course }), [])
  const close = useCallback(() => setState((s) => ({ ...s, open: false })), [])
  const value = useMemo(() => ({ openEnroll }), [openEnroll])
  return (
    <Context.Provider value={value}>
      {children}
      <Dialog open={state.open} onClose={close} title={t('form.enrollTitle')} description={t('form.enrollText')}>
        <Suspense fallback={<div className="grid h-80 place-items-center"><Loader2 className="size-8 animate-spin text-brand-400" aria-hidden /></div>}>
          <EnrollmentForm key={state.course ?? 'any'} defaultCourse={state.course} compact onDone={close} />
        </Suspense>
      </Dialog>
    </Context.Provider>
  )
}

export const useEnroll = () => useContext(Context)
