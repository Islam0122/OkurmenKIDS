import { useEffect } from 'react'

import { useAuth } from '@/hooks/useAuth'
import { syncPushSubscription } from '@/pwa/push'

import { AppSettingsDialog } from './AppSettingsDialog'
import { ConnectionStatus } from './ConnectionStatus'
import { InstallPrompt } from './InstallPrompt'
import { UpdatePrompt } from './UpdatePrompt'

/** Everything the installable app adds on top of the LMS, mounted once next
 * to the router: install offer, update banner, connection status, the
 * «Приложение» dialog, and keeping this device's push subscription current. */
export function PwaChrome() {
  const { status } = useAuth()

  useEffect(() => {
    if (status !== 'authenticated') return
    void syncPushSubscription()
    if (!('serviceWorker' in navigator)) return
    const onMessage = (event: MessageEvent) => {
      if (event.data?.type === 'PUSH_SUBSCRIPTION_CHANGED') void syncPushSubscription()
    }
    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [status])

  return (
    <>
      <ConnectionStatus />
      <UpdatePrompt />
      <InstallPrompt />
      <AppSettingsDialog />
    </>
  )
}
