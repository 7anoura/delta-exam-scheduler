export interface Period {
  id: string
  name: string
  start_date: string
  end_date: string
  status: string
  head_of_control_staff_id: string | null
}

export interface Staff {
  staff_id: string
  academic_rank: string
  can_invigilate: boolean
  can_chair: boolean
}

export interface ExamSession {
  date: string
  start: string
  end: string
  source_ref: string
}

export interface Exam {
  code: string
  title: string
  sessions: ExamSession[]
}

export interface RoomSitting {
  sitting_id: string
  date: string
  start: string
  end: string
  room_code: string
  course_codes: string[]
  session_refs: string[]
}

export interface Snapshot {
  label: string
  exam_period_id: string
  head_of_control_selected: boolean
  verified_against_live_database: boolean
  staff: Staff[]
  exams: Exam[]
  room_sittings: RoomSitting[]
  assumptions: {
    invigilators_per_room: number
    min_break_minutes: number
    preparation_minutes: number
    max_daily_invigilation_minutes: number | null
    allow_parallel_chair_assignments: boolean
  }
}

export interface Shortage {
  date: string
  time: string
  simultaneous_courses: number
  available_chairs_at_start: number
  missing_chairs_lower_bound?: number
  course_codes?: string[]
}

export interface Audit {
  status: string
  counts: {
    staff_total_active: number
    eligible_invigilators: number
    eligible_chairs: number
    courses: number
    exam_sessions: number
    physical_room_sittings: number
    required_invigilation_assignments: number
    time_points_evaluated: number
  }
  peak_required_invigilators: number
  chair_shortages: Shortage[]
  invigilator_shortages: unknown[]
  double_booked_rooms: unknown[]
  issues: string[]
  note: string
}

export interface Comparison {
  matches: boolean
  sections: Record<string, { matches: boolean; expected: number; live: number }>
  rule_matches: Record<string, boolean>
  note: string
}


export interface DraftAssignment {
  staff_id: string
  sitting_id: string
  date: string
  start: string
  end: string
  room_code: string
  minutes: number
  course_codes: string
}
export interface PreviewResult {
  mode: 'preview_only'
  persisted: false
  published: false
  generated_at: string
  period_id: string
  invigilator: { status: string; reason?: string; counts?: Record<string, number> }
  chair: { status: string; reason?: string; shortages?: Array<{ date: string; time: string; active_courses: number; eligible_chairs: number; minimum_missing_chairs: number }> }
  validation: { valid: boolean; issues: string[]; covered_sittings: number; total_sittings: number }
  metrics: { staff_used: number; total_duties: number; minimum_minutes: number; maximum_minutes: number; workload_gap_minutes: number; total_days_min: number; total_days_max: number }
  staff_loads: Array<{ staff_id: string; minutes: number; days: number; duties: number }>
  assignments: DraftAssignment[]
  message: string
}

export interface ScheduleDraft {
  id: string
  exam_period_id: string
  version_number: number
  status: 'draft' | 'approved' | 'published' | 'archived'
  solver_status: string
  generated_at: string
  notes: string | null
}
export interface SaveDraftResult {
  version: { id: string; version_number: number; status: 'draft'; assignments_saved: number; chairs_saved: number; solver_status: string }
  saved_assignments: number
  chairs_saved: number
  publication_blocked: true
  warning: string
}
export interface SavedDraftDetail {
  version: ScheduleDraft
  assignments: Array<{ staff_id: string; sitting_id: string; date: string; start: string; end: string; room_code: string }>
}

export interface ReplacementCandidate {
  staff_code: string
  existing_minutes: number
  existing_days: number
  existing_duties: number
  new_daily_minutes: number
}
export interface ReplacementResult {
  version: { id: string; version_number: number; status: 'draft'; assignments_saved: number; source_version_id: string }
  publication_blocked: true
  warning: string
}
