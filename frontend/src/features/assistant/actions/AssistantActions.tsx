import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import type { BulkAction, Ref } from '@/types/assistant'

import { ScheduleModal } from './ScheduleModal'
import { ActivateModal, BulkActionModal, DeactivateModal, TransferModal } from './StudentActionModals'
import type { StudentLite } from './StudentActionModals'
import { StudentPickerModal } from './StudentPickerModal'

/**
 * The Assistant's quick actions, one place for every entry point: a
 * student's page, a row in the students list, the dashboard, the header's
 * «+ Создать». Started with a student, an action opens its modal at once
 * (Студент → Деактивировать → Причина → Подтвердить); started without one,
 * a student search comes first.
 */
export type AssistantAction =
  | { type: 'deactivate' | 'activate' | 'transfer'; student?: StudentLite }
  | { type: 'bulk'; action: BulkAction; students?: StudentLite[]; group?: Ref; onDone?: () => void }
  | { type: 'schedule'; group?: Ref; programId?: number }

interface ActionsContextValue {
  open: (action: AssistantAction) => void
}

const ActionsContext = createContext<ActionsContextValue | null>(null)

const PICKER: Record<'deactivate' | 'activate' | 'transfer', { title: string; status: 'active' | 'inactive' | 'all' }> = {
  deactivate: { title: 'Кого деактивировать?', status: 'active' },
  activate: { title: 'Кого активировать?', status: 'all' },
  transfer: { title: 'Кого перевести?', status: 'all' },
}

export function AssistantActionsProvider({ children }: { children: ReactNode }) {
  const [action, setAction] = useState<AssistantAction | null>(null)
  const close = useCallback(() => setAction(null), [])
  const value = useMemo(() => ({ open: setAction }), [])

  let modal: ReactNode = null
  if (action?.type === 'deactivate' || action?.type === 'activate' || action?.type === 'transfer') {
    const { student, type } = action
    if (!student) {
      modal = (
        <StudentPickerModal
          isOpen
          title={PICKER[type].title}
          status={PICKER[type].status}
          onClose={close}
          onPick={([picked]) => setAction({ type, student: picked })}
        />
      )
    } else if (type === 'deactivate') {
      modal = <DeactivateModal student={student} onClose={close} />
    } else if (type === 'activate') {
      modal = <ActivateModal student={student} onClose={close} />
    } else {
      modal = <TransferModal student={student} onClose={close} />
    }
  } else if (action?.type === 'bulk') {
    modal = action.students?.length ? (
      <BulkActionModal action={action.action} students={action.students} presetGroup={action.group} onClose={close} onDone={action.onDone} />
    ) : (
      <StudentPickerModal
        isOpen
        multiple
        title={action.group ? `Добавить студентов в ${action.group.name}` : 'Выберите студентов'}
        excludeGroup={action.group?.id}
        status={action.action === 'activate' ? 'inactive' : 'all'}
        onClose={close}
        onPick={(students) => setAction({ ...action, students })}
      />
    )
  } else if (action?.type === 'schedule') {
    modal = <ScheduleModal group={action.group} programId={action.programId} onClose={close} />
  }

  return (
    <ActionsContext.Provider value={value}>
      {children}
      {modal}
    </ActionsContext.Provider>
  )
}

export function useAssistantActions(): ActionsContextValue {
  const context = useContext(ActionsContext)
  if (!context) throw new Error('useAssistantActions must be used inside AssistantActionsProvider')
  return context
}
