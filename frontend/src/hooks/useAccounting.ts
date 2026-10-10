import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { accountingApi } from '@/api/accounting'
import type { PayrollFilters } from '@/api/accounting'
import type { MySalaryFilters, PeriodSelection } from '@/types/accounting'

export function useAccountingOptions() {
  return useQuery({ queryKey: ['accounting', 'options'], queryFn: accountingApi.options, staleTime: 5 * 60 * 1000 })
}

export function useAccountingDashboard(selection: PeriodSelection) {
  return useQuery({
    queryKey: ['accounting', 'dashboard', selection],
    queryFn: () => accountingApi.dashboard(selection),
    placeholderData: keepPreviousData,
  })
}

export function useAccountingEmployees(selection: PeriodSelection, filters: PayrollFilters & { payment_status?: string }) {
  return useQuery({
    queryKey: ['accounting', 'employees', selection, filters],
    queryFn: () => accountingApi.employees(selection, filters),
    placeholderData: keepPreviousData,
  })
}

export function usePayroll(id: number | undefined) {
  return useQuery({
    queryKey: ['accounting', 'payroll', id],
    queryFn: () => accountingApi.payroll(id as number),
    enabled: id !== undefined && !Number.isNaN(id),
  })
}

export function useSalaryProfiles(search: string) {
  return useQuery({
    queryKey: ['accounting', 'profiles', search],
    queryFn: () => accountingApi.profiles(search ? { search } : undefined),
    placeholderData: keepPreviousData,
  })
}

export function useStudentPayments(params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ['accounting', 'student-payments', params],
    queryFn: () => accountingApi.studentPayments(params),
    placeholderData: keepPreviousData,
  })
}

export function useAuditLog(params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ['accounting', 'audit', params],
    queryFn: () => accountingApi.audit(params),
    placeholderData: keepPreviousData,
  })
}

export function useMyPayrolls() {
  return useQuery({ queryKey: ['accounting', 'my'], queryFn: accountingApi.myPayrolls })
}

/** Every write changes totals somewhere — refetch the whole section. */
export function useAccountingMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting'] }),
  })
}

export function useCourseSettings() {
  return useQuery({ queryKey: ['accounting', 'course-settings'], queryFn: accountingApi.courseSettings })
}

export function useCourseCycles(params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ['accounting', 'cycles', params],
    queryFn: () => accountingApi.cycles(params),
    placeholderData: keepPreviousData,
  })
}

export function useMySalary(filters: MySalaryFilters) {
  return useQuery({
    queryKey: ['accounting', 'my-salary', filters],
    queryFn: () => accountingApi.mySalary(filters),
    placeholderData: keepPreviousData,
  })
}
