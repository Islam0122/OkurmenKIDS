import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { monthlyReportsApi, type MonthlyReportListParams } from '@/api/monthlyReports'

export function useMonthlyReportsList(params: MonthlyReportListParams = {}) {
  return useQuery({
    queryKey: ['monthly-reports', 'list', params],
    queryFn: () => monthlyReportsApi.list(params),
  })
}

export function useMonthlyReportDetail(id: number | undefined) {
  return useQuery({
    queryKey: ['monthly-reports', 'detail', id],
    queryFn: () => monthlyReportsApi.get(id as number),
    enabled: id !== undefined,
  })
}

export function useCreateMonthlyReport() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { year: number; month: number }) => monthlyReportsApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['monthly-reports', 'list'] })
    },
  })
}

export function useUpdateMonthlyReportComment(id: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (comment: string) => monthlyReportsApi.updateComment(id, comment),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['monthly-reports', 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: ['monthly-reports', 'list'] })
    },
  })
}
