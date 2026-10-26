import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { EmptyState } from '@/components/ui/EmptyState'
import { useAuth } from '@/hooks/useAuth'
import { isStaffOnlyRole } from '@/lib/roles'
import type { UserRole } from '@/types/auth'

import { PersonalAttendancePage } from './PersonalAttendancePage'
import { personalPathFor, type PersonalVariant } from './roles'
import { OFFICE_CODE_RE } from './scanUrl'

/** /attendance — открыть личную страницу своей категории. */
export function AttendanceHomeRedirect() {
  const { user } = useAuth()
  return <Navigate to={personalPathFor(user?.role)} replace />
}

export function TeacherAttendancePage() {
  return <PersonalAttendancePage variant="teacher" />
}

export function AccountingAttendancePage() {
  return <PersonalAttendancePage variant="accounting" />
}

export function AssistantAttendancePage() {
  return <PersonalAttendancePage variant="assistant" />
}

export function OfficeAttendancePage() {
  return <PersonalAttendancePage variant="office" />
}

export function StaffAttendancePage() {
  return <PersonalAttendancePage variant="staff" />
}

function variantFor(role: UserRole | undefined): PersonalVariant {
  if (role === 'teacher') return 'teacher'
  if (role === 'accountant') return 'accounting'
  if (role === 'assistant') return 'assistant'
  if (isStaffOnlyRole(role)) return 'staff'
  return 'office'
}

/** /attendance/scan?office=<код> — сюда ведёт QR-код, отсканированный
 * обычной камерой телефона. Сам переход ничего не отмечает: нужен вход,
 * свежая геолокация и проверки сервера — их выполняет MarkFlow. */
export function ScanLandingPage() {
  const { user } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const code = params.get('office') ?? ''
  const home = personalPathFor(user?.role)

  if (!OFFICE_CODE_RE.test(code)) {
    return <EmptyState title="Некорректная ссылка QR-кода" description="Отсканируйте QR-код офиса ещё раз или откройте свой кабинет посещаемости." />
  }
  return <PersonalAttendancePage variant={variantFor(user?.role)} presetCode={code} onFlowDone={() => navigate(home, { replace: true })} />
}
