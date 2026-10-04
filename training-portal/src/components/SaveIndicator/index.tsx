import type { SaveState } from '@/hooks/useAttemptRunner'
import { t } from '@/i18n'

import { Icon } from '../Icon'

const VIEW: Record<Exclude<SaveState, 'idle'>, { icon: string; text: string; color: string }> = {
  saving: { icon: 'arrow-repeat', text: t.save.saving, color: 'var(--text-3)' },
  saved: { icon: 'cloud-check', text: t.save.saved, color: 'var(--green-600)' },
  offline: { icon: 'wifi-off', text: t.save.offline, color: 'var(--red-600)' },
}

/** «Сакталууда… / Сакталды / Байланыш жок» */
export function SaveIndicator({ state }: { state: SaveState }) {
  if (state === 'idle') return null
  const view = VIEW[state]
  return (
    <span role="status" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 700, color: view.color }}>
      <Icon name={view.icon} />{view.text}
    </span>
  )
}
