import type { Audit, Comparison, Period, Snapshot, PreviewResult, ScheduleDraft, SaveDraftResult, SavedDraftDetail, ReplacementCandidate, ReplacementResult } from './types'
import { supabase } from './authClient'

async function getJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!supabase) throw new Error('Supabase Auth is not configured in .env.local.')
  const { data: { session }, error: sessionError } = await supabase.auth.getSession()
  if (sessionError || !session?.access_token) throw new Error('Not signed in. Please log in again.')
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', Authorization: `Bearer ${session.access_token}`, ...init.headers },
      cache: 'no-store',
    })
  } catch {
    throw new Error('FastAPI is not responding on 127.0.0.1:8000.')
  }
  if (!response.ok) {
    let message = response.statusText
    try { const result: { detail?: string } = await response.json(); if (result.detail) message = result.detail } catch { /* no JSON */ }
    throw new Error(`API ${response.status}: ${message}`)
  }
  return response.json() as Promise<T>
}

export interface Me { user_id: string; email: string | null; role: 'admin' | 'staff'; staff_id: string | null; full_name: string | null }
export function getMe() { return getJson<Me>('/api/v1/auth/me') }
export function getMyAssignments() { return getJson<Array<{date: string; start: string; end: string; room_code: string}>>('/api/v1/my-assignments') }
export function getPeriods() { return getJson<Period[]>('/api/v1/periods') }
export function getPeriodData(id: string) {
  const base = `/api/v1/periods/${encodeURIComponent(id)}`
  return Promise.all([
    getJson<Audit>(`${base}/audit`), getJson<Comparison>(`${base}/comparison`), getJson<Snapshot>(`${base}/snapshot`),
  ])
}
export function generatePreview(periodId: string, seconds = 25) {
  return getJson<PreviewResult>(`/api/v1/periods/${encodeURIComponent(periodId)}/preview?seconds=${seconds}`, { method: 'POST' })
}
export function getDrafts(periodId: string) {
  return getJson<ScheduleDraft[]>(`/api/v1/periods/${encodeURIComponent(periodId)}/drafts`)
}
export function saveNewDraft(periodId: string, note = '') {
  return getJson<SaveDraftResult>(`/api/v1/periods/${encodeURIComponent(periodId)}/drafts`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ seconds: 25, note }),
  })
}
export function getSavedDraft(periodId: string, versionId: string) {
  return getJson<SavedDraftDetail>(`/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}`)
}

export function getReplacementOptions(periodId: string, versionId: string, sittingId: string, oldStaffCode: string) {
  const path = `/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}`
  const query = `room_sitting_id=${encodeURIComponent(sittingId)}&old_staff_code=${encodeURIComponent(oldStaffCode)}`
  return getJson<{ source_version_id: string; candidates: ReplacementCandidate[]; note: string }>(`${path}/replacement-options?${query}`)
}
export function replaceDraftAssignment(periodId: string, versionId: string, roomSittingId: string,
                                       oldStaffCode: string, newStaffCode: string, reason: string) {
  const path = `/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}/replace`
  return getJson<ReplacementResult>(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ room_sitting_id: roomSittingId, old_staff_code: oldStaffCode,
                           new_staff_code: newStaffCode, reason }),
  })
}

