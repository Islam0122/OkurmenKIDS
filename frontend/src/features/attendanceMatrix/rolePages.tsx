import { AttendanceTablesPage } from './AttendanceTablesPage'

/** The same attendance tables for every role — only the summary link and the
 * server-side scope differ (backend: apps.attendance_matrix.access). */
export function TeamLeadAttendancePage() {
  return <AttendanceTablesPage summaryPath="/app/attendance-monitoring" />
}

export function OperationsAttendanceTablesPage() {
  return <AttendanceTablesPage summaryPath="/operations/academy/attendance" />
}

export function AssistantAttendanceTablesPage() {
  return <AttendanceTablesPage summaryPath="/assistant/attendance-summary" />
}
