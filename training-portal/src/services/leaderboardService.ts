import type { LeaderboardEntry, TrainingResult } from '@/types'

import { newId } from '@/lib/id'

import { STORAGE_KEYS, storageService } from './storageService'

/**
 * Leaderboard source. The UI only knows this interface: today results are
 * kept on this device (LocalLeaderboardService); an ApiLeaderboardService
 * talking to the Django API can replace it without touching any component.
 */
export interface LeaderboardService {
  getLeaderboard(testId?: string): Promise<LeaderboardEntry[]>
  submitResult(result: TrainingResult): Promise<void>
}

const MAX_ENTRIES = 200

/** Best first: higher score, then faster, then earlier. */
export function rankEntries(entries: LeaderboardEntry[]): LeaderboardEntry[] {
  return [...entries].sort(
    (a, b) => b.percent - a.percent || a.durationSeconds - b.durationSeconds || a.finishedAt - b.finishedAt,
  )
}

export function entryFromResult(result: TrainingResult): LeaderboardEntry {
  return {
    id: newId(),
    name: result.studentName,
    testId: result.testId,
    testTitle: result.testTitle,
    percent: result.percent,
    correct: result.correct,
    graded: result.total - result.ungraded,
    durationSeconds: Math.round((result.finishedAt - result.startedAt) / 1000),
    finishedAt: result.finishedAt,
  }
}

export class LocalLeaderboardService implements LeaderboardService {
  async getLeaderboard(testId?: string): Promise<LeaderboardEntry[]> {
    const all = storageService.read<LeaderboardEntry[]>(STORAGE_KEYS.leaderboard, [])
    return rankEntries(testId ? all.filter((e) => e.testId === testId) : all)
  }

  /** Keeps each name's best result per test. */
  async submitResult(result: TrainingResult): Promise<void> {
    const entry = entryFromResult(result)
    const all = storageService.read<LeaderboardEntry[]>(STORAGE_KEYS.leaderboard, [])
    const sameName = (e: LeaderboardEntry) =>
      e.testId === entry.testId && e.name.toLocaleLowerCase() === entry.name.toLocaleLowerCase()
    const previous = all.find(sameName)
    if (previous && rankEntries([previous, entry])[0] === previous) return
    const next = rankEntries([entry, ...all.filter((e) => !sameName(e))]).slice(0, MAX_ENTRIES)
    storageService.write(STORAGE_KEYS.leaderboard, next)
  }
}

export const leaderboardService: LeaderboardService = new LocalLeaderboardService()