export interface ControlStaff {
  id: string
  source_ref: string
  full_name: string
  academic_rank: string
  is_active: boolean
  can_chair: boolean
  eligible_for_this_plan: boolean
}
export interface ControlOverview {
  exam_period_id: string
  head_staff_id: string | null
  head_can_chair: boolean
  parallel_chair_assignments_allowed: boolean
  staff: ControlStaff[]
  course_count: number
  note: string
}
export interface ChairPreview {
  status: string
  coverage: string
  assigned_exams: number
  total_exams: number
  missing_count: number
  eligible_chairs: number
  reason: string
  assignments: Array<{exam_id:string; code:string; title:string; staff_id:string; staff_code:string}>
  unassigned_exams: Array<{exam_id:string; code:string; title:string}>
}
export interface SavedChairs {
  version: {id:string;version_number:number;status:string}
  chairs: Array<{exam_id:string;code:string;staff_id:string;staff_code:string}>
  chair_count: number
  total_exams: number
  complete: boolean
  publication_blocked: boolean
}
export function getControl(periodId: string) {
  return getJson<ControlOverview>(`/api/v1/periods/${encodeURIComponent(periodId)}/control`)
}
export function appointControlHead(periodId: string, staffId: string | null) {
  return getJson<{head_staff_id:string|null;head_name:string|null;changed:boolean;message:string}>(
    `/api/v1/periods/${encodeURIComponent(periodId)}/control/head`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({staff_id:staffId}),
    })
}
export function previewChairs(periodId: string) {
  return getJson<ChairPreview>(`/api/v1/periods/${encodeURIComponent(periodId)}/chairs/preview?seconds=20`, {method:'POST'})
}
export function getSavedChairs(periodId: string,versionId:string){
  return getJson<SavedChairs>(`/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}/chairs`)
}
export function saveChairDraft(periodId:string,versionId:string, chairs:Array<{exam_id:string; staff_id:string}>,note:string){
  return getJson<{version:{id:string;version_number:number;chairs_saved:number;total_exams:number;chair_coverage_complete:boolean};warning:string}>(
    `/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}/chairs`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chairs,note}),
    })
}


// Phase 12: admin-authorized READ-ONLY what-if advisor.
export interface ResolutionBottleneck {
  date:string; time:string; simultaneous_courses:number;
  eligible_present_chairs:number; minimum_missing_chairs:number;
  course_codes:string[]; occupied_chair_codes:string[]
}
export interface ResolutionSummary {
  solver_status:string; coverage:string; assigned_exams:number; total_exams:number;
  missing_count:number|null; eligible_chairs:number;
  unassigned_exams:Array<{exam_id:string;code:string;title:string}>;
  bottlenecks:ResolutionBottleneck[]; reason:string
}
export interface ResolutionPreview {
  mode:'ADVISORY_ONLY'; saved:false; policy_changed:false; schedule_changed:false;
  publication_enabled:false; baseline:ResolutionSummary; hypothetical:ResolutionSummary;
  comparison:{missing_courses_reduced_by:number|null;full_coverage_in_simulation:boolean;
    requires_formal_approval:boolean;conclusive:boolean};
  scenario:{assistant_lecturer_ids_simulated:string[];selected_head_id:string|null;
    head_can_chair_simulated:boolean;head_appointment_simulated:boolean};
  advisory:string
}
export interface ResolutionRequest {
  include_assistant_lecturers:boolean; simulate_head_appointment:boolean;
  head_staff_id:string|null; head_can_chair:boolean; seconds:number
}
export function previewShortageResolution(periodId:string, args:ResolutionRequest){
  return getJson<ResolutionPreview>(`/api/v1/periods/${encodeURIComponent(periodId)}/control/resolution-preview`,{
    method:'POST',headers:{'Content-Type':'application/json'}, body:JSON.stringify(args),
  })
}

// Phase 13: administrative decisions and independent SAVED-DRAFT readiness audit.
export interface AdminDecisionRecord {
  id:string; decision_type:string; target_staff_id:string|null;
  previous_value:string|null;new_value:string;justification:string;decided_at:string
}
export interface AdministrationOverview {
  period_id:string;
  assistant_lecturers:Array<{id:string;source_ref:string;full_name:string;academic_rank:string;is_active:boolean;can_chair:boolean}>;
  max_daily_minutes:number|null;
  source_attestation:{document_name:string;reviewed_at:string;matches_live_source:boolean}|null;
  decisions:AdminDecisionRecord[];
  approval_enabled:false;publishing_enabled:false;
}
export interface ReadinessReport {
  version_id:string;version_number:number;draft_status:string;ready_for_formal_review:boolean;
  approval_enabled:false;publishing_enabled:false;
  checks:{room_sittings:number;invigilator_duties:number;course_exams:number;chair_assignments:number};
  issues:Array<{code:string;message:string}>;note:string
}
export type AdminDecisionRequest = {
  kind:'chair_eligibility'|'daily_limit'|'source_signoff';staff_id?:string;
  can_chair?:boolean;max_daily_minutes?:number;source_name?:string;
  checked_original_document?:boolean;reason:string;
}
export function getAdministration(periodId:string){
  return getJson<AdministrationOverview>(`/api/v1/periods/${encodeURIComponent(periodId)}/administration`)
}
export function recordAdminDecision(periodId:string,body:AdminDecisionRequest){
  return getJson<{saved:boolean;warning:string}>(`/api/v1/periods/${encodeURIComponent(periodId)}/administration/decision`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),
  })
}
export function getDraftReadiness(periodId:string,versionId:string){
  return getJson<ReadinessReport>(`/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}/readiness`)
}

