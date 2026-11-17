/* DELTA_UNIVERSITY_PRODUCTION_VISUAL_V1 — visual only; Production authorization / API behavior unchanged. */
import ControlCenter from './ControlCenter'
import ReviewCenter from './ReviewCenter'
import ReleaseCenter from './ReleaseCenter'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowRight, BarChart3, BookOpen,
  CalendarDays, Check, CheckCircle2, ChevronDown, CircleHelp, ClipboardCheck,
  ExternalLink, GraduationCap, Layers3, LayoutDashboard,
  LockKeyhole, LogOut, Menu, RefreshCw, Search,
  ShieldAlert, ShieldCheck, Sparkles, Users2, X
} from './ui/DeltaIcons'
import { generatePreview, getDrafts, getSavedDraft, saveNewDraft, getPeriodData, getPeriods, getReplacementOptions, replaceDraftAssignment } from './api'
import type { Audit, Comparison, Exam, Period, RoomSitting, Snapshot, Staff, PreviewResult, ScheduleDraft, SavedDraftDetail, ReplacementCandidate } from './types'

type Screen = 'overview' | 'exams' | 'rooms' | 'staff' | 'scheduler' | 'control' | 'reports' | 'review' | 'release'
type AppData = { audit: Audit; comparison: Comparison; snapshot: Snapshot }

type NavItem = { id: Screen; label: string; icon: typeof LayoutDashboard; section: 'workspace' | 'management' }
const NAV: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, section: 'workspace' },
  { id: 'scheduler', label: 'AI Scheduling', icon: Sparkles, section: 'workspace' },
  { id: 'reports', label: 'Analytics & Reports', icon: BarChart3, section: 'workspace' },
  { id: 'exams', label: 'Exam Sessions', icon: CalendarDays, section: 'management' },
  { id: 'rooms', label: 'Rooms & Labs', icon: Layers3, section: 'management' },
  { id: 'staff', label: 'Faculty & Staff', icon: Users2, section: 'management' },
  { id: 'control', label: 'Control Center', icon: ShieldCheck, section: 'management' },
  { id: 'review', label: 'Review & Access', icon: ClipboardCheck, section: 'management' },
  { id: 'release', label: 'Approval & Publishing', icon: LockKeyhole, section: 'management' },
]
const TITLES: Record<Screen, { title: string; sub: string }> = {
  overview: { title: 'Overview', sub: 'A clear view of academic examination logistics and readiness.' },
  scheduler: { title: 'Intelligent Scheduling', sub: 'Preview CP-SAT allocation and save an administrator-only draft.' },
  reports: { title: 'Analytics & Reports', sub: 'Demand patterns, capacity and operational metrics.' },
  exams: { title: 'Exam Sessions', sub: 'Browse all imported courses and their scheduled sessions.' },
  rooms: { title: 'Rooms & Laboratories', sub: 'Understand physical room occupancy throughout the exam period.' },
  staff: { title: 'Faculty & Staff', sub: 'Eligibility and academic roles, without exposing personal records.' },
  control: { title: 'Exam Control Center', sub: 'Assign Head of Control, optimize committee chairs, and save protected drafts.' },
  review: { title: 'Internal Review & Staff Access', sub: 'Request internal review and safely link faculty accounts.' },
  release: { title: 'Schedule Approval & Publishing', sub: 'Protected readiness gate, official decisions, and release history.' },
}
const ISSUE_TEXT: Record<string, { title: string; detail: string }> = {
  HEAD_OF_CONTROL_NOT_APPOINTED: { title: 'Head of Control not assigned', detail: 'An authorized admin must appoint the Head of Control.' },
  CHAIR_SHORTAGE: { title: 'Committee chair shortage', detail: 'At least one time slot has more concurrent courses than available chairs.' },
  DAILY_INVIGILATION_LIMIT_NOT_SET: { title: 'Daily work limit not defined', detail: 'Set a maximum daily invigilation duration to enforce workload policy.' },
  SOURCE_PDF_NOT_SIGNED_OFF: { title: 'Source timetable awaiting verification', detail: 'The scanned timetable must be reviewed and signed off by the faculty.' },
  INVIGILATOR_SHORTAGE: { title: 'Insufficient invigilators', detail: 'Additional eligible invigilators or new constraints are needed.' },
  ROOM_DOUBLE_BOOKED: { title: 'Overlapping room use', detail: 'One or more physical rooms have conflicting bookings.' },
  PARALLEL_CHAIR_POLICY_REQUIRES_MANUAL_VALIDATION: { title: 'Parallel chair exception', detail: 'A faculty administrator must confirm this policy before publication.' },
}

const number = (v: number) => new Intl.NumberFormat('en-US').format(v)
const shortDate = (str: string) => {
  const date = new Date(`${str}T12:00:00`)
  return Number.isNaN(date.getTime()) ? str : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}
const shortDay = (str: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(`${str}T12:00:00`))
const labelRank = (rank: string) => ({ teaching_assistant: 'Teaching Assistant', assistant_lecturer: 'Assistant Lecturer', lecturer: 'Lecturer', associate_professor: 'Associate Professor', professor: 'Professor' } as Record<string, string>)[rank] ?? rank.replaceAll('_', ' ')

