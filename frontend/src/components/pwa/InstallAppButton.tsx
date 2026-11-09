import { Download } from 'lucide-react'

import { installAvailability, openAppSettings, usePwaState } from '@/pwa/store'

/** Header shortcut, shown only while installation is actually possible —
 * gone for good once the app is installed (push settings stay in the
 * notifications panel and the profile). */
export function InstallAppButton() {
  const pwa = usePwaState()
  const availability = installAvailability(pwa)
  if (availability !== 'available' && !(availability === 'manual' && pwa.method !== 'prompt')) return null
  return (
    <button
      type="button"
      onClick={openAppSettings}
      aria-label="Установить приложение"
      title="Установить приложение"
      className="flex size-10 items-center justify-center rounded-lg text-brand-700 hover:bg-brand-50"
    >
      <Download className="size-5" aria-hidden />
    </button>
  )
}