// Phase 14 — verified internal review (NOT approval) & scoped staff portal.
export interface InternalReviewRecord {
  id:string; schedule_version_id:string;state:'submitted'|'changes_requested'|'cancelled';
  request_note:string; observed_blockers:Array<{code:string;message:string}>;
  requested_at:string;response_note:string|null;resolved_at:string|null;
}
export interface StaffAccessRecord {
  id:string;source_ref:string;full_name:string;academic_rank:string;is_active:boolean;auth_user_id:string|null;
}
export interface PersonalDuty {
  type:'invigilation'|'committee_chair';date:string;start:string;end:string;
  room_code:string|null;room_number:string|null;course_codes:string[];
  period:string;version_number:number;duration_minutes:number;
}
export interface PersonalSchedule {
  published_only:true;duties:PersonalDuty[];total_duties:number;total_minutes:number;total_days:number;message:string;
}
export function getInternalReviews(periodId:string){
  return getJson<InternalReviewRecord[]>(`/api/v1/periods/${encodeURIComponent(periodId)}/internal-reviews`)
}
export function requestInternalReview(periodId:string,versionId:string,note:string){
  return getJson<{review_id:string;state:string;formal_approval:false;published:false}>(
    `/api/v1/periods/${encodeURIComponent(periodId)}/drafts/${encodeURIComponent(versionId)}/request-internal-review`,
    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})})
}
export function respondInternalReview(reviewId:string,action:'changes_requested'|'cancelled',note:string){
  return getJson<{state:string;formal_approval:false;published:false}>(
    `/api/v1/internal-reviews/${encodeURIComponent(reviewId)}/respond`,
    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,note})})
}
export function getStaffAccess(){return getJson<StaffAccessRecord[]>('/api/v1/staff-access')}
export function linkStaffAccount(staffId:string,authUserId:string,justification:string){
  return getJson<{linked:boolean;already_linked:boolean}>('/api/v1/staff-access/link',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({staff_id:staffId,auth_user_id:authUserId,justification}),
  })
}
export function getPersonalPublishedSchedule(){
  return getJson<PersonalSchedule>('/api/v1/staff/me/published-schedule')
}


// Phase 15 -- gated schedule release (only server-verified admin can access).
export interface ReleaseVersion {id:string;version_number:number;status:string;generated_at:string;approved_at:string|null;published_at:string|null}
export interface ReleaseEvent {id:string;schedule_version_id:string;action:'approved'|'published'|'superseded';decision_reference:string;created_at:string}
export interface ReleaseOverview {versions:ReleaseVersion[];events:ReleaseEvent[];current_published_version_id:string|null}
export interface ReleaseValidation {ready:boolean;status:string;issues:Array<{code:string;message:string}>;python:ReadinessReport;sql:{ready:boolean;issues:string[]}}
export function getReleaseOverview(periodId:string){
  return getJson<ReleaseOverview>(`/api/v1/periods/${encodeURIComponent(periodId)}/release`)
}
export function getReleaseValidation(periodId:string,versionId:string){
  return getJson<ReleaseValidation>(`/api/v1/periods/${encodeURIComponent(periodId)}/release/${encodeURIComponent(versionId)}/validation`)
}
export function transitionSchedule(periodId:string,versionId:string,action:'approve'|'publish',official_reference:string){
  return getJson<{action:string;version_id:string;published:boolean}>(
    `/api/v1/periods/${encodeURIComponent(periodId)}/release/${encodeURIComponent(versionId)}/transition`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,official_reference,confirms_authority:true}),
  })
}
