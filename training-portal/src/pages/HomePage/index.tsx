import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { Video } from '@/types'

import { getLeaderboard } from '@/api/leaderboard'
import { getMaterials } from '@/api/materials'
import { getTests } from '@/api/tests'
import { getVideos } from '@/api/videos'
import { Button } from '@/components/Button'
import { ExamButton } from '@/components/Button/ExamButton'
import { ErrorState } from '@/components/ErrorState'
import { Hero } from '@/components/Hero'
import { Icon } from '@/components/Icon'
import { LeaderboardTable } from '@/components/Leaderboard'
import { Loader } from '@/components/Loader'
import { CategorySections } from '@/components/CategorySections'
import { UsefulLinkCard } from '@/components/UsefulLinkCard'
import { VideoCard, VideoPlayerModal } from '@/components/VideoCard'
import { usePortal } from '@/context/PortalContext'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import './HomePage.css'

const STEP_ICONS = ['ui-checks-grid', 'person-badge', 'patch-question', 'bar-chart']
const LEADERS_PREVIEW = 5

const TESTS_SECTION_ID = 'training-tests'

export function HomePage() {
  const portal = usePortal()
  const tests = useAsync(getTests)
  const videos = useAsync(getVideos)
  const links = useAsync(getMaterials)
  const leaders = useAsync(() => getLeaderboard(undefined, LEADERS_PREVIEW))
  const [playing, setPlaying] = useState<Video | null>(null)
  // «Тренировка баштоо» stays on this page: it scrolls down to the tests.
  const handleStartTraining = () => {
    document.getElementById(TESTS_SECTION_ID)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <Hero portal={portal.data} onStart={handleStartTraining} />

      <section className="section home-tests" id={TESTS_SECTION_ID} style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="section-head">
            <div>
              <h2 className="section-title">{t.home.testsTitle}</h2>
              <p className="section-subtitle">{t.home.testsSubtitle}</p>
            </div>
          </div>
          {tests.loading ? <Loader /> : tests.error ? <ErrorState error={tests.error} onRetry={tests.reload} /> : tests.data?.length ? (
            <CategorySections tests={tests.data} />
          ) : (
            <div className="empty"><Icon name="clipboard" /><p>{t.home.noTests}</p></div>
          )}
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
            {leaders.error ? <ErrorState error={leaders.error} onRetry={leaders.reload} /> : leaders.data?.length ? (
              <LeaderboardTable entries={leaders.data} showTest compact />
            ) : leaders.loading ? <Loader /> : (
              <div className="empty home-leaders__empty"><Icon name="trophy" /><p>{t.leaderboard.empty}</p></div>
            )}
          </div>
          {links.data?.length ? (
            <div>
              <div className="section-head">
                <h2 className="section-title">{t.home.materialsTitle}</h2>
                <Link className="link-arrow" to="/materials">{t.home.materialsAll}<Icon name="arrow-right" /></Link>
              </div>
              <div className="grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 240px), 1fr))' }}>
                {links.data.slice(0, 4).map((link) => <UsefulLinkCard key={link.id} link={link} />)}
              </div>
            </div>
          ) : null}
        </div>
      </section>

      {videos.data?.length ? (
        <section className="section alt-bg">
          <div className="container">
            <div className="section-head">
              <h2 className="section-title">{t.home.videosTitle}</h2>
              <Link className="link-arrow" to="/videos">{t.home.videosAll}<Icon name="arrow-right" /></Link>
            </div>
            <div className="grid-cards">
              {videos.data.slice(0, 3).map((video) => <VideoCard key={video.id} video={video} onPlay={setPlaying} />)}
            </div>
          </div>
        </section>
      ) : null}

      {portal.data?.exam_url ? (
        <section className="section">
          <div className="container">
            <div className="exam-band">
              <div style={{ position: 'relative', zIndex: 1 }}>
                <h2>{t.home.examTitle}</h2>
                <p>{t.home.examText}</p>
              </div>
              <div className="exam-band__actions">
                <Button onClick={handleStartTraining} variant="glass" size="lg" icon="play-circle">{portal.data.start_button_label}</Button>
                <ExamButton variant="primary" size="lg" />
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <VideoPlayerModal video={playing} onClose={() => setPlaying(null)} />
    </>
  )
}
