/** Bulk copy of trainer scores between subjects — apps.scholarships.score_copy_views. */

export interface Ref {
  id: number
  name: string
}

export interface ScoreCopyPeriod {
  id: number
  title: string
  period_start: string
  period_end: string
  status: 'draft' | 'approved'
  is_draft: boolean
}

export interface ScoreCopyOptions {
  groups: (Ref & { status: string })[]
  periods: ScoreCopyPeriod[]
  subjects: Ref[]
}

export type ScoreCopyMode = 'all' | 'selected'
export type ScoreCopyConflict = 'preserve' | 'overwrite'

export interface ScoreCopyParams {
  group: number
  source_subject: number
  target_subject: number
  source_period: number
  target_period: number
  mode: ScoreCopyMode
  student_ids: number[]
  conflict: ScoreCopyConflict
  copy_comment: boolean
  source_teacher: number | null
  target_teacher: number | null
}

export type ScoreCopyAction =
  | 'create'
  | 'overwrite'
  | 'unchanged'
  | 'skip_existing'
  | 'skip_empty'
  | 'unmatched_ambiguous_source'
  | 'unmatched_no_target'
  | 'unmatched_ambiguous_target'
  | 'not_selected'

export interface ScoreValues {
  progress: number
  participation: number
  discipline: number
  understanding: number
  score: number | null
  comment?: string
}

export interface ScoreCopyRow {
  student_id: number
  student_name: string
  action: ScoreCopyAction
  reason: string
  source: ScoreValues | null
  source_teacher: Ref | null
  target: ScoreValues | null
  target_teacher: Ref | null
  target_teachers: Ref[]
  after: ScoreValues | null
}

export interface ScoreCopySummary {
  students: number
  matched: number
  copyable: number
  create: number
  overwrite: number
  unchanged: number
  skip_existing: number
  empty: number
  existing_target: number
  unmatched: number
  not_selected: number
}

export interface ScoreCopyPreview {
  summary: ScoreCopySummary
  fingerprint: string
  rows: ScoreCopyRow[]
  source_teachers: Ref[]
  target_teachers: Ref[]
  target_period_is_draft: boolean
}

export type ScoreCopyStatus = 'applied' | 'reverted' | 'partially_reverted'
export type UndoResult = '' | 'restored' | 'deleted' | 'skipped_changed' | 'skipped_missing'

export interface ScoreCopyOperation {
  id: number
  operation_id: string
  status: ScoreCopyStatus
  status_label: string
  group: { id: number | null; name: string }
  source_subject: { id: number | null; name: string }
  target_subject: { id: number | null; name: string }
  source_period: ScoreCopyPeriod | null
  target_period: ScoreCopyPeriod | null
  options: Record<string, unknown>
  copied: number
  overwritten: number
  skipped: number
  skipped_details: Partial<Record<ScoreCopyAction, number>>
  created_by: string
  created_at: string
  reverted_by: string | null
  reverted_at: string | null
  revert_details: Partial<Record<UndoResult, number>>
  can_undo: boolean
  replayed?: boolean
  items?: {
    id: number
    student_id: number
    student_name: string
    teacher: Ref | null
    action: 'created' | 'overwritten'
    before: Omit<ScoreValues, 'score'> | null
    after: Omit<ScoreValues, 'score'>
    undo_result: UndoResult
  }[]
}
