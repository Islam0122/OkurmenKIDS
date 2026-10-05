import { EXAM_MODE, TEST_MODES, TRAINING_MODE, type TestModeConfig } from './modes'

describe('test mode configs', () => {
  it('keeps the exam rules apart from training', () => {
    expect(EXAM_MODE.allowCheck).toBe(false)
    expect(EXAM_MODE.allowRestart).toBe(false)
    expect(EXAM_MODE.header).toEqual({ label: 'Экзамен', icon: 'clipboard-check', canLeave: false })
    expect(EXAM_MODE.timer).toEqual({ warnAt: 600, dangerAt: 300 })
    expect(TRAINING_MODE.allowCheck).toBe(true)
    expect(TRAINING_MODE.header).toEqual({ label: 'Тренировка', icon: 'mortarboard', canLeave: true })
    expect(TRAINING_MODE.counts).toBeUndefined()
    expect(TEST_MODES).toEqual({ training: TRAINING_MODE, exam: EXAM_MODE })
  })

  it('has no training wording in the exam texts', () => {
    const texts = Object.values(EXAM_MODE.text).map((v) => (typeof v === 'function' ? v(1, 3) : v))
    expect(texts.join(' ')).not.toMatch(/тренировк/i)
  })

  it('a new kind of test is a config, not a new screen', () => {
    const mock: TestModeConfig = { ...EXAM_MODE, id: 'mock', header: { label: 'Сынак экзамен', icon: 'clipboard-check', canLeave: false }, allowCheck: true }
    expect(mock.timer).toBe(EXAM_MODE.timer)
  })
})
