/** GET /api/v1/training/portal/ */
export interface PortalSettings {
  hero_title: string
  hero_subtitle: string
  start_button_label: string
  exam_button_label: string
  /** empty — the exam button is hidden */
  exam_url: string
  exam_open_in_new_tab: boolean
}