function Pill({ children, kind = 'neutral' }: { children: ReactNode; kind?: 'neutral' | 'ok' | 'warn' | 'blue' }) {
  return <span className={`pill pill-${kind}`}>{children}</span>
}
function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`surface ${className}`}>{children}</section>
}
function PanelTitle({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return <div className="panel-heading"><div><h2>{title}</h2>{sub && <p>{sub}</p>}</div>{action}</div>
}
function StatCard({ icon: Icon, label, value, info, tone = 'purple' }: { icon: typeof Users2; label: string; value: number; info: string; tone?: 'purple' | 'cyan' | 'amber' | 'blue' | 'green' }) {
  return <div className="stat-card"><div className="stat-upper"><span>{label}</span><span className={`stat-icon stat-${tone}`}><Icon size={19}/></span></div><div className="stat-value">{number(value)}</div><div className="stat-info">{info}</div></div>
}
function Issues({ audit, compact = false }: { audit: Audit; compact?: boolean }) {
  return <div className="issue-list">
    {audit.issues.length === 0 ? <div className="empty-content"><CheckCircle2 size={22}/> No blocking issues reported.</div> : audit.issues.slice(0, compact ? 4 : undefined).map((key, i) => {
      const item = ISSUE_TEXT[key] ?? { title: key.replaceAll('_', ' '), detail: 'Requires administrative review.' }
      return <div className="issue-row" key={`${key}-${i}`}><span className="issue-icon"><AlertCircle size={18}/></span><div className="issue-copy"><strong>{item.title}</strong><p>{item.detail}</p></div><Pill kind="warn">Needs action</Pill></div>
    })}
  </div>
}
function DayBars({ sittings }: { sittings: RoomSitting[] }) {
  const rows = useMemo(() => {
    const map = new Map<string, number>()
    for (const sitting of sittings) map.set(sitting.date, (map.get(sitting.date) ?? 0) + 1)
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, count]) => ({ date, count }))
  }, [sittings])
  const max = Math.max(1, ...rows.map(r => r.count))
  return <div className="chart-area">
    <div className="chart-grid"><span>{max}</span><span>{Math.round(max / 2)}</span><span>0</span></div>
    <div className="bar-chart">{rows.map((r) => <div className="bar-slot" key={r.date} title={`${shortDate(r.date)} — ${r.count} room sittings`}><div className="bar-wrapper"><div className="bar" style={{ height: `${Math.max(4, (r.count / max) * 100)}%` }} /></div><span>{shortDay(r.date)}</span></div>)}</div>
  </div>
}
function Overview({ data, navigate }: { data: AppData; navigate: (s: Screen) => void }) {
  const { audit, snapshot, comparison } = data
  const count = audit.counts
  return <>
    <div className="stats-grid">
      <StatCard icon={Users2} label="Total Faculty & Staff" value={count.staff_total_active} info="Active records in Supabase" tone="purple" />
      <StatCard icon={BookOpen} label="Course Exams" value={count.courses} info={`${count.exam_sessions} exam sessions`} tone="blue" />
      <StatCard icon={Layers3} label="Room Sittings" value={count.physical_room_sittings} info="Across the exam period" tone="cyan" />
      <StatCard icon={GraduationCap} label="Invigilation Duties" value={count.required_invigilation_assignments} info="2 per occupied room" tone="amber" />
      <StatCard icon={ShieldCheck} label="Source audit flags" value={audit.issues.length} info="Source checks, not release status" tone="green" />
    </div>
    <div className="delta-quick-actions" aria-label="Quick navigation"><span className="delta-quick-label"><ShieldCheck size={20}/> Quick Actions</span><button className="primary-button" onClick={() => navigate("scheduler")}><ShieldCheck size={17}/> AI Scheduling</button><button className="outline-button" onClick={() => navigate("exams")}><CalendarDays size={17}/> Exam Sessions</button><button className="outline-button" onClick={() => navigate("staff")}><Users2 size={17}/> Faculty & Staff</button><button className="outline-button" onClick={() => navigate("release")}><ClipboardCheck size={17}/> Approval & Publishing</button></div>
    <div className="overview-layout">
      <Panel className="overview-chart">
        <PanelTitle title="Examination activity" sub="Physical room sittings by examination day" action={<Pill kind="blue">Live source</Pill>} />
        <DayBars sittings={snapshot.room_sittings} />
        <div className="chart-foot"><span><span className="legend-dot"/> Room sittings</span><span>{count.time_points_evaluated} time checkpoints analyzed</span></div>
      </Panel>
      <div className="side-panel-stack">
        <div className="readiness-card"><div className="readiness-top"><span className="readiness-icon"><ShieldAlert size={21}/></span><Pill kind="warn">Publication blocked</Pill></div><h2>Schedule readiness</h2><p>Allocation is possible for invigilators, but some administrative constraints remain unresolved.</p><div className="readiness-footer"><span>{audit.issues.length} items to review</span><button onClick={() => navigate('control')} className="inline-link">Review issues <ArrowRight size={16}/></button></div></div>
        <Panel className="small-summary"><PanelTitle title="Resource coverage" /><div className="coverage-line"><span>Eligible invigilators</span><strong>{count.eligible_invigilators}</strong></div><div className="coverage-line"><span>Eligible chairs</span><strong>{count.eligible_chairs}</strong></div><div className="coverage-line"><span>Peak invigilators needed</span><strong>{audit.peak_required_invigilators}</strong></div><div className="coverage-line"><span>Chair shortage time points</span><strong className="text-warning">{audit.chair_shortages.length}</strong></div></Panel>
      </div>
    </div>
    <div className="bottom-grid">
      <Panel><PanelTitle title="Attention required" sub="Checks preventing approval" action={<button className="text-action" onClick={() => navigate('control')}>View all <ArrowRight size={15}/></button>} /><Issues audit={audit} compact /></Panel>
      <Panel><PanelTitle title="Data integrity" sub="Supabase compared with verified baseline structure"/><div className="integrity-hero"><span className={`integrity-symbol ${comparison.matches ? 'good' : 'bad'}`}>{comparison.matches ? <Check size={22}/> : <AlertCircle size={22}/>}</span><div><strong>{comparison.matches ? 'Structure matched' : 'Difference detected'}</strong><p>{comparison.matches ? 'Live records match the offline draft structure.' : 'Live records differ from the offline reference.'}</p></div></div><div className="integrity-items">{Object.entries(comparison.sections).map(([name, section])=><div className="integrity-row" key={name}><span>{name.replaceAll('_',' ')}</span><Pill kind={section.matches ? 'ok' : 'warn'}>{section.matches ? 'Matched' : 'Review'}</Pill></div>)}</div><p className="fine-print">A structural match does not validate the source PDF transcription.</p></Panel>
    </div>
  </>
}

