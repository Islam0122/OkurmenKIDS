import { useEffect } from 'react'
import { Download } from 'lucide-react'

import { promptInstall } from '@/pwa/install'
import { installAvailability, openAppSettings, registerInlineInstallButton, usePwaState } from '@/pwa/store'

/** Header shortcut, shown only while installation is actually possible —
 * gone for good once the app is installed (push settings stay in the
 * notifications panel and the profile). */
export function InstallAppButton() {
  const pwa = usePwaState()
  const availability = installAvailability(pwa)
  const visible = availability === 'available' || (availability === 'manual' && pwa.method !== 'prompt')
  useEffect(() => (visible ? registerInlineInstallButton() : undefined), [visible])
  if (!visible) return null
  return (
    <button
      type="button"
      // Chromium: the browser's own install dialog, straight from the click.
      // Apple: no install API exists — the dialog shows the manual steps.
      onClick={() => (availability === 'available' ? void promptInstall() : openAppSettings())}
      aria-label="Установить приложение"
      title="Установить приложение"
      className="flex size-10 items-center justify-center rounded-lg text-brand-700 hover:bg-brand-50"
    >
      <Download className="size-5" aria-hidden />
    </button>
  )
}
