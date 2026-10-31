import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { notificationsApi, operationsApi, tasksApi, workReportsApi } from '@/api/operations'
import type { IssuesParams, KpiTargetInput, OpsFiltersParams, OpsSettings, Priority, RecurrenceInput, TaskInput, TasksParams, WorkReport } from '@/types/operations'

/** Кабинет операционного директора и задачи сотрудников. Любое изменение
 * (задача, цель, проблема, отчёт) обновляет связанные данные: главная,
 * ежедневный контроль и KPI считаются из тех же записей. */
const OPS = 'operations'
const TASKS = 'tasks'
type Params = OpsFiltersParams & Record<string, string | number | undefined>

function useOps<T>(key: string, fn: () => Promise<T>, params?: unknown, enabled = true) {
  return useQuery({ queryKey: [OPS, key, params], queryFn: fn, placeholderData: keepPreviousData, enabled })
}

export const useOpsMeta = () => useQuery({ queryKey: [OPS, 'meta'], queryFn: operationsApi.meta, staleTime: 5 * 60_000 })
export const useOpsDashboard = (p: Params) => useOps('dashboard', () => operationsApi.dashboard(p), p)
export const useOpsDepartments = (p: Params) => useOps('departments', () => operationsApi.departments(p), p)
export const useOpsDepartment = (key: string, p: Params) => useOps(`department-${key}`, () => operationsApi.department(key, p), p)
export const useOpsEmployees = (p: Params) => useOps('employees', () => operationsApi.employees(p), p)
export const useOpsEmployee = (id: number, p: Params) => useOps(`employee-${id}`, () => operationsApi.employee(id, p), p)
export const useOpsTrainers = (p: Params) => useOps('trainers', () => operationsApi.trainers(p), p)
export const useOpsTrainer = (id: number, p: Params) => useOps(`trainer-${id}`, () => operationsApi.trainer(id, p), p)
export const useOpsTeamLeads = (p: Params) => useOps('team-leads', () => operationsApi.teamLeads(p), p)
export const useOpsProblemStudents = (p: Params) => useOps('students', () => operationsApi.problemStudents(p), p)
export const useOpsSales = (p: Params) => useOps('sales', () => operationsApi.sales(p), p)
export const useOpsHeadOfSales = (p: Params) => useOps('sales-head', () => operationsApi.headOfSales(p), p)
export const useOpsMarketing = (p: Params) => useOps('marketing', () => operationsApi.marketing(p), p)
export const useOpsHr = (p: Params) => useOps('hr', () => operationsApi.hr(p), p)
export const useOpsAttendance = (p: Params) => useOps('attendance', () => operationsApi.attendance(p), p)
export const useOpsDaily = (date?: string) => useOps('daily', () => operationsApi.daily(date), date)
export const useOpsKpi = (p: Params) => useOps('kpi', () => operationsApi.kpi(p), p)
export const useOpsKpiHistory = (p: Params, enabled: boolean) => useOps('kpi-history', () => operationsApi.kpiHistory(p), p, enabled)
export const useOpsTargets = (p: Record<string, string | undefined>) => useOps('targets', () => operationsApi.targets(p), p)
export const useOpsReports = (p: Params) => useOps('reports', () => operationsApi.reports(p), p)
export const useOpsIssues = (p: IssuesParams) => useOps('issues', () => operationsApi.issues(p), p)
export const useOpsIssue = (id: number | null) => useOps(`issue-${id}`, () => operationsApi.issue(id as number), id, id !== null)
export const useOpsSettings = () => useOps('settings', operationsApi.settings)

function useInvalidate(...keys: string[]) {
  const client = useQueryClient()
  return () => Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key] })))
}

export function useSaveTarget() {
  const invalidate = useInvalidate(OPS)
  return useMutation({ mutationFn: ({ id, body }: { id: number | null; body: KpiTargetInput }) => operationsApi.saveTarget(id, body), onSuccess: invalidate })
}

export function useDeleteTarget() {
  const invalidate = useInvalidate(OPS)
  return useMutation({ mutationFn: operationsApi.deleteTarget, onSuccess: invalidate })
}

export function useIssueActions() {
  const invalidate = useInvalidate(OPS)
  return {
    status: useMutation({ mutationFn: ({ id, status, comment }: { id: number; status: string; comment?: string }) => operationsApi.issueStatus(id, status, comment), onSuccess: invalidate }),
    assign: useMutation({ mutationFn: ({ id, responsible }: { id: number; responsible: number | null }) => operationsApi.issueAssign(id, responsible), onSuccess: invalidate }),
    comment: useMutation({ mutationFn: ({ id, text }: { id: number; text: string }) => operationsApi.issueComment(id, text), onSuccess: invalidate }),
    create: useMutation({
      mutationFn: (body: { title: string; description?: string; department: string; priority: Priority; responsible?: number | null }) => operationsApi.createIssue(body),
      onSuccess: invalidate,
    }),
    scan: useMutation({ mutationFn: operationsApi.scan, onSuccess: invalidate }),
  }
}

