import { Link } from 'react-router-dom'

import { usePortal } from '@/context/PortalContext'
import { t } from '@/i18n'

import { Brand } from '../Header'
import { Icon } from '../Icon'
import './Footer.css'

export function Footer() {
  const { data: portal } = usePortal()
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__top">
          <div>
            <Brand />
            <p className="footer__about">{t.common.footer}</p>
          </div>
          <nav className="footer__links" aria-label="Шилтемелер">
            <Link to="/training"><Icon name="ui-checks-grid" />{t.nav.training}</Link>
            <Link to="/leaderboard"><Icon name="trophy" />{t.nav.leaderboard}</Link>
            <Link to="/videos"><Icon name="camera-video" />{t.nav.videos}</Link>
            <Link to="/materials"><Icon name="journal-bookmark" />{t.nav.materials}</Link>
            {portal?.exam_url ? (
              <a href={portal.exam_url} {...(portal.exam_open_in_new_tab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
                <Icon name="mortarboard" />{portal.exam_button_label}
              </a>
            ) : null}
          </nav>
        </div>
        <div className="footer__bottom">
          <span>© {new Date().getFullYear()} Okurmen Kids</span>
          <span className="footer__note"><Icon name="info-circle" />{t.common.trainingOnly}</span>
        </div>
      </div>
    </footer>
  )
}
