import type { BadgeTone } from '@/components/ui/Badge'
import type { DayStatus } from '@/types/staffAttendance'

export const DAY_STATUS_TONE: Record<DayStatus, BadgeTone> = {
  not_arrived: 'muted',
  at_work: 'success',
  day_finished: 'info',
  no_check_in: 'danger',
  no_check_out: 'warning',
  day_off: 'muted',
  not_tracked: 'muted',
}
