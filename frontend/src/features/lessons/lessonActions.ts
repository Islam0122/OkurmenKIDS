import type { LucideIcon } from 'lucide-react'
import { BookOpen, CheckCircle2, Eye, PlayCircle, XCircle } from 'lucide-react'

import type { Lesson } from '@/types/academy'

export type LessonActionKey =
  | 'start'
  | 'attendance'
  | 'homework'
  | 'complete'
  | 'cancel'
  | 'view_attendance'
  | 'view_homework'
  | 'view_details'

export interface LessonAction {
  key: LessonActionKey
  label: string
  icon: LucideIcon
}

export interface LessonActionPlan {
  /** Prominent, in-order workflow buttons for the current status. */
  primary: LessonAction[]
  /** Non-destructive extra actions for a "⋯" menu — currently unused (every
   * status's only "extra" action is destructive), kept for future actions
   * (e.g. "Изменить занятие") without reshaping the plan's shape again. */
  secondary: LessonAction[]
  /** The one destructive action for this status, if any — always kept out
   * of the primary row (rendered in a "⋯" menu / danger zone, never a plain button). */
  danger?: LessonAction
  /** Completed/cancelled — nothing further can change; render read-only. */
  isReadOnly: boolean
}

const ACTION_LABELS: Record<LessonActionKey, string> = {
  start: 'Начать занятие',
  attendance: 'Заполнить посещаемость',
  homework: 'Домашнее задание',
  complete: 'Завершить занятие',
  cancel: 'Отменить занятие',
  view_attendance: 'Посмотреть посещаемость',
  view_homework: 'Посмотреть домашнее задание',
  view_details: 'Просмотреть детали',
}

const ACTION_ICONS: Record<LessonActionKey, LucideIcon> = {
  start: PlayCircle,
  attendance: CheckCircle2,
  homework: BookOpen,
  complete: CheckCircle2,
  cancel: XCircle,
  view_attendance: Eye,
  view_homework: Eye,
  view_details: Eye,
}

function action(key: LessonActionKey): LessonAction {
  return { key, label: ACTION_LABELS[key], icon: ACTION_ICONS[key] }
}

/**
 * The one shared derivation of "what actions does this lesson allow right
 * now" — a pure mapping of already-computed backend fields (`status`,
 * `can_start`, `can_complete`, `can_cancel`, `homework_added`,
 * `homework_not_required`) onto UI structure. It never re-decides whether
 * an action is *allowed* — that's the backend's job (see
 * services.lesson_lifecycle: a Teacher only ever gets `can_*: true` for
 * their own lessons) — it only arranges the allowed ones, so every page
 * that shows lesson actions can never drift from another.
 */
export function getLessonActionPlan(lesson: Lesson): LessonActionPlan {
  switch (lesson.status) {
    case 'scheduled':
      return {
        primary: lesson.can_start ? [action('start')] : [],
        secondary: [],
        danger: lesson.can_cancel ? action('cancel') : undefined,
        isReadOnly: false,
      }

    case 'in_progress':
      return {
        primary: [action('attendance'), action('homework'), action('complete')],
        secondary: [],
        danger: lesson.can_cancel ? action('cancel') : undefined,
        isReadOnly: false,
      }

    case 'completed':
      // Homework already has its own "Посмотреть домашнее задание" door on
      // the Homework summary card (see HomeworkSummaryCard) — listing
      // `view_homework` here too would just duplicate that same button in
      // the trailing view-only actions section, so the plan only ever
      // offers attendance here.
      return { primary: [action('view_attendance')], secondary: [], danger: undefined, isReadOnly: true }

    case 'cancelled':
      return { primary: [], secondary: [], danger: undefined, isReadOnly: true }
  }
}

/**
 * A single best-next-action for compact contexts (a lesson card/row) that
 * can only show one button — never a second, independent rule set: for
 * `in_progress` it just orders the same three actions `getLessonActionPlan`
 * already lists by real progress (`attendance_completed`/`homework_added`/
 * `homework_not_required`), and otherwise takes the plan's first action,
 * falling back to "view details" when nothing is left to do (cancelled, or
 * scheduled without start permission).
 */
export function getPrimaryCardAction(lesson: Lesson): LessonAction {
  if (lesson.status === 'in_progress') {
    if (!lesson.attendance_completed) return action('attendance')
    if (!lesson.homework_added && !lesson.homework_not_required) return action('homework')
    return action('complete')
  }
  const plan = getLessonActionPlan(lesson)
  return plan.primary[0] ?? action('view_details')
}
