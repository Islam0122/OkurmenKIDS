import type { Test, UsefulLink, Video } from '@/types'

import { usefulLinks } from '@/data/links'
import { trainingTests } from '@/data/tests'
import { videos } from '@/data/videos'

/*
 * Content source for the pages. Async on purpose: today it reads the static
 * data in src/data, later it fetches the same shapes from the Django API —
 * the pages don't change. Only published items are returned, in order.
 */
const byOrder = <T extends { order: number }>(items: T[]) => [...items].sort((a, b) => a.order - b.order)

export const contentService = {
  async getTests(): Promise<Test[]> {
    return trainingTests.filter((t) => t.published)
  },
  async getTest(id: string): Promise<Test | null> {
    return trainingTests.find((t) => t.id === id && t.published) ?? null
  },
  async getVideos(): Promise<Video[]> {
    return byOrder(videos.filter((v) => v.published))
  },
  async getLinks(): Promise<UsefulLink[]> {
    return byOrder(usefulLinks.filter((l) => l.published))
  },
}