function Exams({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState('')
  const exams = useMemo(() => snapshot.exams.filter(e => `${e.code} ${e.title}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => a.code.localeCompare(b.code)), [snapshot.exams, query])
  return <Panel><PanelTitle title="Course examination register" sub="Imported course codes and examination sessions" action={<Pill kind="blue">{snapshot.exams.length} courses</Pill>}/><div className="table-toolbar"><div className="search-box"><Search size={17}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search course name or code" /></div></div><div className="table-scroll"><table><thead><tr><th>Course code</th><th>Course title</th><th>First session</th><th>Sessions</th><th>State</th></tr></thead><tbody>{exams.map((exam: Exam) => <tr key={exam.code}><td><span className="course-code">{exam.code}</span></td><td>{exam.title}</td><td>{exam.sessions[0] ? `${shortDate(exam.sessions[0].date)} · ${exam.sessions[0].start}` : '—'}</td><td>{exam.sessions.length}</td><td><Pill kind="ok">Imported</Pill></td></tr>)}</tbody></table>{exams.length === 0 && <div className="empty-content">No courses match your search.</div>}</div></Panel>
}
function Rooms({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState('')
  const [date, setDate] = useState('all')
  const dates = [...new Set(snapshot.room_sittings.map(s=>s.date))].sort()
  const rooms = [...new Set(snapshot.room_sittings.map(s=>s.room_code))].sort((a,b)=>a.localeCompare(b, undefined,{ numeric:true }))
  const rows = rooms.map(room => {
    const all = snapshot.room_sittings.filter(s=>s.room_code===room)
    const filtered = date === 'all' ? all : all.filter(s=>s.date===date)
    return { room, total:filtered.length, courses:new Set(filtered.flatMap(s=>s.course_codes)).size, dates:new Set(filtered.map(s=>s.date)).size }
  }).filter(r=>r.room.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>b.total-a.total)
  return <Panel><PanelTitle title="Room utilization" sub="Each physical room counts once per sitting, even when shared by courses" action={<Pill kind="blue">{rooms.length} active rooms</Pill>}/><div className="table-toolbar"><div className="search-box"><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search room code"/></div><select className="select-filter" value={date} onChange={e=>setDate(e.target.value)}><option value="all">All dates</option>{dates.map(d=><option key={d} value={d}>{shortDate(d)}</option>)}</select></div><div className="table-scroll"><table><thead><tr><th>Room / Lab</th><th>Occupied sittings</th><th>Different courses</th><th>Active days</th><th>Monitoring policy</th></tr></thead><tbody>{rows.map(r=><tr key={r.room}><td><span className="room-code">{r.room}</span></td><td>{r.total}</td><td>{r.courses}</td><td>{r.dates}</td><td><Pill kind="ok">{snapshot.assumptions.invigilators_per_room} invigilators</Pill></td></tr>)}</tbody></table></div><p className="fine-print padded">This view only lists rooms appearing in at least one imported sitting; all 33 configured rooms are not exposed by the Phase 6 API yet.</p></Panel>
}
function StaffPage({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState('')
  const rows = snapshot.staff.filter(s=>`${s.staff_id} ${s.academic_rank}`.toLowerCase().includes(query.toLowerCase()))
  const rankCounts = new Map<string,number>()
  snapshot.staff.forEach(s=>rankCounts.set(s.academic_rank,(rankCounts.get(s.academic_rank)??0)+1))
  return <><div className="three-grid"><StatCard icon={Users2} label="Active staff" value={snapshot.staff.length} info="Registered academic personnel"/><StatCard icon={GraduationCap} label="Eligible invigilators" value={snapshot.staff.filter(s=>s.can_invigilate).length} info="Invigilation candidates" tone="cyan"/><StatCard icon={ShieldCheck} label="Eligible chairs" value={snapshot.staff.filter(s=>s.can_chair).length} info="Committee leadership candidates" tone="blue"/></div><Panel><PanelTitle title="Academic rank distribution" sub="Imported classifications are preliminary"/><div className="rank-grid">{[...rankCounts].map(([rank,count])=><div key={rank} className="rank-stat"><div className="rank-num">{count}</div><span>{labelRank(rank)}</span></div>)}</div></Panel><Panel><PanelTitle title="Staff eligibility" sub="Privacy-safe preview with staff identifiers only" action={<Pill kind="neutral">Personal records hidden</Pill>}/><div className="table-toolbar"><div className="search-box"><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search staff ID or rank"/></div></div><div className="table-scroll scroll-contained"><table><thead><tr><th>Staff ID</th><th>Academic rank</th><th>Invigilation</th><th>Chair eligibility</th></tr></thead><tbody>{rows.map((s: Staff)=><tr key={s.staff_id}><td><span className="course-code">{s.staff_id}</span></td><td>{labelRank(s.academic_rank)}</td><td><Pill kind={s.can_invigilate ? 'ok' : 'neutral'}>{s.can_invigilate ? 'Eligible' : 'No'}</Pill></td><td><Pill kind={s.can_chair ? 'blue' : 'neutral'}>{s.can_chair ? 'Eligible' : 'No'}</Pill></td></tr>)}</tbody></table></div><p className="fine-print padded">Names, phones and editable staff records will be integrated after Supabase Auth and role-based permissions are implemented.</p></Panel></>
}
function ReplacementPanel({ periodId, savedDetail, target, onCancel, onSaved }: {
  periodId: string
  savedDetail: SavedDraftDetail
  target: SavedDraftDetail['assignments'][number]
  onCancel: () => void
  onSaved: (versionId: string, versionNumber: number) => void
}) {
  const [candidates, setCandidates] = useState<ReplacementCandidate[]>([])
  const [chosen, setChosen] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setCandidates([]); setChosen(''); setReason('')
    getReplacementOptions(periodId, savedDetail.version.id, target.sitting_id, target.staff_id)
      .then(result => { if(active) { setCandidates(result.candidates); setChosen(result.candidates[0]?.staff_code ?? '') } })
      .catch(e => { if(active) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if(active) setLoading(false) })
    return () => { active = false }
  }, [periodId, savedDetail.version.id, target.sitting_id, target.staff_id])
  async function save() {
    if (busy || !chosen || reason.trim().length < 3) return
    setBusy(true); setError('')
    try {
      const result = await replaceDraftAssignment(periodId, savedDetail.version.id,
        target.sitting_id, target.staff_id, chosen, reason.trim())
      onSaved(result.version.id, result.version.version_number)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <div className="replace-panel">
    <div className="replace-head"><div><h3>Replace invigilator · Draft only</h3><p>{target.date} · {target.start}–{target.end} · {target.room_code} · Current {target.staff_id}</p></div>
      <button className="outline-button" onClick={onCancel} disabled={busy}>Cancel</button></div>
    <p className="fine-print">Candidates are filtered for clashes and absences, ranked by their existing workload. The server rechecks the complete schedule before saving.</p>
    {loading ? <p>Finding eligible replacements…</p> : <div className="replace-fields">
      <label>Recommended replacement<select aria-label="Choose replacement" value={chosen} onChange={e => setChosen(e.target.value)}>
        {candidates.map(c => <option key={c.staff_code} value={c.staff_code}>{c.staff_code} · {c.existing_minutes} min · {c.existing_days} days</option>)}
      </select></label>
      <label>Reason for the change<input aria-label="Replacement reason" value={reason} onChange={e=>setReason(e.target.value)}
        maxLength={300} placeholder="e.g. Invigilator unavailable" /></label>
      <button className="primary-button" onClick={save} disabled={busy || !chosen || reason.trim().length < 3}>
        {busy ? 'Validating and saving…' : 'Save as NEW draft version'}</button>
    </div>}
    {!loading && candidates.length === 0 && <p className="form-error">No eligible candidates under the current constraints.</p>}
    {error && <p className="form-error">{error}</p>}
    <p className="fine-print">The original draft is never changed. Committee chairs and publication remain blocked.</p>
  </div>
}

function Scheduler({ audit, snapshot, periodId }: { audit: Audit; snapshot: Snapshot; periodId: string }) {
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [running, setRunning] = useState(false)
  const [problem, setProblem] = useState('')
  const [query, setQuery] = useState('')
  const [date, setDate] = useState('all')
  const [page, setPage] = useState(1)
  const [showLoads, setShowLoads] = useState(false)
  const [drafts, setDrafts] = useState<ScheduleDraft[]>([])
  const [draftError, setDraftError] = useState('')
  const [savedNote, setSavedNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveConfirmation, setSaveConfirmation] = useState('')
  const [savedDetail, setSavedDetail] = useState<SavedDraftDetail | null>(null)
  const [showSavedCount, setShowSavedCount] = useState(50)
  const [replacementTarget, setReplacementTarget] = useState<SavedDraftDetail['assignments'][number] | null>(null)
  const loadDrafts = useCallback(() => {
    getDrafts(periodId).then(setDrafts).catch(e => setDraftError(e instanceof Error ? e.message : String(e)))
  }, [periodId])
  useEffect(() => { loadDrafts() }, [loadDrafts])
  async function persistNewDraft() {
    setSaving(true); setDraftError(''); setSaveConfirmation(''); setSavedDetail(null); setReplacementTarget(null)
    try {
      const saved = await saveNewDraft(periodId, savedNote)
      setSaveConfirmation(`Version ${saved.version.version_number} saved with ${saved.saved_assignments} invigilation duties. Chairs remain incomplete. Publishing is disabled.`)
      await getDrafts(periodId).then(setDrafts)
    } catch (e) { setDraftError(e instanceof Error ? e.message : String(e)) }
    finally { setSaving(false) }
  }
  async function viewSaved(versionId: string) {
    setDraftError(''); setSavedDetail(null); setShowSavedCount(50); setReplacementTarget(null)
    try { setSavedDetail(await getSavedDraft(periodId, versionId)) }
    catch (e) { setDraftError(e instanceof Error ? e.message : String(e)) }
  }
  const formatMinutes = (n: number) => `${Math.floor(n / 60)}h ${String(n % 60).padStart(2, '0')}m`
  async function runPreview() {
    setProblem('')
    setRunning(true)
    setPreview(null)
    try {
      const result = await generatePreview(periodId, 25)
      setPreview(result)
      setQuery('')
      setDate('all')
      setPage(1)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error))
    } finally { setRunning(false) }
  }
  const dates = useMemo(() => [...new Set(preview?.assignments.map(a=>a.date) ?? [])].sort(), [preview])
  const filtered = useMemo(() => (preview?.assignments ?? []).filter(a => (date === 'all' || a.date === date) &&
    [a.staff_id,a.room_code,a.course_codes].some(v=>v.toLowerCase().includes(query.toLowerCase()))), [preview, date, query])
  const limit = 50
  const pages = Math.max(1, Math.ceil(filtered.length / limit))
  const visible = filtered.slice((Math.min(page,pages)-1)*limit,Math.min(page,pages)*limit)
  function exportCsv() {
    if (!preview?.assignments.length) return
    const header = ['Staff ID','Date','Start','End','Room','Course codes','Minutes','Sitting ID']
    const rows = preview.assignments.map(x=>[x.staff_id,x.date,x.start,x.end,x.room_code,x.course_codes,x.minutes,x.sitting_id])
    const content='\uFEFF'+[header,...rows].map(row=>row.map(cell=>`"${String(cell).replaceAll('"','""')}"`).join(',')).join('\r\n')
    const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}))
    const a=document.createElement('a');a.href=url;a.download='invigilator_PREVIEW_NOT_APPROVED.csv';a.click();URL.revokeObjectURL(url)
  }
  return <>
    <div className="scheduler-hero"><div className="large-sparkle"><Sparkles size={25}/></div><div className="scheduler-hero-copy">
      <span className="eyebrow">OPTIMIZATION ENGINE / LIVE CP-SAT</span>
      <h2>Generate a schedule, then save a secure draft.</h2>
      <p>Use the live Supabase records to allocate two invigilators per occupied room. Previews stay in memory. Only an authenticated admin can run and save a NEW validated draft. Chairs, approvals and publishing remain blocked.</p>
      <div className="hero-actions"><button className="primary-button" disabled={running} onClick={runPreview}><Sparkles size={17}/>{running ? 'Running optimization…' : 'Generate schedule preview'}</button><Pill kind="warn">Publishing disabled</Pill></div>
    </div><span className="hero-decor">AI</span></div>
    <div className="three-grid"><StatCard icon={Users2} label="Eligible invigilators" value={audit.counts.eligible_invigilators} info="Available under current role flags"/><StatCard icon={Layers3} label="Required duties" value={audit.counts.required_invigilation_assignments} info="Two per occupied room" tone="cyan"/><StatCard icon={ShieldAlert} label="Chair shortage slots" value={audit.chair_shortages.length} info="Requires administrative resolution" tone="amber"/></div>
    {running && <Panel><div className="preview-notice"><div className="spinner"/><div><strong>Optimizing invigilator assignments...</strong><p>Checking availability, preventing overlaps and balancing workloads. This operation can take several seconds.</p></div></div></Panel>}
    {problem && <div className="control-banner"><AlertCircle size={21}/><div><strong>Preview could not run</strong><p>{problem}</p><p>Check that you installed the Phase 8 backend patch, restarted FastAPI, and kept the local server running.</p></div></div>}
    {preview && <>
      <Panel><PanelTitle title="Live preview results" sub={`Generated ${new Date(preview.generated_at).toLocaleString('en-GB')} · In-memory draft only`}
        action={<button className="outline-button" onClick={exportCsv} disabled={!preview.assignments.length}><ArrowDownToLine size={17}/> Export draft CSV</button>}/>
        <div className="preview-status"><Pill kind={preview.validation.valid ? 'ok' : 'warn'}>{preview.validation.valid ? 'Independent roster checks passed' : 'Roster needs review'}</Pill><Pill kind={preview.invigilator.status === 'OPTIMAL' ? 'ok' : 'blue'}>Invigilators: {preview.invigilator.status}</Pill><Pill kind="warn">Chairs: {preview.chair.status}</Pill></div>
        <div className="preview-metrics"><div><span>Assigned duties</span><strong>{number(preview.metrics.total_duties)}</strong></div><div><span>Staff used</span><strong>{preview.metrics.staff_used}</strong></div><div><span>Workload spread</span><strong>{formatMinutes(preview.metrics.workload_gap_minutes)}</strong></div><div><span>Assigned days range</span><strong>{preview.metrics.total_days_min}–{preview.metrics.total_days_max}</strong></div></div>
        <div className="preview-note"><ShieldAlert size={18}/><span>{preview.message} {preview.chair.reason ?? ''}</span></div>
        {preview.validation.issues.length > 0 && <div className="preview-errors">{preview.validation.issues.map(issue=><div key={issue}><AlertCircle size={16}/> {issue}</div>)}</div>}
      </Panel>
      <Panel><PanelTitle title="Invigilator assignment preview" sub="Anonymous staff IDs only. All rows are generated from live database records."
        action={<Pill kind="neutral">{number(filtered.length)} of {number(preview.assignments.length)} duties</Pill>}/>
        <div className="table-toolbar"><div className="search-box"><Search size={17}/><input value={query} onChange={e=>{setQuery(e.target.value);setPage(1)}} placeholder="Search staff, lab or course" /></div><select className="select-filter" value={date} onChange={e=>{setDate(e.target.value);setPage(1)}}><option value="all">All dates</option>{dates.map(d=><option key={d} value={d}>{shortDate(d)}</option>)}</select></div>
        <div className="table-scroll"><table><thead><tr><th>Staff ID</th><th>Date</th><th>Time</th><th>Room</th><th>Course(s)</th><th>Duration</th></tr></thead><tbody>{visible.map((a,i)=><tr key={`${a.sitting_id}-${a.staff_id}-${i}`}><td><span className="course-code">{a.staff_id}</span></td><td>{shortDate(a.date)}</td><td>{a.start}–{a.end}</td><td><span className="room-code">{a.room_code}</span></td><td>{a.course_codes}</td><td>{a.minutes} min</td></tr>)}</tbody></table>{filtered.length === 0 && <div className="empty-content">No assignments match those filters.</div>}</div>
        <div className="preview-pagination"><span>Page {Math.min(page,pages)} of {pages}</span><div><button className="outline-button" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="outline-button" disabled={page>=pages} onClick={()=>setPage(p=>p+1)}>Next</button></div></div>
      </Panel>
      <Panel><PanelTitle title="Fairness by staff member" sub="Hours, duties and active days across the full examination period"
        action={<button className="outline-button" onClick={()=>setShowLoads(v=>!v)}>{showLoads ? 'Hide breakdown' : 'View breakdown'}</button>}/>
        {showLoads && <div className="table-scroll scroll-contained"><table><thead><tr><th>Staff ID</th><th>Assignments</th><th>Total time</th><th>Assigned days</th></tr></thead><tbody>{preview.staff_loads.map(x=><tr key={x.staff_id}><td>{x.staff_id}</td><td>{x.duties}</td><td>{formatMinutes(x.minutes)}</td><td>{x.days}</td></tr>)}</tbody></table></div>}
        <p className="fine-print">Equal total hours do not necessarily mean equal daily workload. The daily limit is still not configured.</p>
      </Panel>
    </>}
    <Panel><PanelTitle title="Saved draft versions" sub="Private admin-only schedules stored atomically in Supabase. Saving reruns the solver against current live data. No publishing is possible." action={<button className="outline-button" onClick={loadDrafts}><RefreshCw size={16}/> Reload</button>}/>
      <div className="draft-save-actions"><input aria-label="Draft notes" value={savedNote} onChange={e=>setSavedNote(e.target.value)} placeholder="Optional internal note" maxLength={350}/>
        <button className="primary-button" onClick={persistNewDraft} disabled={saving || running}>{saving ? 'Generating and saving…' : 'Generate & save NEW draft'}</button></div>
      <div className="draft-alert"><ShieldAlert size={17}/> No approval or publication in Phase 10. The six eligible chairs cannot yet cover all overlapping exams.</div>
      {saveConfirmation && <div className="preview-status"><Pill kind="ok">{saveConfirmation}</Pill></div>}
      {draftError && <p className="form-error">{draftError}</p>}
      <div className="draft-list">{drafts.map(d=><div className="draft-row" key={d.id}><div><strong>Version {d.version_number} · {d.solver_status}</strong><p>Saved {new Date(d.generated_at).toLocaleString('en-GB')} · {d.status.toUpperCase()} · Chairs not approved</p></div><button className="outline-button" onClick={()=>viewSaved(d.id)}>View saved duties</button></div>)}
      {drafts.length === 0 && !draftError && <div className="empty-content">No drafts saved yet. Generate and save your first private draft.</div>}</div>
      {savedDetail && <div style={{marginTop:24}}><PanelTitle title={`Version ${savedDetail.version.version_number} — persisted assignments`} sub={`${savedDetail.assignments.length} saved rows; showing first ${Math.min(showSavedCount, savedDetail.assignments.length)}`}/>
        <div className="table-scroll scroll-contained"><table><thead><tr><th>Staff code</th><th>Date</th><th>Time</th><th>Room</th><th>Action</th></tr></thead><tbody>{savedDetail.assignments.slice(0,showSavedCount).map((a,i)=><tr key={`${a.sitting_id}-${a.staff_id}-${i}`}><td>{a.staff_id}</td><td>{a.date}</td><td>{a.start}–{a.end}</td><td>{a.room_code}</td><td><button className="outline-button" onClick={()=>setReplacementTarget(a)}>Replace</button></td></tr>)}</tbody></table></div>
        {showSavedCount < savedDetail.assignments.length && <button className="outline-button" onClick={()=>setShowSavedCount(n=>n+50)}>Load 50 more</button>}
        {replacementTarget && <ReplacementPanel key={`${savedDetail.version.id}-${replacementTarget.sitting_id}-${replacementTarget.staff_id}`}
          periodId={periodId} savedDetail={savedDetail} target={replacementTarget}
          onCancel={()=>setReplacementTarget(null)} onSaved={(newId, newNumber)=>{
            setReplacementTarget(null)
            setSaveConfirmation(`New version ${newNumber} saved after validated replacement. The source version remains unchanged.`)
            getDrafts(periodId).then(setDrafts).catch(()=>{})
            viewSaved(newId)
          }}/>}</div>}
    </Panel>
    <div className="bottom-grid"><Panel><PanelTitle title="Current optimization rules" sub="Read from the live scheduling_rules record"/><div className="rules-grid"><div><span>Invigilators per room</span><strong>{snapshot.assumptions.invigilators_per_room}</strong></div><div><span>Minimum break</span><strong>{snapshot.assumptions.min_break_minutes} min</strong></div><div><span>Preparation time</span><strong>{snapshot.assumptions.preparation_minutes} min</strong></div><div><span>Daily time limit</span><strong>{snapshot.assumptions.max_daily_invigilation_minutes ?? 'Not set'}</strong></div><div><span>Parallel chair assignments</span><strong>{snapshot.assumptions.allow_parallel_chair_assignments ? 'Allowed' : 'Disallowed'}</strong></div></div></Panel><Panel><PanelTitle title="What remains before publishing" sub="A preview does not approve exam duties"/><Issues audit={audit} compact/></Panel></div>
  </>
}