export function useSaveOpsSettings() {
  const invalidate = useInvalidate(OPS)
  return useMutation({ mutationFn: (body: Partial<OpsSettings>) => operationsApi.saveSettings(body), onSuccess: invalidate })
}

// --- Задачи ---------------------------------------------------------------------

export const useTasksMeta = () => useQuery({ queryKey: [TASKS, 'meta'], queryFn: tasksApi.meta, staleTime: 5 * 60_000 })
export const useTasks = (params: TasksParams) =>
  useQuery({ queryKey: [TASKS, 'list', params], queryFn: () => tasksApi.list(params), placeholderData: keepPreviousData })
export const useMyTasks = () => useQuery({ queryKey: [TASKS, 'my'], queryFn: tasksApi.my })
export const useTask = (id: number) => useQuery({ queryKey: [TASKS, 'detail', id], queryFn: () => tasksApi.get(id) })
export const useRecurrences = () => useQuery({ queryKey: [TASKS, 'recurrences'], queryFn: tasksApi.recurrences })

export function useTaskMutations() {
  const invalidate = useInvalidate(TASKS, OPS, 'notifications')
  return {
    create: useMutation({ mutationFn: (body: TaskInput) => tasksApi.create(body), onSuccess: invalidate }),
    update: useMutation({ mutationFn: ({ id, body }: { id: number; body: Partial<TaskInput> }) => tasksApi.update(id, body), onSuccess: invalidate }),
    act: useMutation({ mutationFn: ({ id, action, comment }: { id: number; action: string; comment?: string }) => tasksApi.act(id, action, comment), onSuccess: invalidate }),
    addChecklist: useMutation({ mutationFn: ({ id, text }: { id: number; text: string }) => tasksApi.addChecklist(id, text), onSuccess: invalidate }),
    toggleChecklist: useMutation({
      mutationFn: ({ id, itemId, isDone }: { id: number; itemId: number; isDone: boolean }) => tasksApi.toggleChecklist(id, itemId, isDone),
      onSuccess: invalidate,
    }),
    comment: useMutation({ mutationFn: ({ id, text }: { id: number; text: string }) => tasksApi.comment(id, text), onSuccess: invalidate }),
    upload: useMutation({ mutationFn: ({ id, file }: { id: number; file: File }) => tasksApi.upload(id, file), onSuccess: invalidate }),
    deleteAttachment: useMutation({ mutationFn: ({ id, attachmentId }: { id: number; attachmentId: number }) => tasksApi.deleteAttachment(id, attachmentId), onSuccess: invalidate }),
    saveRecurrence: useMutation({ mutationFn: ({ id, body }: { id: number | null; body: RecurrenceInput }) => tasksApi.saveRecurrence(id, body), onSuccess: invalidate }),
    stopRecurrence: useMutation({ mutationFn: tasksApi.stopRecurrence, onSuccess: invalidate }),
  }
}

// --- Отчёты сотрудников и уведомления ----------------------------------------------

export const useWorkReportsMeta = () => useQuery({ queryKey: ['work-reports', 'meta'], queryFn: workReportsApi.meta })
export const useWorkReports = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: ['work-reports', 'list', params], queryFn: () => workReportsApi.list(params), placeholderData: keepPreviousData })

export function useWorkReportMutations() {
  const invalidate = useInvalidate('work-reports', OPS)
  return {
    save: useMutation({ mutationFn: ({ id, body }: { id: number | null; body: Partial<WorkReport> }) => workReportsApi.save(id, body), onSuccess: invalidate }),
    submit: useMutation({ mutationFn: workReportsApi.submit, onSuccess: invalidate }),
    review: useMutation({
      mutationFn: ({ id, decision, comment }: { id: number; decision: 'accept' | 'return'; comment?: string }) => workReportsApi.review(id, decision, comment),
      onSuccess: invalidate,
    }),
  }
}

export const useUnreadNotifications = () =>
  useQuery({ queryKey: ['notifications', 'unread'], queryFn: notificationsApi.unreadCount, refetchInterval: 60_000 })
export const useNotifications = (params: { unread?: '1'; page?: number }) =>
  useQuery({ queryKey: ['notifications', 'list', params], queryFn: () => notificationsApi.list(params), placeholderData: keepPreviousData })

export function useNotificationMutations() {
  const invalidate = useInvalidate('notifications')
  return {
    read: useMutation({ mutationFn: notificationsApi.read, onSuccess: invalidate }),
    readAll: useMutation({ mutationFn: notificationsApi.readAll, onSuccess: invalidate }),
  }
}
