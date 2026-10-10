import type { UserRole } from '@/types/auth'

/** UI-only role helpers. Every permission is enforced by the backend
 * (apps.users.permissions) — these only decide what the UI offers. */

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: 'Администратор',
  teacher: 'Тренер',
  team_lead: 'Team Lead',
  assistant: 'Ассистент',
  accountant: 'Бухгалтер',
  director: 'Директор',
}

/** The Assistant works only in the Assistant Workspace (/assistant), never in /app. */
export function isAssistant(role: UserRole | undefined): boolean {
  return role === 'assistant'
}

export function isTeamLead(role: UserRole | undefined): boolean {
  return role === 'team_lead'
}

/** Admin or Team Lead: reads the whole academy (every trainer/group/student).
 * Mirrors `apps.users.permissions.can_view_academy` — never a write gate. */
export function seesWholeAcademy(role: UserRole | undefined): boolean {
  return role === 'admin' || role === 'team_lead'
}

/** Бухгалтер и Директор работают только в разделе бухгалтерии (/accounting). */
export function isAccountingRole(role: UserRole | undefined): boolean {
  return role === 'accountant' || role === 'director'
}

/** Where a role lands after sign-in. The Accountant lives only in /accounting
 * (backend: apps.accounting.access — every LMS URL answers it 403). */
export function homeFor(role: UserRole | undefined, target: string): string {
  if (role === 'accountant' && !target.startsWith('/accounting')) return '/accounting'
  return target
}
