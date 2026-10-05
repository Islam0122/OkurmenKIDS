import type { PortalSettings } from '@/types'

import { t } from '@/i18n'

import { Button } from '../Button'
import { ExamButton } from '../Button/ExamButton'
import { Icon } from '../Icon'
import './Hero.css'

/** Texts come from the backend (portal settings); the visual is abstract. */
export function Hero({ portal, onStart }: { portal: PortalSettings | undefined; onStart: () => void }) {
  const title = portal?.hero_title ?? ''
  const [first, ...rest] = title.split(' ')
  return (
    <section className="hero">
      <div className="container hero__grid">
        <div className="reveal">
          <span className="eyebrow"><Icon name="stars" />{t.hero.eyebrow}</span>
          <h1 className="hero__title">{first ? <><em>{first}</em> {rest.join(' ')}</> : <span className="hero__title-skeleton" />}</h1>
          {portal?.hero_subtitle ? <p className="hero__subtitle">{portal.hero_subtitle}</p> : null}
          <div className="hero__actions">
            <Button variant="test" onClick={onStart} size="lg" icon="play-circle">{portal?.start_button_label ?? t.hero.start}</Button>
            <ExamButton variant="test-outline" size="lg" />
          </div>
          <ul className="hero__perks">
            {t.hero.perks.map((perk) => <li key={perk}><Icon name="check-circle-fill" />{perk}</li>)}
          </ul>
        </div>

        <div className="hero-visual reveal" style={{ animationDelay: '.15s' }} aria-hidden="true">
          <div className="hero-visual__ring" />
          <div className="hero-card">
            <div className="hero-card__top">
              <span className="hero-card__label"><Icon name="ui-checks-grid" />{t.hero.cardLabel}</span>
              <span className="hero-card__timer"><Icon name="clock" /></span>
            </div>
            <div className="hero-card__bar"><span /></div>
            <div className="hero-card__line" />
            <div className="hero-card__line hero-card__line--short" />
            <div className="hero-card__opt is-right"><i className="dot" /><span className="hero-card__ph" /><Icon name="check-circle-fill" /></div>
            <div className="hero-card__opt"><i className="dot" /><span className="hero-card__ph hero-card__ph--md" /></div>
            <div className="hero-card__opt"><i className="dot" /><span className="hero-card__ph hero-card__ph--sm" /></div>
          </div>
          <div className="floaty floaty--score">
            <span className="floaty__icon"><Icon name="bar-chart-fill" /></span>
            <span>{t.result.title}</span>
          </div>
          <div className="floaty floaty--rank">
            <span className="floaty__icon"><Icon name="trophy-fill" /></span>
            <span>{t.nav.leaderboard}</span>
          </div>
        </div>
      </div>
    </section>
  )
}
