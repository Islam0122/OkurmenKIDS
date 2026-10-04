import type { LeaderboardEntry } from '@/types'

import { t } from '@/i18n'
import { formatDate, formatDuration, pad2 } from '@/lib/format'

import { Icon } from '../Icon'
import './Leaderboard.css'

function initials(name: string): string {
  return name.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

export function Podium({ entries }: { entries: LeaderboardEntry[] }) {
  if (entries.length < 3) return null
  return (
    <div className="podium">
      {entries.slice(0, 3).map((entry, i) => (
        <div key={entry.id} className={`podium__item podium__item--${i + 1}`} style={{ animationDelay: `${i * 0.08}s` }}>
          {i === 0 ? <Icon name="trophy-fill" className="podium__trophy" /> : null}
          <div className="podium__rank">{pad2(i + 1)}</div>
          <div className="podium__name">{entry.name}</div>
          <div className="podium__score">{entry.percent}%</div>
          <div className="podium__meta">{formatDuration(entry.durationSeconds)}</div>
        </div>
      ))}
    </div>
  )
}

export function LeaderboardTable({ entries, highlightName, showTest = false, compact = false }: {
  entries: LeaderboardEntry[]
  highlightName?: string
  showTest?: boolean
  compact?: boolean
}) {
  const me = highlightName?.toLocaleLowerCase()
  return (
    <div className="board">
      <table>
        <thead>
          <tr>
            <th scope="col">{t.leaderboard.rank}</th>
            <th scope="col">{t.leaderboard.name}</th>
            <th scope="col">{t.leaderboard.score}</th>
            {!compact ? <th scope="col" className="hide-sm">{t.leaderboard.time}</th> : null}
            {!compact ? <th scope="col" className="hide-sm">{t.leaderboard.date}</th> : null}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr key={entry.id} className={[i < 3 && 'is-top', me && entry.name.toLocaleLowerCase() === me && 'is-me'].filter(Boolean).join(' ')}>
              <td><span className="rank">{pad2(i + 1)}</span></td>
              <td>
                <span className="board__name">
                  <span className="avatar" aria-hidden="true">{initials(entry.name)}</span>
                  <span>
                    {entry.name}
                    {showTest ? <span className="board__test">{entry.testTitle}</span> : null}
                  </span>
                </span>
              </td>
              <td><span className={`score-pill${entry.percent >= 80 ? ' score-pill--high' : ''}`}>{entry.percent}%</span></td>
              {!compact ? <td className="hide-sm board__muted">{formatDuration(entry.durationSeconds)}</td> : null}
              {!compact ? <td className="hide-sm board__muted">{formatDate(entry.finishedAt)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
