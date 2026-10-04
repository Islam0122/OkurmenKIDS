import { useState } from 'react'

import { getMaterials } from '@/api/materials'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { UsefulLinkCard } from '@/components/UsefulLinkCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'

export function MaterialsPage() {
  const { data, loading, error, reload } = useAsync(getMaterials)
  const [category, setCategory] = useState<string | null>(null)
  const links = data ?? []
  const categories = [...new Set(links.map((l) => l.category).filter(Boolean))] as string[]
  const shown = category ? links.filter((l) => l.category === category) : links

  return (
    <div className="container" style={{ paddingBottom: 80 }}>
      <header className="page-head">
        <span className="eyebrow"><Icon name="journal-bookmark" />{t.nav.materials}</span>
        <h1 className="page-title" style={{ marginTop: 14 }}>{t.materials.title}</h1>
        <p className="section-subtitle">{t.materials.subtitle}</p>
      </header>
      {categories.length > 1 ? (
        <div className="chips">
          <button type="button" className={`chip${!category ? ' is-active' : ''}`} onClick={() => setCategory(null)}>{t.materials.all}</button>
          {categories.map((c) => (
            <button key={c} type="button" className={`chip${category === c ? ' is-active' : ''}`} onClick={() => setCategory(c)}>{c}</button>
          ))}
        </div>
      ) : null}
      {loading ? <Loader /> : error ? <ErrorState error={error} onRetry={reload} /> : shown.length ? (
        <div className="grid-cards">{shown.map((link) => <UsefulLinkCard key={link.id} link={link} />)}</div>
      ) : (
        <div className="empty"><Icon name="journal-x" /><p>{t.materials.empty}</p></div>
      )}
    </div>
  )
}
