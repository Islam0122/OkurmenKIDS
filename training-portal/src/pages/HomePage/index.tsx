import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { Video } from '@/types'

import { ExamButton } from '@/components/Button/ExamButton'
import { Button } from '@/components/Button'
import { Hero } from '@/components/Hero'
import { Icon } from '@/components/Icon'
import { LeaderboardTable } from '@/components/Leaderboard'
import { TestCard } from '@/components/TestCard'
import { UsefulLinkCard } from '@/components/UsefulLinkCard'
import { VideoCard, VideoPlayerModal } from '@/components/VideoCard'
import { siteConfig } from '@/config/site'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { contentService } from '@/services/contentService'
import { leaderboardService } from '@/services/leaderboardService'
import { trainingService } from '@/services/trainingService'
import './HomePage.css'

const STEP_ICONS = ['ui-checks-grid', 'person-badge', 'patch-question', 'bar-chart']

export function HomePage() {
  const tests = useAsync(() => contentService.getTests())
  const videos = useAsync(() => contentService.getVideos())
  const links = useAsync(() => contentService.getLinks())
  const leaders = useAsync(() => leaderboardService.getLeaderboard())
  const [playing, setPlaying] = useState<Video | null>(null)

  return (
    <>
      <Hero />

      <section className="section" id="tests" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="section-head">
            <div>
              <h2 className="section-title">{t.home.testsTitle}</h2>
              <p className="section-subtitle">{t.home.testsSubtitle}</p>
            </div>
          </div>
          <div className="grid-cards">
            {(tests.data ?? []).map((test) => (
              <TestCard key={test.id} test={test} inProgress={Boolean(trainingService.getProgress(test.id))} />
            ))}
          </div>
        </div>
      </section>

      <section className="section alt-bg">
        <div className="container">
          <div className="section-head"><h2 className="section-title">{t.home.stepsTitle}</h2></div>
          <ol className="steps" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {t.home.steps.map((step, i) => (
              <li key={step.title} className="step reveal" style={{ animationDelay: `${i * 0.08}s` }}>
                <span className="step__num">{String(i + 1).padStart(2, '0')}</span>
                <Icon name={STEP_ICONS[i]} className="step__icon" />
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="container home-split">
          <div>
            <div className="section-head">
              <h2 className="section-title">{t.home.leadersTitle}</h2>
              <Link className="link-arrow" to="/leaderboard">{t.home.leadersAll}<Icon name="arrow-right" /></Link>
            </div>
            {leaders.data?.length ? (
              <LeaderboardTable entries={leaders.data.slice(0, siteConfig.leaderboardPreviewSize)} showTest compact />
            ) : (
              <div className="empty home-leaders__empty"><Icon name="trophy" /><p>{t.leaderboard.empty}</p></div>
            )}
          </div>
          <div>
            <div className="section-head">
              <h2 className="section-title">{t.home.materialsTitle}</h2>
              <Link className="link-arrow" to="/materials">{t.home.materialsAll}<Icon name="arrow-right" /></Link>
            </div>
            <div className="grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 240px), 1fr))' }}>
              {(links.data ?? []).slice(0, 4).map((link) => <UsefulLinkCard key={link.id} link={link} />)}
            </div>
          </div>
        </div>
      </section>

      <section className="section alt-bg">
        <div className="container">
          <div className="section-head">
            <h2 className="section-title">{t.home.videosTitle}</h2>
            <Link className="link-arrow" to="/videos">{t.home.videosAll}<Icon name="arrow-right" /></Link>
          </div>
          <div className="grid-cards">
            {(videos.data ?? []).slice(0, 3).map((video) => <VideoCard key={video.id} video={video} onPlay={setPlaying} />)}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="exam-band">
            <div style={{ position: 'relative', zIndex: 1 }}>
              <h2>{t.home.examTitle}</h2>
              <p>{t.home.examText}</p>
            </div>
            <div className="exam-band__actions">
              <Button to={`/training/${siteConfig.defaultTestId}`} variant="glass" size="lg" icon="play-circle">{t.hero.start}</Button>
              <ExamButton variant="primary" size="lg" />
            </div>
          </div>
        </div>
      </section>

      <VideoPlayerModal video={playing} onClose={() => setPlaying(null)} />
    </>
  )
}
