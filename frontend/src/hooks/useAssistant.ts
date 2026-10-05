import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { assistantApi, surveysApi, type GroupListParams, type StudentListParams } from '@/api/assistant'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'

/** Every Assistant Workspace query lives under one key root, so a write can
 * refresh everything it may have touched (a transfer changes two groups,
 * the dashboard, the student list…) with one invalidation. */
export const ASSISTANT_KEY = ['assistant'] as const

export function useAssistantDashboard() {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'dashboard'], queryFn: assistantApi.dashboard })
}

export function useAssistantOptions() {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'options'], queryFn: assistantApi.options, staleTime: 60_000 })
}

export function useAssistantGroups(params: GroupListParams) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'groups', params], queryFn: () => assistantApi.groups(params), placeholderData: keepPreviousData })
}

export function useAssistantGroup(id: number | undefined) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'group', id], queryFn: () => assistantApi.group(id as number), enabled: id !== undefined })
}

export function useAssistantStudents(params: StudentListParams, enabled = true) {
  return useQuery({
    queryKey: [...ASSISTANT_KEY, 'students', params],
    queryFn: () => assistantApi.students(params),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useAssistantStudent(id: number | undefined) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'student', id], queryFn: () => assistantApi.student(id as number), enabled: id !== undefined })
}

export function useAssistantSchedule(params: { start: string; end: string; group?: number; teacher?: number }) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'schedule', params], queryFn: () => assistantApi.schedule(params), placeholderData: keepPreviousData })
}

export function useAssistantAttendance(params: { date: string; group?: number }) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'attendance', params], queryFn: () => assistantApi.attendance(params) })
}

export function useAssistantScholarships() {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'scholarships'], queryFn: assistantApi.scholarships })
}

export function useSurveys(params: { status?: string; group?: number; search?: string; page?: number }) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'surveys', params], queryFn: () => surveysApi.list(params), placeholderData: keepPreviousData })
}

export function useSurvey(id: number | undefined) {
  return useQuery({ queryKey: [...ASSISTANT_KEY, 'survey', id], queryFn: () => surveysApi.get(id as number), enabled: id !== undefined })
}

export function useSurveyAnalytics(id: number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...ASSISTANT_KEY, 'survey-analytics', id],
    queryFn: () => surveysApi.analytics(id as number),
    enabled: id !== undefined && enabled,
  })
}

/**
 * Every Assistant write: on success — the toast message and a refresh of
 * every workspace query; on error — the API's own message as an error toast
 * (validation, conflicts…) — unless the form shows it inline
 * (useAssistantFormMutation).
 */
export function useAssistantMutation<TVars, TResult>(
  fn: (vars: TVars) => Promise<TResult>,
  successMessage?: string | ((result: TResult, vars: TVars) => string),
  { silentError = false }: { silentError?: boolean } = {},
) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result, vars) => {
      await queryClient.invalidateQueries({ queryKey: ASSISTANT_KEY })
      const message = typeof successMessage === 'function' ? successMessage(result, vars) : successMessage
      if (message) showToast(message, 'success')
    },
    onError: (error) => {
      if (!silentError) showToast(extractErrorMessage(error), 'error')
    },
  })
}

/** A form's write: its error is shown inside the form (FormError), so no
 * second copy of it as a toast. */
export function useAssistantFormMutation<TVars, TResult>(
  fn: (vars: TVars) => Promise<TResult>,
  successMessage?: string | ((result: TResult, vars: TVars) => string),
) {
  return useAssistantMutation(fn, successMessage, { silentError: true })
}
