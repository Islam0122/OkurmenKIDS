import { t } from '@/i18n'

export function Loader() {
  return (
    <div className="container" style={{ padding: '96px 16px', textAlign: 'center', color: 'var(--text-3)', fontWeight: 700 }} role="status">
      {t.common.loading}
    </div>
  )
}
