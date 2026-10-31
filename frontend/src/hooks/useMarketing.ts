import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { marketingApi } from '@/api/marketing'
import type { CampaignInput, ContentInput, ContentParams, ReportPeriod, TaskInput, TasksParams } from '@/types/marketing'

/** Кабинет маркетинга (apps.marketing). Любое изменение обновляет все данные
 * кабинета: главная, контент-план, задачи и отчёты связаны между собой. */
const KEY = 'marketing'

export function useMarketingMeta() {
  return useQuery({ queryKey: [KEY, 'meta'], queryFn: marketingApi.meta, staleTime: 5 * 60_000 })
}

export function useMarketingDashboard(params: { date_from?: string; date_to?: string }) {
  return useQuery({ queryKey: [KEY, 'dashboard', params], queryFn: () => marketingApi.dashboard(params), placeholderData: keepPreviousData })
}

export function useMarketingReport(params: { period: ReportPeriod; date?: string }) {
  return useQuery({ queryKey: [KEY, 'report', params], queryFn: () => marketingApi.report(params), placeholderData: keepPreviousData })
}

export function useContentItems(params: ContentParams) {
  return useQuery({ queryKey: [KEY, 'content', params], queryFn: () => marketingApi.content(params), placeholderData: keepPreviousData })
}

export function useMarketingTasks(params: TasksParams) {
  return useQuery({ queryKey: [KEY, 'tasks', params], queryFn: () => marketingApi.tasks(params), placeholderData: keepPreviousData })
}

function useInvalidate() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: [KEY] })
}

export function useSaveContent() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<ContentInput> }) =>
      id === null ? marketingApi.createContent(body as ContentInput) : marketingApi.updateContent(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteContent() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: marketingApi.deleteContent, onSuccess: invalidate })
}

export function useSaveTask() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Partial<TaskInput> }) =>
      id === null ? marketingApi.createTask(body as TaskInput) : marketingApi.updateTask(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteTask() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: marketingApi.deleteTask, onSuccess: invalidate })
}

export function useCampaigns(params: { status?: string; page?: number; page_size?: number }) {
  return useQuery({ queryKey: [KEY, 'campaigns', params], queryFn: () => marketingApi.campaigns(params), placeholderData: keepPreviousData })
}

export function useSaveCampaign() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: CampaignInput }) => marketingApi.saveCampaign(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteCampaign() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: marketingApi.deleteCampaign, onSuccess: invalidate })
}
