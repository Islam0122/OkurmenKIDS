import { Menu } from '@/components/ui/Menu'
import type { MenuItem } from '@/components/ui/Menu'
import { Button } from '@/components/ui/Button'
import type { Lesson } from '@/types/academy'

import type { LessonActionKey } from './lessonActions'
import { getLessonActionPlan } from './lessonActions'

const PROMINENT_ACTIONS: LessonActionKey[] = ['start', 'complete']

export interface LessonActionBarProps {
  lesson: Lesson
  onAction: (key: LessonActionKey) => void
  /** The action key currently in flight (if any) — only that button shows a spinner. */
  pendingKey?: LessonActionKey | null
}

/**
 * The one shared lesson action bar — a pure rendering of
 * `getLessonActionPlan(lesson)`: which buttons show, in what order, and
 * which single destructive action (if any) is tucked into the "⋯" menu
 * instead of sitting next to the workflow buttons. A completed/cancelled
 * lesson renders its actions (if any) as plain, muted "view" buttons —
 * never Start/Complete/Cancel, and never through a second copy of this
 * logic (see `lessonActions.ts`'s own docstring).
 */
export function LessonActionBar({ lesson, onAction, pendingKey }: LessonActionBarProps) {
  const plan = getLessonActionPlan(lesson)

  const menuItems: MenuItem[] = []
  if (plan.danger) {
    const danger = plan.danger
    menuItems.push({
      key: danger.key,
      label: danger.label,
      tone: 'danger',
      icon: <danger.icon className="size-4" aria-hidden />,
      onClick: () => onAction(danger.key),
    })
  }

  if (plan.primary.length === 0 && menuItems.length === 0) {
    return null
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {plan.primary.map((act) => {
        const Icon = act.icon
        const isProminent = !plan.isReadOnly && PROMINENT_ACTIONS.includes(act.key)
        const isCompleteDisabled = act.key === 'complete' && !lesson.can_complete
        return (
          <Button
            key={act.key}
            variant={plan.isReadOnly ? 'secondary' : isProminent ? 'primary' : 'secondary'}
            leftIcon={<Icon className="size-4" aria-hidden />}
            isLoading={pendingKey === act.key}
            disabled={isCompleteDisabled || (pendingKey != null && pendingKey !== act.key)}
            onClick={() => onAction(act.key)}
          >
            {act.label}
          </Button>
        )
      })}
      {menuItems.length > 0 ? <Menu items={menuItems} /> : null}
    </div>
  )
}
