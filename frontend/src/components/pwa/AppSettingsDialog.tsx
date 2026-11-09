import { Smartphone } from 'lucide-react'

import { Modal } from '@/components/ui/Modal'
import { closeAppSettings, usePwaState } from '@/pwa/store'

import { AppSettingsPanel } from './AppSettingsPanel'

/** The «Приложение» dialog, opened from the header of any cabinet. */
export function AppSettingsDialog() {
  const { settingsOpen } = usePwaState()
  return (
    <Modal
      isOpen={settingsOpen}
      onClose={closeAppSettings}
      title="Приложение Okurmen Kids"
      icon={<Smartphone className="size-5 text-brand-600" aria-hidden />}
    >
      <AppSettingsPanel />
    </Modal>
  )
}
