import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BellOff, CheckCircle2, Download, Monitor, Send } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage } from '@/lib/apiError'
import { promptInstall } from '@/pwa/install'
import { isIOS } from '@/pwa/platform'
import {
  currentSubscription,
  disablePush,
  enablePush,
  notificationPermission,
  pushApi,
  pushAvailableHere,
  type PushPreferences,
} from '@/pwa/push'
import { SW_ENABLED } from '@/pwa/register'
import { installAvailability, usePwaState } from '@/pwa/store'
import { cn } from '@/utils/cn'

import { InstallInstructions } from './InstallInstructions'

/** «Приложение»: installation status and push notifications for this device.
 * Lives in the header dialog (every cabinet) and on the profile pages. */
export function AppSettingsPanel({ className }: { className?: string }) {
  // Push is per account: guests (public sites) see installation only.
  const { status } = useAuth()
  return (
    <div className={cn('space-y-6', className)}>
      <InstallSection />
      {status === 'authenticated' ? (
        <>
          <div className="border-t border-border" />
          <NotificationsSection />
        </>
      ) : null}
    </div>
  )
}

function SectionTitle({ icon: Icon, title, aside }: { icon: typeof Bell; title: string; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Icon className="size-4 text-ink-muted" aria-hidden />
        {title}
      </h3>
      {aside}
    </div>
  )
}

function InstallSection() {
  const pwa = usePwaState()
  const availability = installAvailability(pwa)

  return (
    <section>
      <SectionTitle
        icon={Monitor}
        title="Приложение"
        aside={availability === 'installed' ? <Badge tone="success">Установлено</Badge> : null}
      />
      {availability === 'installed' ? (
        <p className="flex items-start gap-2 text-sm text-ink-secondary">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-500" aria-hidden />
          {pwa.standalone
            ? 'Okurmen Kids открыт как приложение на этом устройстве.'
            : 'Okurmen Kids установлен на этом устройстве — открывайте его с рабочего стола или из списка приложений.'}
        </p>
      ) : availability === 'available' ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-secondary">Отдельное окно, запуск в одно нажатие и уведомления — без магазина приложений.</p>
          <Button leftIcon={<Download className="size-4" aria-hidden />} onClick={() => void promptInstall()}>
            Установить
          </Button>
        </div>
      ) : availability === 'unsupported' ? (
        <p className="text-sm text-ink-secondary">
          Этот браузер не умеет устанавливать веб-приложения. Откройте Okurmen Kids в Chrome, Edge или Safari.
        </p>
      ) : (
        <InstallInstructions method={pwa.method} />
      )}
    </section>
  )
}

const PREFERENCE_LABELS: Record<keyof PushPreferences, { title: string; hint: string }> = {
  tasks: { title: 'Задачи', hint: 'Новые задачи, дедлайны, проверка и комментарии' },
  reports: { title: 'Отчёты', hint: 'Несданные и возвращённые отчёты' },
  alerts: { title: 'KPI и проблемы', hint: 'Показатели ниже цели и найденные проблемы' },
}

function NotificationsSection() {
  const pwa = usePwaState()
  const available = pushAvailableHere()
  const [permission, setPermission] = useState(notificationPermission)

  const config = useQuery({ queryKey: ['push', 'config'], queryFn: pushApi.config, enabled: available, staleTime: 5 * 60_000 })
  const serverEnabled = Boolean(config.data?.enabled && config.data.public_key)

  let body: ReactNode
  if (!available) {
    body = (
      <p className="text-sm text-ink-secondary">
        {!SW_ENABLED
          ? 'Push-уведомления работают в рабочей (production) версии приложения.'
          : isIOS() && !pwa.standalone
            ? 'На iPhone и iPad уведомления приходят в установленное приложение (iOS 16.4 и новее). Установите Okurmen Kids на экран «Домой» и откройте эту настройку там.'
            : 'Этот браузер не поддерживает push-уведомления.'}
      </p>
    )
  } else if (config.isPending) {
    body = <p className="text-sm text-ink-muted">Проверяем настройки…</p>
  } else if (config.isError) {
    body = <p className="text-sm text-ink-secondary">Не удалось получить настройки уведомлений. Проверьте подключение и откройте раздел снова.</p>
  } else if (!serverEnabled) {
    body = <p className="text-sm text-ink-secondary">Push-уведомления пока не включены администратором. Уведомления по-прежнему доступны в колокольчике.</p>
  } else if (permission === 'denied') {
    body = (
      <p className="text-sm text-ink-secondary">
        Уведомления запрещены для этого сайта в настройках браузера. Разрешите их (значок замка у адреса сайта → «Уведомления») и вернитесь сюда.
      </p>
    )
  } else {
    body = <DeviceSubscription publicKey={config.data!.public_key} onPermission={setPermission} />
  }

  return (
    <section>
      <SectionTitle icon={Bell} title="Уведомления на этом устройстве" />
      {body}
    </section>
  )
}

