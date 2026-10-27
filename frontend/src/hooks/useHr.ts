import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { recruitmentApi } from '@/api/hr'
import type {
  AccountRequestInput,
  ApplicationInput,
  ApplicationsParams,
  ApplicationUpdateInput,
  HireInput,
  InterviewInput,
  InterviewResultInput,
  InterviewsParams,
  PeriodParams,
  PersonFields,
  ReportFilters,
  VacanciesParams,
  VacancyInput,
  VacancyStatus,
} from '@/types/hr'

/** Подбор персонала (apps.recruitment). Любое изменение обновляет все HR-данные:
 * этапы откликов, календарь, главная, напоминания и отчёты связаны между собой. */
const KEY = 'hr'

export function useRecruitmentMeta() {
  return useQuery({ queryKey: [KEY, 'meta'], queryFn: recruitmentApi.meta, staleTime: 5 * 60_000 })
}

export function useHrDashboard(params: { date_from?: string; date_to?: string }) {
  return useQuery({ queryKey: [KEY, 'dashboard', params], queryFn: () => recruitmentApi.dashboard(params), placeholderData: keepPreviousData })
}

export function useHrReminders(mine: boolean) {
  return useQuery({
    queryKey: [KEY, 'reminders', mine],
    queryFn: () => recruitmentApi.reminders(mine ? { mine: 'true' } : {}),
    refetchInterval: 5 * 60_000,
  })
}

export function useVacancies(params: VacanciesParams) {
  return useQuery({ queryKey: [KEY, 'vacancies', params], queryFn: () => recruitmentApi.vacancies(params), placeholderData: keepPreviousData })
}

/** Все вакансии для выпадающих списков (их немного). */
export function useAllVacancies() {
  return useVacancies({ page_size: 100, ordering: 'title' })
}

export function useVacancy(id: number | null) {
  return useQuery({ queryKey: [KEY, 'vacancy', id], queryFn: () => recruitmentApi.vacancy(id as number), enabled: id !== null })
}

export function useApplications(params: ApplicationsParams, enabled = true) {
  return useQuery({ queryKey: [KEY, 'applications', params], queryFn: () => recruitmentApi.applications(params), placeholderData: keepPreviousData, enabled })
}

export function useBoard(params: ApplicationsParams, enabled = true) {
  return useQuery({ queryKey: [KEY, 'board', params], queryFn: () => recruitmentApi.board(params), placeholderData: keepPreviousData, enabled })
}

export function useCandidatesList(params: { search?: string; page?: number }) {
  return useQuery({ queryKey: [KEY, 'candidates', params], queryFn: () => recruitmentApi.candidates(params), placeholderData: keepPreviousData })
}

export function useCandidate(id: number) {
  return useQuery({ queryKey: [KEY, 'candidate', id], queryFn: () => recruitmentApi.candidate(id) })
}

export function useCandidateHistory(id: number) {
  return useQuery({ queryKey: [KEY, 'candidate', id, 'history'], queryFn: () => recruitmentApi.history(id) })
}

export function useCandidateNotes(id: number) {
  return useQuery({ queryKey: [KEY, 'candidate', id, 'notes'], queryFn: () => recruitmentApi.notes(id) })
}

export function useInterviews(params: InterviewsParams, enabled = true) {
  return useQuery({ queryKey: [KEY, 'interviews', params], queryFn: () => recruitmentApi.interviews(params), placeholderData: keepPreviousData, enabled })
}

export function useDailyReport(params: ReportFilters & { date?: string }) {
  return useQuery({ queryKey: [KEY, 'report', 'daily', params], queryFn: () => recruitmentApi.daily(params), placeholderData: keepPreviousData })
}

export function useMonthlyReport(params: PeriodParams) {
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

export function useVacancyStatus() {
  return useHrMutation(({ id, status }: { id: number; status: VacancyStatus }) => recruitmentApi.setVacancyStatus(id, status))
}

export function useCreateApplication() {
  return useHrMutation(({ payload, resume }: { payload: ApplicationInput; resume?: File | null }) =>
    recruitmentApi.createApplication(payload, resume))
}

export function useUpdateApplication() {
  return useHrMutation(({ id, payload }: { id: number; payload: ApplicationUpdateInput }) => recruitmentApi.updateApplication(id, payload))
}

export function useUpdateCandidate() {
  return useHrMutation(({ id, payload }: { id: number; payload: Partial<PersonFields> }) => recruitmentApi.updateCandidate(id, payload))
}

export function useChangeApplicationStatus() {
  return useHrMutation(({ id, status, comment }: { id: number; status: string; comment: string }) =>
    recruitmentApi.changeStatus(id, status, comment))
}

export function useAddNote() {
  return useHrMutation(({ id, text, application }: { id: number; text: string; application: number | null }) =>
    recruitmentApi.addNote(id, text, application))
}

export function useMergeCandidate() {
  return useHrMutation(({ id, target }: { id: number; target: number }) => recruitmentApi.mergeCandidate(id, target))
}

export function useNotDuplicate() {
  return useHrMutation((id: number) => recruitmentApi.notDuplicate(id))
}

export function useEraseCandidate() {
  return useHrMutation(({ id, reason }: { id: number; reason: string }) => recruitmentApi.eraseCandidate(id, reason))
}

export function useUploadResume() {
  return useHrMutation(({ id, file }: { id: number; file: File }) => recruitmentApi.uploadResume(id, file))
}

export function useHireCandidate() {
  return useHrMutation(({ id, payload }: { id: number; payload: HireInput }) => recruitmentApi.hire(id, payload))
}

export function useRequestAccount() {
  return useHrMutation(({ id, payload }: { id: number; payload: AccountRequestInput }) => recruitmentApi.requestAccount(id, payload))
}

export function useSaveInterview() {
  return useHrMutation(({ id, application, payload }: { id?: number; application?: number; payload: InterviewInput }) =>
    id ? recruitmentApi.updateInterview(id, payload) : recruitmentApi.scheduleInterview({ ...payload, application: application as number }))
}

export function useCancelInterview() {
  return useHrMutation(({ id, reason }: { id: number; reason: string }) => recruitmentApi.cancelInterview(id, reason))
}

export function useNoShowInterview() {
  return useHrMutation(({ id, comment }: { id: number; comment: string }) => recruitmentApi.markNoShow(id, comment))
}

export function useRecordInterviewResult() {
  return useHrMutation(({ id, payload }: { id: number; payload: InterviewResultInput }) => recruitmentApi.recordResult(id, payload))
}
