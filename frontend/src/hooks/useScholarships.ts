import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { scholarshipsApi } from '@/api/scholarships'
import type { RequiredFeedbackItem, TrainerFeedbackInput } from '@/types/scholarship'

export function useScholarshipPeriods() {
  return useQuery({ queryKey: ['scholarships', 'periods'], queryFn: () => scholarshipsApi.periods() })
}

export function useScholarshipRanking(periodId: number | undefined, page = 1) {
  return useQuery({
    queryKey: ['scholarships', 'ranking', periodId, page],
    queryFn: () => scholarshipsApi.ranking(periodId as number, page),
    enabled: periodId !== undefined,
  })
}

export function useScholarshipAnalytics(periodId: number | undefined) {
  return useQuery({
    queryKey: ['scholarships', 'analytics', periodId],
    queryFn: () => scholarshipsApi.analytics(periodId as number),
    enabled: periodId !== undefined,
  })
}

function useInvalidateScholarships() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['scholarships'] })
}

export function useRecalculateScholarship() {
  const invalidate = useInvalidateScholarships()
  return useMutation({ mutationFn: (periodId: number) => scholarshipsApi.recalculate(periodId), onSuccess: invalidate })
}

export function useApproveScholarship() {
  const invalidate = useInvalidateScholarships()
  return useMutation({ mutationFn: (periodId: number) => scholarshipsApi.approve(periodId), onSuccess: invalidate })
}

export function useRequiredFeedback(periodId: number | undefined) {
  return useQuery({
    queryKey: ['scholarships', 'required-feedback', periodId],
    queryFn: () => scholarshipsApi.requiredFeedback(periodId as number),
    enabled: periodId !== undefined,
  })
}

export function useSaveFeedback(periodId: number) {
  const invalidate = useInvalidateScholarships()
  return useMutation({
    mutationFn: ({ item, values }: { item: RequiredFeedbackItem; values: TrainerFeedbackInput }) =>
      item.feedback
        ? scholarshipsApi.updateFeedback(item.feedback.id, values)
        : scholarshipsApi.createFeedback({ ...values, period: periodId, student: item.student, subject: item.subject }),
    onSuccess: invalidate,
  })
}
