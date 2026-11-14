import type { TeamCategory, TeamMember } from '@/types/api'

/**
 * The public category of a profile — the single rule the homepage, /team,
 * /about and profile pages share. Comes from the CMS (`category`); an API
 * that predates the field falls back to the department the same way the
 * backend migration did («Руководство»/«Администрация» → management).
 */
export function teamCategory(member: Pick<TeamMember, 'category' | 'group'>): TeamCategory {
  if (member.category) return member.category
  return member.group === 'management' || member.group === 'administration' ? 'management' : 'teacher'
}

export const isManagement = (m: TeamMember) => teamCategory(m) === 'management'
export const isTeacher = (m: TeamMember) => teamCategory(m) === 'teacher'
