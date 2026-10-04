import { useState } from 'react'

import { getLeaderboard } from '@/api/leaderboard'
import { getTests } from '@/api/tests'
import { Button } from '@/components/Button'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { LeaderboardTable, Podium } from '@/components/Leaderboard'
import { Loader } from '@/components/Loader'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { storageService } from '@/services/storageService'

export function LeaderboardPage() {
  const tests = useAsync(getTests)
  const [testId, setTestId] = useState<string | undefined>(undefined)
  const board = useAsync(() => getLeaderboard(testId), [testId])
  const entries = board.data ?? []

  return (
    <div className="container" style={{ paddingBottom: 80 }}>
      <header className="page-head">
        <span className="eyebrow"><Icon name="trophy" />{t.nav.leaderboard}</span>
        <h1 className="page-title" style={{ marginTop: 14 }}>{t.leaderboard.title}</h1>
        <p className="section-subtitle">{t.leaderboard.subtitle}</p>
      </header>

      {tests.data && tests.data.length > 1 ? (
        <div className="chips" role="tablist" aria-label={t.home.testsTitle}>
          <button type="button" role="tab" aria-selected={!testId} className={`chip${!testId ? ' is-active' : ''}`} onClick={() => setTestId(undefined)}>{t.leaderboard.all}</button>
          {tests.data.map((test) => (
            <button key={test.id} type="button" role="tab" aria-selected={testId === test.id} className={`chip${testId === test.id ? ' is-active' : ''}`} onClick={() => setTestId(test.id)}>
              {test.title}
            </button>
          ))}
        </div>
      ) : null}

      {board.loading ? <Loader /> : board.error ? <ErrorState error={board.error} onRetry={board.reload} /> : entries.length ? (
        <>
          <Podium entries={entries} />
          <LeaderboardTable entries={entries} highlightName={storageService.getStudentName()} showTest={!testId} />
          <p className="muted" style={{ marginTop: 14, fontSize: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
            <Icon name="info-circle" />{t.leaderboard.note}
          </p>
        </>
      ) : (
        <div className="empty">
          <Icon name="trophy" />
          <p>{t.leaderboard.empty}</p>
          <div style={{ marginTop: 20 }}><Button to={testId ? `/training/${testId}` : '/training'} icon="play-circle">{t.test.start}</Button></div>
        </div>
      )}
    </div>
  )
}
