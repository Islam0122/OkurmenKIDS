/**
 * TanStack Query hooks — one per public resource. Keys include the language,
 * so switching language refetches translated content.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { useI18n } from '@/i18n'
import { ApiError } from '@/services/api/client'
import { careersApi, newsApi, projectsApi, siteApi, type ListParams } from '@/services/endpoints'

const notFoundNoRetry = (count: number, error: unknown) =>
  !(error instanceof ApiError && (error.kind === 'not_found' || error.kind === 'config' || error.kind === 'validation')) && count < 2

export function useSettings() {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['settings', lang], queryFn: siteApi.settings, staleTime: 5 * 60_000, retry: notFoundNoRetry })
}

export function useHome() {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['home', lang], queryFn: siteApi.home, retry: notFoundNoRetry })
}

export function useCourses() {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['courses', lang], queryFn: siteApi.courses, retry: notFoundNoRetry })
}

export function useCourse(slug: string) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['course', slug, lang], queryFn: () => siteApi.course(slug), retry: notFoundNoRetry })
}

export function useEvents(params: ListParams) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['events', params, lang], queryFn: () => siteApi.events(params), placeholderData: keepPreviousData, retry: notFoundNoRetry })
}

export function useEvent(slug: string) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['event', slug, lang], queryFn: () => siteApi.event(slug), retry: notFoundNoRetry })
}

export function useAchievements(params: ListParams) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['achievements', params, lang], queryFn: () => siteApi.achievements(params), placeholderData: keepPreviousData, retry: notFoundNoRetry })
}

export function useAchievement(slug: string) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['achievement', slug, lang], queryFn: () => siteApi.achievement(slug), retry: notFoundNoRetry })
}

export function useTeam() {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['team', lang], queryFn: siteApi.team, retry: notFoundNoRetry })
}

export function useTestimonials(params: ListParams) {
  return useQuery({ queryKey: ['testimonials', params], queryFn: () => siteApi.testimonials(params), placeholderData: keepPreviousData, retry: notFoundNoRetry })
}

export function useNews(params: ListParams) {
  return useQuery({ queryKey: ['news', params], queryFn: () => newsApi.list(params), placeholderData: keepPreviousData, retry: notFoundNoRetry })
}

export function useArticle(slug: string) {
  return useQuery({ queryKey: ['article', slug], queryFn: () => newsApi.article(slug), retry: notFoundNoRetry })
}

export function useProjects(params: ListParams) {
  return useQuery({ queryKey: ['projects', params], queryFn: () => projectsApi.list(params), placeholderData: keepPreviousData, retry: notFoundNoRetry })
}

export function useProject(key: string) {
  return useQuery({ queryKey: ['project', key], queryFn: () => projectsApi.detail(key), retry: notFoundNoRetry })
}

export function usePreview(token: string) {
  const { lang } = useI18n()
  return useQuery({ queryKey: ['preview', token, lang], queryFn: () => siteApi.preview(token), retry: false, staleTime: 0 })
}

export const isNotFound = (error: unknown) => error instanceof ApiError && error.kind === 'not_found'

/** Open vacancies of the existing careers site — only to show the «join the team» CTA honestly. */
export function useOpenVacancies(enabled: boolean) {
  return useQuery({ queryKey: ['vacancies-count'], queryFn: careersApi.vacancies, enabled, staleTime: 10 * 60_000, retry: false })
}
