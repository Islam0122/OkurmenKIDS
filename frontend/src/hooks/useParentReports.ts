import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { parentReportsApi, type ParentReportListParams } from '@/api/parentReports'
import type { ParentReportConfig, ParentReportDetail, ParentReportTextUpdate } from '@/types/parentReports'

const KEY = ['parent-reports'] as const

export function useParentReportHistory(params: ParentReportListParams) {
  return useQuery({
    queryKey: [...KEY, 'list', params],
    queryFn: () => parentReportsApi.list(params),
  })
}

export function useParentReport(id: number | null) {
  return useQuery({
    queryKey: [...KEY, 'detail', id],
    queryFn: () => parentReportsApi.get(id as number),
    enabled: id !== null,
  })
}

/** Preview of a configuration — recomputed on the server on every call, never cached for long. */
export function useParentReportPreview(groupId: number | null, config: ParentReportConfig | null) {
  return useQuery({
    queryKey: [...KEY, 'preview', groupId, config],
    queryFn: () => parentReportsApi.preview(groupId as number, config as ParentReportConfig),
    enabled: groupId !== null && config !== null,
    staleTime: 0,
  })
}

function useStoreDetail() {
  const queryClient = useQueryClient()
  return (report: ParentReportDetail) => {
    queryClient.setQueryData([...KEY, 'detail', report.id], report)
    void queryClient.invalidateQueries({ queryKey: [...KEY, 'list'] })
  }
}

export function useGenerateParentReport() {
  const store = useStoreDetail()
  return useMutation({
    mutationFn: ({ groupId, config }: { groupId: number; config: ParentReportConfig }) =>
      parentReportsApi.generate(groupId, config),
    onSuccess: store,
  })
}

export function useRegenerateParentReport() {
  const store = useStoreDetail()
  return useMutation({ mutationFn: (id: number) => parentReportsApi.regenerate(id), onSuccess: store })
}

export function useSaveParentReportText(id: number) {
  const store = useStoreDetail()
  return useMutation({
    mutationFn: (payload: ParentReportTextUpdate) => parentReportsApi.updateText(id, payload),
    onSuccess: store,
  })
}

/** Object URL of one PNG page, fetched with auth; revoked when the query is dropped. */
export function useParentReportImage(reportId: number, imageId: number | null) {
  return useQuery({
    queryKey: [...KEY, 'image', reportId, imageId],
    queryFn: async () => URL.createObjectURL(await parentReportsApi.imageBlob(reportId, imageId as number)),
    enabled: imageId !== null,
    staleTime: Infinity,
    gcTime: 5 * 60 * 1000,
  })
}
