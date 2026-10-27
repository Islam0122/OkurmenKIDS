import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { recruitmentApi } from '@/api/hr'
import type {
  CandidateInput,
  CandidatesParams,
  HireInput,
  InterviewInput,
  InterviewResultInput,
  InterviewsParams,
  ReportFilters,
  VacancyInput,
} from '@/types/hr'

/** Подбор персонала (apps.recruitment). Любое изменение обновляет все HR-данные:
 * этапы кандидатов, календарь, главная и отчёты связаны между собой. */
const KEY = 'hr'

export function useRecruitmentMeta() {
  return useQuery({ queryKey: [KEY, 'meta'], queryFn: recruitmentApi.meta, staleTime: 5 * 60_000 })
}

export function useHrDashboard(params: { date_from?: string; date_to?: string }) {
  return useQuery({ queryKey: [KEY, 'dashboard', params], queryFn: () => recruitmentApi.dashboard(params), placeholderData: keepPreviousData })
}

export function useVacancies(params: { status?: string; search?: string; page?: number; page_size?: number }) {
  return useQuery({ queryKey: [KEY, 'vacancies', params], queryFn: () => recruitmentApi.vacancies(params), placeholderData: keepPreviousData })
}

/** Все вакансии для выпадающих списков (их немного). */
export function useAllVacancies() {
  return useVacancies({ page_size: 100 })
}

export function useCandidates(params: CandidatesParams, enabled = true) {
  return useQuery({ queryKey: [KEY, 'candidates', params], queryFn: () => recruitmentApi.candidates(params), placeholderData: keepPreviousData, enabled })
}

export function useCandidate(id: number) {
  return useQuery({ queryKey: [KEY, 'candidate', id], queryFn: () => recruitmentApi.candidate(id) })
}

export function useCandidateHistory(id: number) {
  return useQuery({ queryKey: [KEY, 'candidate', id, 'history'], queryFn: () => recruitmentApi.history(id) })
}

export function useInterviews(params: InterviewsParams) {
  return useQuery({ queryKey: [KEY, 'interviews', params], queryFn: () => recruitmentApi.interviews(params), placeholderData: keepPreviousData })
}

export function useDailyReport(params: ReportFilters & { date?: string }) {
  return useQuery({ queryKey: [KEY, 'report', 'daily', params], queryFn: () => recruitmentApi.daily(params), placeholderData: keepPreviousData })
}

export function useMonthlyReport(params: ReportFilters & { month?: string }) {
  return useQuery({ queryKey: [KEY, 'report', 'monthly', params], queryFn: () => recruitmentApi.monthly(params), placeholderData: keepPreviousData })
}

function useHrMutation<A, R>(fn: (args: A) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: [KEY] }),
      queryClient.invalidateQueries({ queryKey: ['hr-employees'] }),
    ]),
  })
}

export function useSaveVacancy() {
  return useHrMutation(({ id, payload }: { id?: number; payload: VacancyInput }) =>
    id ? recruitmentApi.updateVacancy(id, payload) : recruitmentApi.createVacancy(payload))
}

export function useSaveCandidate() {
  return useHrMutation(({ id, payload }: { id?: number; payload: CandidateInput }) =>
    id ? recruitmentApi.updateCandidate(id, payload) : recruitmentApi.createCandidate(payload))
}

export function useChangeCandidateStatus() {
  return useHrMutation(({ id, status, comment }: { id: number; status: string; comment: string }) =>
    recruitmentApi.changeStatus(id, status, comment))
}

export function useAddCandidateNote() {
  return useHrMutation(({ id, text }: { id: number; text: string }) => recruitmentApi.addNote(id, text))
}

export function useHireCandidate() {
  return useHrMutation(({ id, payload }: { id: number; payload: HireInput }) => recruitmentApi.hire(id, payload))
}

export function useSaveInterview() {
  return useHrMutation(({ id, candidate, payload }: { id?: number; candidate?: number; payload: InterviewInput }) =>
    id ? recruitmentApi.updateInterview(id, payload) : recruitmentApi.scheduleInterview({ ...payload, candidate: candidate as number }))
}

export function useCancelInterview() {
  return useHrMutation(({ id, reason }: { id: number; reason: string }) => recruitmentApi.cancelInterview(id, reason))
}

export function useRecordInterviewResult() {
  return useHrMutation(({ id, payload }: { id: number; payload: InterviewResultInput }) => recruitmentApi.recordResult(id, payload))
}
