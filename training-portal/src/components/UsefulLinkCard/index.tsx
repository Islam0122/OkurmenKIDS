import type { UsefulLink } from '@/types'

import { t } from '@/i18n'
import { isExternalUrl } from '@/lib/video'

import { Button } from '../Button'
import { Icon } from '../Icon'
import './UsefulLinkCard.css'

export function UsefulLinkCard({ link }: { link: UsefulLink }) {
  const external = isExternalUrl(link.url)
  const host = external ? new URL(link.url).hostname.replace(/^www\./, '') : null
  return (
    <article className="link-card">
      <span className="link-card__icon"><Icon name={link.icon ?? 'link-45deg'} /></span>
      {link.category ? <span className="link-card__cat">{link.category}</span> : null}
      <h3 className="link-card__title">{link.title}</h3>
      {link.description ? <p className="link-card__desc">{link.description}</p> : null}
      <div className="link-card__foot">
        {external
          ? <Button href={link.url} newTab variant="outline" size="sm" iconEnd="box-arrow-up-right">{t.materials.open}</Button>
          : <Button to={link.url} variant="outline" size="sm" iconEnd="arrow-right">{t.materials.open}</Button>}
        {host ? <span className="link-card__host">{host}</span> : null}
      </div>
    </article>
  )
}
