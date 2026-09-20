import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { academyReportsApi, type AcademyReportListParams } from '@/api/academyReports'

export function useAcademyReportsList(params: AcademyReportListParams = {}) {
  return useQuery({
    queryKey: ['academy-reports', 'list', params],
    queryFn: () => academyReportsApi.list(params),
  })
}

export function useAcademyReportDetail(id: number | undefined) {
  return useQuery({
    queryKey: ['academy-reports', 'detail', id],
    queryFn: () => academyReportsApi.get(id as number),
    enabled: id !== undefined,
  })
}

export function useCreateAcademyReport() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { year: number; month: number }) => academyReportsApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['academy-reports', 'list'] })
    },
  })
}

export function useUpdateAcademyReportComment(id: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (comment: string) => academyReportsApi.updateComment(id, comment),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['academy-reports', 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: ['academy-reports', 'list'] })
    },
  })
}
