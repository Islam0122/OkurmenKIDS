import type { TrainingResult } from '@/types'

import { LocalLeaderboardService } from './leaderboardService'
import { validateName } from './studentService'

function result(name: string, percent: number, seconds = 60, testId = 'py'): TrainingResult {
  return {
    attemptId: `${name}-${percent}-${seconds}`, testId, testTitle: 'Python', studentName: name,
    startedAt: 0, finishedAt: seconds * 1000, timedOut: false, total: 10, correct: percent / 10,
    incorrect: 0, skipped: 0, ungraded: 0, percent, answers: {}, outcomes: {},
  }
}

describe('LocalLeaderboardService', () => {
  it('ranks by score, then time, and keeps each name’s best result', async () => {
    const service = new LocalLeaderboardService()
    await service.submitResult(result('Айбек', 70))
    await service.submitResult(result('Мээрим', 90, 120))
    await service.submitResult(result('Бакыт', 90, 80))
    await service.submitResult(result('айбек', 60))   // worse — ignored
    await service.submitResult(result('Айбек', 100))  // better — replaces

    const board = await service.getLeaderboard('py')
    expect(board.map((e) => [e.name, e.percent])).toEqual([['Айбек', 100], ['Бакыт', 90], ['Мээрим', 90]])
  })

  it('filters by test', async () => {
    const service = new LocalLeaderboardService()
    await service.submitResult(result('A', 50, 60, 'py'))
    await service.submitResult(result('B', 50, 60, 'web'))
    expect(await service.getLeaderboard('web')).toHaveLength(1)
    expect(await service.getLeaderboard()).toHaveLength(2)
  })
})

it('validateName', () => {
  expect(validateName('  ')).toBe('required')
  expect(validateName('A')).toBe('tooShort')
  expect(validateName('A'.repeat(51))).toBe('tooLong')
  expect(validateName('  Айбек  ')).toBeNull()
})
