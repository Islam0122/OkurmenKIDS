import { useEffect, useState, type FormEvent } from 'react'
import { Copy, MapPin, MapPinned, PencilLine, Plus, Power, Printer } from 'lucide-react'
import { Navigate } from 'react-router-dom'

import { staffAttendanceApi } from '@/api/staffAttendance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useAttendanceMeta, useOfficeLocations, useSaveLocation } from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import type { OfficeLocation, OfficeLocationInput } from '@/types/staffAttendance'

/** /admin/attendance/locations — офисы, их геозоны и постоянные QR-коды. */
export function LocationsPage() {
  const meta = useAttendanceMeta()
  if (meta.isPending) return <LoadingState label="Проверяем доступ…" />
  if (meta.isError || !meta.data.access.can_manage) return <Navigate to="/attendance" replace />
  return <Locations />
}

function Locations() {
  const locations = useOfficeLocations()
  const [editing, setEditing] = useState<OfficeLocation | 'new' | null>(null)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Офисы и QR-коды"
        description="Постоянный QR-код офиса и геозона, внутри которой принимается отметка"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')}>Новый офис</Button>}
      />
      <p className="rounded-xl bg-info-soft px-4 py-3 text-sm text-info">
        QR-код содержит только ссылку на страницу отметки и код офиса — без паролей и данных сотрудников. Он постоянный,
        поэтому его можно сфотографировать: отметка дополнительно требует входа в LMS, свежей геолокации в радиусе офиса
        и проверки сервером. Подмену координат браузера это полностью не исключает.
      </p>
      {locations.isPending ? (
        <LoadingState />
      ) : locations.isError ? (
        <ErrorState message={extractErrorMessage(locations.error)} onRetry={() => void locations.refetch()} />
      ) : locations.data.length === 0 ? (
        <EmptyState icon={MapPinned} title="Офисов пока нет" description="Создайте офис, чтобы получить QR-код." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {locations.data.map((location) => <LocationCard key={location.id} location={location} onEdit={() => setEditing(location)} />)}
        </div>
      )}
      <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Новый офис' : 'Изменить офис'}>
        {editing !== null ? <LocationForm location={editing === 'new' ? null : editing} onClose={() => setEditing(null)} /> : null}
      </Modal>
    </div>
  )
}

