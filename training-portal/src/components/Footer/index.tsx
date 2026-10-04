import { Link } from 'react-router-dom'

import { siteConfig } from '@/config/site'
import { t } from '@/i18n'

import { Brand } from '../Header'
import { Icon } from '../Icon'
import './Footer.css'

export function Footer() {
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
            <a href={siteConfig.examUrl} {...(siteConfig.openInNewTab ? { target: "_blank", rel: "noopener noreferrer" } : {})}><Icon name="mortarboard" />{t.nav.exam}</a>
          </nav>
        </div>
        <div className="footer__bottom">
          <span>© {new Date().getFullYear()} {siteConfig.brand}</span>
          <span className="footer__note"><Icon name="info-circle" />{t.common.trainingOnly}</span>
        </div>
      </div>
    </footer>
  )
}
