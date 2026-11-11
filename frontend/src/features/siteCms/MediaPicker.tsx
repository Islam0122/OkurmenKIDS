import { useState } from 'react'
import { ImagePlus } from 'lucide-react'

import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { LoadingState } from '@/components/ui/LoadingState'

import { toList, useSiteList } from './api'

export interface PickedAsset {
  url: string
  title: string
  alt: string
}

/** Выбор изображения из медиатеки для текста (или загрузка в «Медиатеке»). */
export function MediaPicker({ isOpen, onClose, onPick }: { isOpen: boolean; onClose: () => void; onPick: (asset: PickedAsset) => void }) {
  const [search, setSearch] = useState('')
  const query = useSiteList('media', { kind: 'image', search: search || undefined, page_size: 60 })
  const { rows } = toList(query.data)
  if (!isOpen) return null
  return (
    <Modal isOpen onClose={onClose} title="Изображение из медиатеки" size="lg" icon={<ImagePlus className="size-5" aria-hidden />}>
      <div className="space-y-3">
        <SearchInput value={search} onChange={setSearch} placeholder="Поиск по названию" />
        {query.isPending ? <LoadingState /> : rows.length ? (
          <ul className="grid max-h-[60vh] grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-4">
            {rows.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => onPick({ url: String(row.url), title: String(row.title), alt: String(row.alt ?? '') })}
                  className="block w-full overflow-hidden rounded-lg border border-border text-left hover:border-brand-500">
                  <img src={String(row.url)} alt={String(row.alt || row.title)} className="aspect-square w-full object-cover" loading="lazy" />
                  <span className="block truncate px-2 py-1 text-xs">{String(row.title)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="py-8 text-center text-sm text-ink-muted">Изображений нет. Загрузите их в разделе «Медиатека».</p>}
      </div>
    </Modal>
  )
}
