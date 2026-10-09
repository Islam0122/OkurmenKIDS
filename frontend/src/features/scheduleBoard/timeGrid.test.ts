import { describe, expect, it } from 'vitest'

import { assignLanes, formatDuration, fromMinutes, hourMarks, place, slotAt, toMinutes } from './timeGrid'

describe('schedule time grid', () => {
  it('spans 08:00 to 24:00 by the hour', () => {
    const marks = hourMarks()
    expect(marks[0]).toBe('08:00')
    expect(marks.at(-1)).toBe('24:00')
    expect(marks).toHaveLength(17)
  })

  it('places lessons by their real start and end, any duration', () => {
    expect(place('08:00', '09:00')).toEqual({ top: 0, height: 60, clippedStart: false, clippedEnd: false })
    expect(place('14:00', '15:30')).toMatchObject({ top: 360, height: 90 })
    expect(place('10:00', '13:15')).toMatchObject({ top: 120, height: 195 })
    expect(place('22:30', '00:00')).toMatchObject({ top: 870, height: 90 })
    expect(place('07:00', '09:00')).toMatchObject({ top: 0, height: 60, clippedStart: true })
  })

  it('puts overlapping lessons side by side, touching ones in one lane', () => {
    const lanes = assignLanes([
      { id: 1, start: '14:00', end: '15:30' },
      { id: 2, start: '15:00', end: '16:00' },
      { id: 3, start: '16:00', end: '17:00' },
      { id: 4, start: '18:00', end: '19:00' },
    ])
    const by = Object.fromEntries(lanes.map((l) => [l.item.id, l]))
    expect([by[1].lane, by[2].lane]).toEqual([0, 1])
    expect(by[1].lanes).toBe(2)
    expect(by[3]).toMatchObject({ lane: 0, lanes: 1 })
    expect(by[4]).toMatchObject({ lane: 0, lanes: 1 })
  })

  it('formats durations and minutes', () => {
    expect(formatDuration(90)).toBe('1 ч 30 мин')
    expect(formatDuration(45)).toBe('45 мин')
    expect(formatDuration(120)).toBe('2 ч')
    expect(toMinutes('24:00')).toBe(1440)
    expect(fromMinutes(1440)).toBe('24:00')
  })

  it('snaps a click to a 30-minute slot inside the day', () => {
    expect(slotAt(0)).toBe(8 * 60)
    expect(slotAt(95)).toBe(9 * 60 + 30)
    expect(slotAt(10_000)).toBe(23 * 60 + 30)
  })
})
