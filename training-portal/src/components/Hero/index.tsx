import { siteConfig } from '@/config/site'
import { t } from '@/i18n'

import { Button } from '../Button'
import { ExamButton } from '../Button/ExamButton'
import { Icon } from '../Icon'
import './Hero.css'

export function Hero() {
  const [first, ...rest] = t.hero.title.split(' ')
  return (
    <section className="hero">
      <div className="container hero__grid">
        <div className="reveal">
          <span className="eyebrow"><Icon name="stars" />{t.hero.eyebrow}</span>
          <h1 className="hero__title"><em>{first}</em> {rest.join(' ')}</h1>
          <p className="hero__subtitle">{t.hero.subtitle}</p>
          <div className="hero__actions">
            <Button to={`/training/${siteConfig.defaultTestId}`} size="lg" icon="play-circle">{t.hero.start}</Button>
            <ExamButton variant="outline" size="lg" label={t.hero.exam} />
          </div>
          <ul className="hero__perks">
            {t.hero.perks.map((perk) => <li key={perk}><Icon name="check-circle-fill" />{perk}</li>)}
          </ul>
        </div>

        <div className="hero-visual reveal" style={{ animationDelay: '.15s' }} aria-hidden="true">
          <div className="hero-visual__ring" />
          <div className="mock">
            <div className="mock__top">
              <span className="mock__label"><Icon name="ui-checks-grid" />{t.hero.cardQuestion}</span>
              <span className="mock__timer"><Icon name="clock" />24:18</span>
            </div>
            <div className="mock__bar"><span /></div>
            <p className="mock__q">print(&quot;Hi&quot; * 3) эмнени чыгарат?</p>
            <div className="mock__opt is-right"><i className="dot" />HiHiHi</div>
            <div className="mock__opt"><i className="dot" />Hi3</div>
            <div className="mock__opt"><i className="dot" />Hi Hi Hi</div>
            <div className="mock__feedback"><Icon name="check-circle-fill" />{t.hero.cardCorrect}</div>
          </div>
          <div className="floaty floaty--score">
            <span className="floaty__icon"><Icon name="bar-chart-fill" /></span>
            <span>87%<small>{t.result.score}</small></span>
          </div>
          <div className="floaty floaty--rank">
            <span className="floaty__icon"><Icon name="trophy-fill" /></span>
            <span>01<small>{t.nav.leaderboard}</small></span>
          </div>
        </div>
      </div>
    </section>
  )
}
