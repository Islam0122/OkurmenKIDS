/** GET /api/v1/training/links/ */
export interface UsefulLink {
  id: number
  title: string
  description: string
  url: string
  category: string
  /** Bootstrap Icons name without «bi-» */
  icon: string
  order: number
}
