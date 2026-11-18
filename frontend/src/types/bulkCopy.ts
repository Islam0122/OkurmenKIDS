/** Bulk copy of lesson records — apps.bulk_copy. */

export type BulkCategory = 'attendance' | 'homework' | 'scores'
export type RecordAction = 'create' | 'overwrite' | 'unchanged' | 'skip_existing' | 'empty' | 'invalid'
export type StudentMatch = 'matched' | 'not_in_target_group' | 'no_source_records' | 'not_selected'

export interface BulkOptions {
  groups: { id: number; name: string; status: string }[]
  subjects: { id: number; name: string }[]
}

export interface BulkParams {
  source_group: number
  source_subject: number
  source_start: string
  source_end: string
  target_group: number
  target_subject: number
  target_start: string
  target_end: string
  categories: BulkCategory[]
  lesson_map: { source: number; target: number }[] | null
  mode: 'all' | 'selected'
  student_ids: number[]
  conflict: 'preserve' | 'overwrite'
  skip_empty: boolean
  copy_comments: boolean
}

export interface BulkLesson {
  id: number
  date: string
  start: string | null
  topic: string
  lesson_number: number | null
  status: string
  teacher: string | null
}

export interface BulkPair {
  index: number
  source: number
  target: number
  valid: boolean
  problem: string | null
  homework_pairs: number
  homework_problem: string | null
}

export type AttValues = { status: string; excuse_reason: string; comment: string }
export type HwValues = { status: string; score: number | null; comment: string; submitted_at: string | null; checked_at: string | null }

export interface BulkRecord {
  kind: 'attendance' | 'homework_result'
  student: number
  pair: number
  homework: string | null
  action: RecordAction
  problem: string | null
  source: AttValues | HwValues | null
  target: AttValues | HwValues | null
  after: AttValues | HwValues | null
}

export interface BulkSummary {
  students_matched: number
  students_unmatched: number
  students_without_source: number
  students_not_selected: number
  pairs: number
  invalid_pairs: number
  homework_problems: number
  to_copy: number
  create: number
  overwrite: number
  unchanged: number
  skip_existing: number
  empty: number
  existing_target: number
  invalid_records: number
  attendance: number
  homework_results: number
  billing_lessons: number
}

export interface BulkPreview {
  summary: BulkSummary
  fingerprint: string
  source_lessons: BulkLesson[]
  target_lessons: BulkLesson[]
  pairs: BulkPair[]
  students: { id: number; name: string; group: string | null; status: StudentMatch }[]
  records: BulkRecord[]
}

export type BulkStatus = 'queued' | 'running' | 'applied' | 'failed' | 'reverted' | 'partially_reverted'

export interface BulkOperation {
  id: number
  operation_id: string
  status: BulkStatus
  status_label: string
  source: { group: string; subject: string; start: string; end: string }
  target: { group: string; subject: string; start: string; end: string }
  categories: BulkCategory[]
  copied: number
  overwritten: number
  skipped: number
  skipped_details: Record<string, number>
  error: string
  created_by: string | null
  created_at: string
  finished_at: string | null
  reverted_by: string | null
  reverted_at: string | null
  revert_details: Record<string, number>
  can_undo: boolean
  replayed?: boolean
}
