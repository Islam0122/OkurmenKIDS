import { t } from '@/i18n'

/**
 * What makes one kind of test differ on the shared <TestScreen>: its rules
 * (checking answers, leaving, restarting), the timer thresholds and its
 * wording. The screen reads only this — a new kind of test (a mock exam, a
 * certification, a placement test) is a new config object, not a copy of
 * the screen or another `if (mode === …)` branch. The attempt lifecycle
 * stays in useAttemptRunner; the endpoints in the adapter (useTraining /
 * useExam); the backend enforces the rules whatever the page shows.
 */
export interface TestModeConfig {
  id: string
  /** Bar, left side: a «back» button (the attempt stays resumable) or a fixed badge. */
  header: { kind: 'leave' } | { kind: 'badge'; label: string }
  /** Timer colours: warning / danger under this many seconds. */
  timer: { warnAt: number; dangerAt: number }
  /** «Текшерүү» during the attempt (still only when the test shows explanations). */
  allowCheck: boolean
  /** «Answered N · left M» under the progress bar (absent: not shown). */
  counts?: (answered: number, left: number) => string
  /** The finish dialog's warning about unanswered questions (absent: not shown). */
  unansweredWarn?: (count: number) => string
  /** «Башынан баштоо» on the resumed notice. */
  allowRestart: boolean
  text: {
    resumed: string
    finish: string
    finishTitle: string
    finishText: string
    keepGoing: string
    timeUpTitle: string
    timeUpText: string
    seeResult: string
    leftCount: (count: number, max: number) => string
  }
}

export const TRAINING_MODE: TestModeConfig = {
  id: 'training',
  header: { kind: 'leave' },
  timer: { warnAt: 300, dangerAt: 60 },
  allowCheck: true,
  allowRestart: true,
  text: {
    resumed: t.training.resumed,
    finish: t.training.finish,
    finishTitle: t.training.finishTitle,
    finishText: t.training.finishText,
    keepGoing: t.training.keepGoing,
    timeUpTitle: t.training.timeUpTitle,
    timeUpText: t.training.timeUpText,
    seeResult: t.training.seeResult,
    leftCount: t.guard.leftCount,
  },
}

/** Exam: no answer checking, no way back to the site, a stricter timer (10 / 5 minutes). */
export const EXAM_MODE: TestModeConfig = {
  id: 'exam',
  header: { kind: 'badge', label: t.examMode.badge },
  timer: { warnAt: 600, dangerAt: 300 },
  allowCheck: false,
  counts: t.examMode.answeredLeft,
  unansweredWarn: t.examMode.unansweredWarn,
  allowRestart: false,
  text: {
    resumed: t.examMode.resumed,
    finish: t.examMode.finish,
    finishTitle: t.examMode.finishTitle,
    finishText: t.examMode.finishText,
    keepGoing: t.examMode.keepGoing,
    timeUpTitle: t.examMode.timeUpTitle,
    timeUpText: t.examMode.timeUpText,
    seeResult: t.examMode.seeResult,
    leftCount: t.examMode.leftCount,
  },
}

export const TEST_MODES = { training: TRAINING_MODE, exam: EXAM_MODE } as const

export type TestMode = keyof typeof TEST_MODES
