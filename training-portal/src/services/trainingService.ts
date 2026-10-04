import type { TrainingProgress, TrainingResult } from '@/types'

import { STORAGE_KEYS, storageService } from './storageService'

/*
 * Attempts on this device: the one in progress (one per test) and finished
 * results (for /result/:attemptId). Training only — nothing here touches
 * the real exam, which lives in the LMS.
 */
const MAX_RESULTS = 50

type ProgressMap = Record<string, TrainingProgress>

export const trainingService = {
  getProgress(testId: string): TrainingProgress | null {
    return storageService.read<ProgressMap>(STORAGE_KEYS.trainingProgress, {})[testId] ?? null
  },
  saveProgress(progress: TrainingProgress): void {
    const all = storageService.read<ProgressMap>(STORAGE_KEYS.trainingProgress, {})
    all[progress.testId] = progress
    storageService.write(STORAGE_KEYS.trainingProgress, all)
  },
  clearProgress(testId: string): void {
    const all = storageService.read<ProgressMap>(STORAGE_KEYS.trainingProgress, {})
    delete all[testId]
    storageService.write(STORAGE_KEYS.trainingProgress, all)
  },

  getResult(attemptId: string): TrainingResult | null {
    return storageService.read<TrainingResult[]>(STORAGE_KEYS.trainingResults, []).find((r) => r.attemptId === attemptId) ?? null
  },
  saveResult(result: TrainingResult): void {
    const all = storageService.read<TrainingResult[]>(STORAGE_KEYS.trainingResults, [])
      .filter((r) => r.attemptId !== result.attemptId)
    storageService.write(STORAGE_KEYS.trainingResults, [result, ...all].slice(0, MAX_RESULTS))
  },
  /** finished attempts of this test under this name */
  attemptsUsed(testId: string, name: string): number {
    const key = name.trim().toLocaleLowerCase()
    return storageService.read<TrainingResult[]>(STORAGE_KEYS.trainingResults, [])
      .filter((r) => r.testId === testId && r.studentName.toLocaleLowerCase() === key).length
  },
}