function DeviceSubscription({
  publicKey,
  onPermission,
}: {
  publicKey: string
  onPermission: (permission: NotificationPermission | 'unsupported') => void
}) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const subscription = useQuery({ queryKey: ['push', 'subscription'], queryFn: currentSubscription, staleTime: Infinity })
  const subscribed = Boolean(subscription.data)

  const toggle = useMutation({
    mutationFn: async () => {
      if (subscribed) {
        await disablePush()
        return 'disabled' as const
      }
      return enablePush(publicKey)
    },
    onSuccess: (result) => {
      onPermission(notificationPermission())
      void queryClient.invalidateQueries({ queryKey: ['push', 'subscription'] })
      if (result === 'enabled') showToast('Уведомления включены на этом устройстве', 'success')
      else if (result === 'disabled') showToast('Уведомления на этом устройстве выключены')
      else if (result === 'denied') showToast('Браузер не разрешил уведомления', 'error')
    },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось изменить настройку уведомлений'), 'error'),
  })

  const test = useMutation({
    mutationFn: pushApi.sendTest,
    onSuccess: ({ delivered }) =>
      showToast(delivered ? 'Тестовое уведомление отправлено' : 'Нет устройств для отправки — включите уведомления ещё раз', delivered ? 'success' : 'error'),
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось отправить тестовое уведомление'), 'error'),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-surface-muted/60 p-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={cn(
              'flex size-9 shrink-0 items-center justify-center rounded-full',
              subscribed ? 'bg-brand-50 text-brand-700' : 'bg-surface-hover text-ink-muted',
            )}
          >
            {subscribed ? <Bell className="size-4" aria-hidden /> : <BellOff className="size-4" aria-hidden />}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{subscribed ? 'Включены' : 'Выключены'}</p>
            <p className="text-xs text-ink-secondary">
              {subscribed ? 'Задачи и отчёты придут, даже когда приложение закрыто.' : 'Браузер спросит разрешение один раз.'}
            </p>
          </div>
        </div>
        <Switch
          checked={subscribed}
          disabled={subscription.isPending || toggle.isPending}
          onChange={() => toggle.mutate()}
          label="Уведомления на этом устройстве"
        />
      </div>

      {subscribed ? (
        <>
          <PreferencesList />
          <Button
            size="sm"
            variant="secondary"
            isLoading={test.isPending}
            leftIcon={<Send className="size-4" aria-hidden />}
            onClick={() => test.mutate()}
          >
            Отправить тестовое уведомление
          </Button>
        </>
      ) : null}
    </div>
  )
}

function PreferencesList() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const preferences = useQuery({ queryKey: ['push', 'preferences'], queryFn: pushApi.preferences })
  const update = useMutation({
    mutationFn: pushApi.updatePreferences,
    onSuccess: (data) => queryClient.setQueryData(['push', 'preferences'], data),
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось сохранить настройку'), 'error'),
  })

  if (!preferences.data) return null
  const data = preferences.data

  return (
    <fieldset className="space-y-1">
      <legend className="mb-1 text-xs font-medium text-ink-secondary">Что присылать</legend>
      {(Object.keys(PREFERENCE_LABELS) as (keyof PushPreferences)[]).map((key) => (
        <div key={key} className="flex items-center justify-between gap-4 rounded-lg px-1 py-2">
          <div className="min-w-0">
            <p className="text-sm text-ink">{PREFERENCE_LABELS[key].title}</p>
            <p className="text-xs text-ink-muted">{PREFERENCE_LABELS[key].hint}</p>
          </div>
          <Switch
            checked={data[key]}
            disabled={update.isPending}
            onChange={() => update.mutate({ [key]: !data[key] })}
            label={PREFERENCE_LABELS[key].title}
          />
        </div>
      ))}
    </fieldset>
  )
}

function Switch({ checked, disabled, onChange, label }: { checked: boolean; disabled?: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-brand-500' : 'bg-border-strong',
      )}
    >
      <span
        className={cn(
          'inline-block size-5 rounded-full bg-white shadow-sm transition-transform',
          checked ? 'translate-x-[22px]' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
