import type { BadgeTone } from '@/components/ui/Badge'
import type { KPIStatus } from '@/types/kpi'

/** Presentation only: how each backend-computed KPI status is colored.
 * The status itself always comes from the API (`services.kpi_engine`) —
 * never derive it from a KPI value on the frontend. */
export const KPI_STATUS_BADGE_TONE: Record<KPIStatus, BadgeTone> = {
  good: 'success',
  attention: 'warning',
  low: 'danger',
  no_data: 'muted',
}

export const KPI_STATUS_CARD_TONE: Record<KPIStatus, 'default' | 'warning' | 'danger'> = {
  good: 'default',
  attention: 'warning',
  low: 'danger',
  no_data: 'default',
}
