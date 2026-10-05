import { useState } from 'react'
import { Search } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { useAssistantStudents } from '@/hooks/useAssistant'
import type { StudentListParams } from '@/api/assistant'
import type { StudentRow } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { ModalActions, StudentStatusBadge } from '../ui'

/**
 * Picks one or several students by search — the first step of a quick
 * action started without a student (header «+ Создать» → «Перевести
 * студента»…). `status` limits the list to students the action applies to.
 */
export function StudentPickerModal({
  isOpen,
  title,
  status = 'all',
  multiple = false,
  confirmLabel = 'Продолжить',
  excludeGroup,
  onClose,
  onPick,
}: {
  isOpen: boolean
  title: string
  status?: StudentListParams['status']
  multiple?: boolean
  confirmLabel?: string
  excludeGroup?: number
  onClose: () => void
  onPick: (students: StudentRow[]) => void
}) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Map<number, StudentRow>>(new Map())
  const { data, isPending } = useAssistantStudents({ search: search || undefined, status, page_size: 30 }, isOpen)
  const rows = (data?.results ?? []).filter((student) => excludeGroup === undefined || student.group?.id !== excludeGroup)

  const toggle = (student: StudentRow) => {
    if (!multiple) {
      onPick([student])
      return
    }
    setSelected((current) => {
      const next = new Map(current)
      if (next.has(student.id)) next.delete(student.id)
      else next.set(student.id, student)
      return next
    })
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} icon={<Search className="size-5 text-brand-600" aria-hidden />}>
      <SearchInput value={search} onChange={setSearch} placeholder="Имя, фамилия или телефон…" aria-label="Поиск студента" />
      <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-border">
        {isPending ? <LoadingState label="Ищем студентов…" /> : null}
        {!isPending && rows.length === 0 ? <p className="p-4 text-center text-sm text-ink-secondary">Студенты не найдены.</p> : null}
        <ul className="divide-y divide-border">
          {rows.map((student) => {
            const checked = selected.has(student.id)
            return (
              <li key={student.id}>
                <button
                  type="button"
                  onClick={() => toggle(student)}
                  aria-pressed={multiple ? checked : undefined}
                  className={cn('flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-hover', checked && 'bg-brand-50')}
                >
                  {multiple ? (
                    <input type="checkbox" readOnly checked={checked} tabIndex={-1} className="size-4 shrink-0 accent-brand-500" aria-hidden />
                  ) : null}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{student.full_name}</span>
                    <span className="block truncate text-xs text-ink-secondary">{student.group?.name ?? 'Без группы'}</span>
                  </span>
                  <StudentStatusBadge status={student.status} label={student.status_display} />
                </button>
              </li>
            )
          })}
        </ul>
      </div>
      {multiple ? (
        <ModalActions>
          <Button variant="secondary" onClick={onClose}>Отмена</Button>
          <Button disabled={selected.size === 0} onClick={() => onPick([...selected.values()])}>
            {confirmLabel}{selected.size ? ` (${selected.size})` : ''}
          </Button>
        </ModalActions>
      ) : null}
    </Modal>
  )
}
