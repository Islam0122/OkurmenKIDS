import { useState } from 'react'

import { Button } from '@/components/Button'
import { Icon } from '@/components/Icon'
import { LeaderboardTable, Podium } from '@/components/Leaderboard'
import { Loader } from '@/components/Loader'
import { siteConfig } from '@/config/site'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { contentService } from '@/services/contentService'
import { leaderboardService } from '@/services/leaderboardService'
import { studentService } from '@/services/studentService'

export function LeaderboardPage() {
  const tests = useAsync(() => contentService.getTests())
  const [testId, setTestId] = useState<string | undefined>(undefined)
  const board = useAsync(() => leaderboardService.getLeaderboard(testId), [testId])
  const entries = board.data ?? []

  return (
    <div className="container" style={{ paddingBottom: 80 }}>
      <header className="page-head">
        <span className="eyebrow"><Icon name="trophy" />{t.nav.leaderboard}</span>
        <h1 className="page-title" style={{ marginTop: 14 }}>{t.leaderboard.title}</h1>
        <p className="section-subtitle">{t.leaderboard.subtitle}</p>
      </header>

      <div className="chips" role="tablist" aria-label="Тесттер">
        <button type="button" role="tab" aria-selected={!testId} className={`chip${!testId ? ' is-active' : ''}`} onClick={() => setTestId(undefined)}>{t.leaderboard.all}</button>
        {(tests.data ?? []).map((test) => (
          <button key={test.id} type="button" role="tab" aria-selected={testId === test.id} className={`chip${testId === test.id ? ' is-active' : ''}`} onClick={() => setTestId(test.id)}>
            {test.title}
          </button>
        ))}
      </div>

      {board.loading ? <Loader /> : entries.length ? (
        <>
          <Podium entries={entries} />
          <LeaderboardTable entries={entries} highlightName={studentService.getName()} showTest={!testId} />
          <p className="muted" style={{ marginTop: 14, fontSize: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
            <Icon name="info-circle" />{t.leaderboard.note}
          </p>
        </>
      ) : (
        <div className="empty">
          <Icon name="trophy" />
          <p>{t.leaderboard.empty}</p>
          <div style={{ marginTop: 20 }}><Button to={`/training/${testId ?? siteConfig.defaultTestId}`} icon="play-circle">{t.test.start}</Button></div>
        </div>
      )}
    </div>
  )
}