function Reports({ snapshot, audit }: { snapshot: Snapshot; audit: Audit }) {
  const daily = useMemo(()=>{ const map = new Map<string,{sittings:number;courses:Set<string>}>(); for(const sitting of snapshot.room_sittings){const item=map.get(sitting.date)??{sittings:0,courses:new Set<string>()};item.sittings+=1;sitting.course_codes.forEach(c=>item.courses.add(c));map.set(sitting.date,item)} return [...map.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([date,item])=>({date,sittings:item.sittings,invigilatorDuties:item.sittings*snapshot.assumptions.invigilators_per_room,courses:item.courses.size}))},[snapshot])
  function exportCsv() { const rows = [['Date','Room sittings','Required invigilation duties','Distinct course codes'],...daily.map(row=>[row.date,row.sittings,row.invigilatorDuties,row.courses])]; const content=rows.map(row=>row.map(cell=>`"${String(cell).replaceAll('"','""')}"`).join(',')).join('\r\n'); const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'})); const a=document.createElement('a');a.href=url;a.download='exam_room_demand_report.csv';a.click();URL.revokeObjectURL(url)}
  return <><Panel><PanelTitle title="Daily room demand" sub="Operational demand across all examination dates" action={<button className="outline-button" onClick={exportCsv}><ArrowDownToLine size={17}/> Export CSV</button>}/><DayBars sittings={snapshot.room_sittings}/></Panel><Panel><PanelTitle title="Daily operational breakdown" sub="Derived from the live room-sittings register"/><div className="table-scroll"><table><thead><tr><th>Date</th><th>Room sittings</th><th>Required invigilation duties</th><th>Distinct courses</th></tr></thead><tbody>{daily.map(row=><tr key={row.date}><td>{shortDate(row.date)}</td><td>{row.sittings}</td><td>{row.invigilatorDuties}</td><td>{row.courses}</td></tr>)}</tbody><tfoot><tr><td>Total</td><td>{audit.counts.physical_room_sittings}</td><td>{audit.counts.required_invigilation_assignments}</td><td>—</td></tr></tfoot></table></div></Panel></>
}

export default function App({ onSignOut, accountEmail }: { onSignOut: () => void; accountEmail: string }) {
  const [screen, setScreen] = useState<Screen>('overview')
  const [periods, setPeriods] = useState<Period[]>([])
  const [periodId, setPeriodId] = useState('')
  const [data, setData] = useState<AppData | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(() => setRefreshKey(k=>k+1), [])
  useEffect(() => {
    let active = true
    getPeriods().then(list=>{ if(active) {setPeriods(list);setPeriodId(id=>list.some(p=>p.id===id)?id:(list[0]?.id??'')); if(list.length===0) setBusy(false)} }).catch(e=>{if(active){setBusy(false);setError(e instanceof Error ? e.message:String(e))}})
    return ()=>{active=false}
  }, [refreshKey])
  useEffect(()=>{
    if(!periodId) return
    let active=true
    setBusy(true);setError('')
    getPeriodData(periodId).then(([audit,comparison,snapshot])=>{if(active){setData({audit,comparison,snapshot});setBusy(false)}}).catch(e=>{if(active){setError(e instanceof Error?e.message:String(e));setBusy(false)}})
    return ()=>{active=false}
  },[periodId,refreshKey])
  const activePeriod=periods.find(p=>p.id===periodId)
  const navigate=(next: Screen)=>{setScreen(next);setMobileOpen(false)}

  return <div className="app-shell">
    {mobileOpen && <div className="mobile-backdrop" onClick={()=>setMobileOpen(false)}/>}
    <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
      <div className="brand delta-branded"><img className="delta-university-logo" src="/delta-university-logo.png" alt="Delta University logo"/><div className="delta-brand-caption"><strong>DELTA <span>EXAM</span></strong><small>Examination Scheduling System</small></div><button className="mobile-close" onClick={()=>setMobileOpen(false)}><X size={19}/></button></div>
      <div className="workspace-badge delta-period-badge"><span className="workspace-icon"><CalendarDays size={20}/></span><div><strong>{activePeriod?.name ?? "Select an exam period"}</strong><small>Exam period · University data</small></div></div>
      <nav>{(['workspace','management'] as const).map(group=><div className="nav-section" key={group}><span className="nav-label">{group==='workspace'?'WORKSPACE':'MANAGEMENT'}</span>{NAV.filter(n=>n.section===group).map(({id,label,icon:Icon})=><button type="button" key={id} className={`nav-item ${screen===id?'selected':''}`} onClick={()=>navigate(id)}><Icon size={19}/><span>{label}</span>{id==='control' && data && data.audit.issues.length>0 && <i className="nav-count">{data.audit.issues.length}</i>}</button>)}</div>)}</nav>
      <div className="sidebar-foot"><div className="foot-status"><span className="pulse-dot"/><div><strong>Local development</strong><small>Authenticated administrator</small></div></div><span className="version-label">DELTA / University data</span></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><div className="delta-topbar-title"><strong>Delta Exam Scheduler</strong><span>Examination Planning & Operations System</span></div><div className="breadcrumbs"><button className="menu-button" onClick={()=>setMobileOpen(true)}><Menu size={22}/></button><span>Workspace</span><span className="slash">/</span><strong>{TITLES[screen].title}</strong></div><div className="topbar-actions"><span className="production-env-badge" title="University Supabase dataset · Local frontend">UNIVERSITY DATA</span><span className="topbar-sync"><span className="green-dot"/> Admin · drafts enabled</span><button className="round-action" title="Refresh live data" onClick={refresh}><RefreshCw size={18}/></button><a className="round-action" title="FastAPI Swagger docs" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer"><ExternalLink size={18}/></a><div className="avatar" title={accountEmail}>AD</div><button className="round-action" title="Sign out" onClick={onSignOut}><LogOut size={18}/></button></div></header>
      <main className="main-content"><div className="page-intro"><div><div className="eyebrow">EXAM MANAGEMENT SYSTEM <span className="eyebrow-bar">/</span> 2026–2027</div><h1>{TITLES[screen].title}</h1><p>{TITLES[screen].sub}</p></div><div className="page-controls">{periods.length>0 && <label className="period-select"><CalendarDays size={18}/><select value={periodId} onChange={e=>setPeriodId(e.target.value)} aria-label="Select examination period">{periods.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select><ChevronDown size={16}/></label>}<button className="outline-button" onClick={refresh} disabled={busy}><RefreshCw size={16} className={busy?'spin':''}/> Refresh</button></div></div>
      {activePeriod && <div className="period-strip"><span className="strip-icon"><CalendarDays size={17}/></span><strong>{activePeriod.name}</strong><span className="strip-divider"/><span>{shortDate(activePeriod.start_date)} — {shortDate(activePeriod.end_date)}</span><span className="strip-spacer"/><Pill kind={data?.comparison.matches?'ok':'neutral'}>{data?.comparison.matches?'Live data verified structurally':'Review status'}</Pill></div>}
      {busy ? <div className="loading-state"><div className="spinner"/><h2>Loading examination records</h2><p>Reading the live Supabase-backed API…</p></div> : error ? <div className="error-state"><AlertCircle size={30}/><h2>Could not load dashboard</h2><p>{error}</p><button className="primary-button" onClick={refresh}><RefreshCw size={16}/> Retry</button><span>Make sure FastAPI is running on http://127.0.0.1:8000</span></div> : !data ? <div className="error-state"><CircleHelp size={30}/><h2>No examination period found</h2><p>Import the exam period into Supabase before using the dashboard.</p></div> : <>
        {screen==='overview' && <Overview data={data} navigate={navigate}/>}
        {screen==='exams' && <Exams snapshot={data.snapshot}/>}
        {screen==='rooms' && <Rooms snapshot={data.snapshot}/>}
        {screen==='staff' && <StaffPage snapshot={data.snapshot}/>}
        {screen==='scheduler' && <Scheduler key={periodId} periodId={periodId} audit={data.audit} snapshot={data.snapshot}/>}
        {screen==='control' && <ControlCenter key={periodId} periodId={periodId} audit={data.audit} snapshot={data.snapshot} onChange={refresh}/>}
        {screen==='review' && <ReviewCenter key={periodId} periodId={periodId}/>}
        {screen==='release' && <ReleaseCenter key={periodId} periodId={periodId}/>}
        {screen==='reports' && <Reports audit={data.audit} snapshot={data.snapshot}/>}
      </>}
      <footer className="content-footer"><span><LockKeyhole size={14}/> Administrator-only scheduling · Publication gated</span><span>Delta University · University data · Protected publication</span><span><Activity size={14}/> FastAPI + Supabase + OR-Tools</span></footer>
      </main>
    </div>
  </div>
}