function useQrImage(location: OfficeLocation): { src: string | null; svg: string | null } {
  const [svg, setSvg] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    staffAttendanceApi.locationQrSvg(location.id).then((text) => alive && setSvg(text)).catch(() => alive && setSvg(null))
    return () => {
      alive = false
    }
  }, [location.id, location.qr_url])
  const src = svg ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}` : null
  return { src, svg }
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)
}

function LocationCard({ location, onEdit }: { location: OfficeLocation; onEdit: () => void }) {
  const { showToast } = useToast()
  const save = useSaveLocation()
  const qr = useQrImage(location)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(location.qr_url)
      showToast('Ссылка скопирована', 'success')
    } catch {
      showToast('Не удалось скопировать — выделите ссылку вручную', 'error')
    }
  }

  const print = () => {
    if (!qr.src) return
    const win = window.open('', '_blank', 'width=720,height=900')
    if (!win) {
      showToast('Браузер заблокировал окно печати', 'error')
      return
    }
    win.document.write(`<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>QR — ${escapeHtml(location.name)}</title>
      <style>body{font-family:system-ui,sans-serif;text-align:center;padding:40px;color:#202622}img{width:420px;height:420px}
      h1{font-size:28px;margin:0 0 8px}p{font-size:16px;color:#555;margin:6px 0}</style></head><body>
      <h1>Отметка прихода и ухода</h1><p>${escapeHtml(location.name)}</p>
      <img src="${qr.src}" alt="QR-код офиса" />
      <p>Откройте камеру телефона или кнопку «Сканировать QR» в LMS OkurmenKIDS.</p>
      <p>Нужен вход в LMS и разрешение на геолокацию.</p></body></html>`)
    win.document.close()
    win.focus()
    win.setTimeout(() => win.print(), 300)
  }

  const toggle = async () => {
    try {
      await save.mutateAsync({ id: location.id, payload: { is_active: !location.is_active } })
      showToast(location.is_active ? 'Офис отключён — отметки в нём не принимаются' : 'Офис активирован', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }

  return (
    <Card>
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex size-44 shrink-0 items-center justify-center self-center rounded-xl border border-border bg-white p-2">
          {qr.src ? <img src={qr.src} alt={`QR-код офиса ${location.name}`} className="size-full" /> : <LoadingState label="QR…" />}
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="section-title">{location.name}</h2>
            <Badge tone={location.is_active ? 'success' : 'muted'}>{location.is_active ? 'Активен' : 'Отключён'}</Badge>
          </div>
          {location.address ? <p className="text-sm text-ink-secondary">{location.address}</p> : null}
          <p className="flex items-center gap-1 text-sm tabular-nums text-ink-secondary">
            <MapPin className="size-4" aria-hidden />
            {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)} · радиус {location.radius_m} м
          </p>
          <a
            className="text-sm text-brand-700 hover:underline"
            href={`https://www.openstreetmap.org/?mlat=${location.latitude}&mlon=${location.longitude}#map=18/${location.latitude}/${location.longitude}`}
            target="_blank"
            rel="noreferrer"
          >
            Открыть на карте
          </a>
          <p className="break-all rounded-lg bg-surface-muted px-2 py-1.5 font-mono text-xs text-ink-secondary">{location.qr_url}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" variant="secondary" leftIcon={<Printer className="size-4" aria-hidden />} onClick={print} disabled={!qr.src}>Печать</Button>
            <Button size="sm" variant="secondary" leftIcon={<Copy className="size-4" aria-hidden />} onClick={() => void copy()}>Копировать URL</Button>
            <Button size="sm" variant="ghost" leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={onEdit}>Изменить</Button>
            <Button size="sm" variant="ghost" leftIcon={<Power className="size-4" aria-hidden />} isLoading={save.isPending} onClick={() => void toggle()}>
              {location.is_active ? 'Деактивировать' : 'Активировать'}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}

function LocationForm({ location, onClose }: { location: OfficeLocation | null; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useSaveLocation()
  const [form, setForm] = useState({
    name: location?.name ?? '',
    address: location?.address ?? '',
    latitude: location ? String(location.latitude) : '',
    longitude: location ? String(location.longitude) : '',
    radius_m: location ? String(location.radius_m) : '100',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const payload: OfficeLocationInput = {
      name: form.name.trim(),
      address: form.address.trim(),
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      radius_m: Number(form.radius_m),
      is_active: location?.is_active ?? true,
    }
    if (!payload.name || Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude) || !payload.radius_m) {
      setError('Заполните название, координаты и радиус.')
      return
    }
    try {
      await save.mutateAsync({ id: location?.id, payload })
      showToast('Офис сохранён', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label htmlFor="loc-name" className="mb-1.5 block field-label">Название *</label>
        <Input id="loc-name" value={form.name} onChange={set('name')} required maxLength={150} />
      </div>
      <div>
        <label htmlFor="loc-address" className="mb-1.5 block field-label">Адрес</label>
        <Input id="loc-address" value={form.address} onChange={set('address')} maxLength={255} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="loc-lat" className="mb-1.5 block field-label">Широта *</label>
          <Input id="loc-lat" inputMode="decimal" value={form.latitude} onChange={set('latitude')} required />
        </div>
        <div>
          <label htmlFor="loc-lon" className="mb-1.5 block field-label">Долгота *</label>
          <Input id="loc-lon" inputMode="decimal" value={form.longitude} onChange={set('longitude')} required />
        </div>
        <div>
          <label htmlFor="loc-radius" className="mb-1.5 block field-label">Радиус, м *</label>
          <Input id="loc-radius" type="number" min={10} max={5000} value={form.radius_m} onChange={set('radius_m')} required />
        </div>
      </div>
      {location ? <p className="text-xs text-ink-muted">Код офиса и QR-код не меняются при редактировании — распечатанный QR остаётся рабочим.</p> : null}
      {error ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
        <Button type="submit" isLoading={save.isPending}>Сохранить</Button>
      </div>
    </form>
  )
}
