import { useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, FlaskConical, LockKeyhole, RefreshCw } from './ui/DeltaIcons'
import { previewShortageResolution, type ResolutionPreview, type ControlStaff } from './api'

type HeadOption = 'keep' | 'remove' | 'select'

export default function ResolutionLab({ periodId, staff, currentHeadId, currentHeadCanChair }: {
  periodId: string
  staff: ControlStaff[]
  currentHeadId: string | null
  currentHeadCanChair: boolean
}) {
  const [includeLecturers, setIncludeLecturers] = useState(false)
  const [headMode, setHeadMode] = useState<HeadOption>('keep')
  const [headId, setHeadId] = useState('')
  const [headCanChair, setHeadCanChair] = useState(currentHeadCanChair)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ResolutionPreview | null>(null)
  const doctors = useMemo(() => staff.filter(p => p.is_active && p.can_chair), [staff])
  const assistantLecturers = useMemo(() => staff.filter(p => p.is_active && p.academic_rank === 'assistant_lecturer'), [staff])

  async function simulate() {
    setError(''); setResult(null); setBusy(true)
    try {
      const data = await previewShortageResolution(periodId, {
        include_assistant_lecturers: includeLecturers,
        simulate_head_appointment: headMode !== 'keep',
        head_staff_id: headMode === 'select' ? headId : null,
        head_can_chair: headCanChair,
        seconds: 12,
      })
      setResult(data)
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setBusy(false) }
  }
  const invalidSelection = headMode === 'select' && !headId
  return <section className="surface phase11-box resolution-lab">
    <div className="panel-heading">
      <div>
        <h2><FlaskConical size={20} /> Smart Shortage Resolution</h2>
        <p>Compare the current university rules with possible changes, without editing any data.</p>
      </div>
      <span className="phase11-chip"><LockKeyhole size={13} /> Simulation only</span>
    </div>
    <div className="resolution-intro">
      <AlertCircle size={19} />
      <p>One course currently lacks a chair. The following alternatives are <strong>hypothetical</strong>:
         choosing them here does not change academic eligibility, appoint the Control Head, or save a schedule.
         Do not apply an option unless the university officially authorizes it.</p>
    </div>
    <div className="resolution-fields">
      <label className="resolution-toggle">
        <input type="checkbox" checked={includeLecturers} onChange={e => setIncludeLecturers(e.target.checked)} />
        <span><strong>What if Assistant Lecturers could chair?</strong>
          <small>{assistantLecturers.length} active staff with this academic rank. Requires official approval.</small></span>
      </label>
      <div className="resolution-head">
        <label className="phase11-label">Simulate Head of Control
          <select className="phase11-input" value={headMode} onChange={e => {setHeadMode(e.target.value as HeadOption); setHeadId('')}}>
            <option value="keep">Keep current appointment {currentHeadId ? '(appointed)' : '(none)'}</option>
            <option value="select">What if a doctor is appointed Head?</option>
            <option value="remove">What if no Head is appointed?</option>
          </select>
        </label>
        {headMode === 'select' && <label className="phase11-label">Choose hypothetical Head
          <select className="phase11-input" value={headId} onChange={e=>setHeadId(e.target.value)}>
            <option value="">Select a doctor</option>
            {doctors.map(c=><option value={c.id} key={c.id}>{c.source_ref} — {c.full_name}</option>)}
          </select>
        </label>}
      </div>
      <label className="resolution-toggle">
        <input type="checkbox" checked={headCanChair} onChange={e=>setHeadCanChair(e.target.checked)}/>
        <span><strong>What if Head of Control may also chair courses?</strong>
          <small>Administrative exception, not enabled in the real scheduling rules.</small></span>
      </label>
    </div>
    <div className="resolution-actions">
      <button className="primary-button" onClick={simulate} disabled={busy || invalidSelection}>
        {busy ? <RefreshCw className="spin" size={17}/> : <FlaskConical size={17}/>}
        {busy ? 'Running two CP-SAT scenarios…' : 'Run comparison preview'}
      </button>
      <span>No database writes • No schedule publication</span>
    </div>
    {error && <div role="alert" className="phase11-message phase11-error"><AlertCircle size={18}/>{error}</div>}
    {result && <div className="resolution-results" role="region" aria-label="Shortage simulation results">
      <div className="resolution-comparison">
        <div className="resolution-stat"><span>Current rules</span>
          <strong>{result.baseline.assigned_exams}/{result.baseline.total_exams}</strong>
          <small>{result.baseline.missing_count ?? '?'} missing · {result.baseline.eligible_chairs} eligible chairs</small>
          <em>{result.baseline.solver_status}</em>
        </div>
        <div className="resolution-versus">→</div>
        <div className="resolution-stat alt"><span>Hypothetical rules</span>
          <strong>{result.hypothetical.assigned_exams}/{result.hypothetical.total_exams}</strong>
          <small>{result.hypothetical.missing_count ?? '?'} missing · {result.hypothetical.eligible_chairs} eligible chairs</small>
          <em>{result.hypothetical.solver_status}</em>
        </div>
      </div>
      <div className={`phase11-message ${result.comparison.full_coverage_in_simulation?'phase11-success':'phase11-error'}`}>
        {result.comparison.full_coverage_in_simulation ? <CheckCircle2 size={18}/> : <AlertCircle size={18}/>}
        {result.comparison.conclusive ?
          (result.comparison.full_coverage_in_simulation
            ? 'This simulation found full chair coverage under hypothetical rules; approval is still required.'
            : 'This scenario did not produce complete coverage. Review remaining bottlenecks below.') :
          'The solver did not return a conclusive comparison within the time limit.'}
      </div>
      <div className="resolution-two">
        <div><h3>Current bottlenecks</h3><Bottlenecks rows={result.baseline.bottlenecks}/></div>
        <div><h3>After simulated changes</h3><Bottlenecks rows={result.hypothetical.bottlenecks}/></div>
      </div>
      {result.hypothetical.unassigned_exams.length>0 && <div className="resolution-unassigned">
        <h3>Still unassigned in this simulation</h3>
        {result.hypothetical.unassigned_exams.map(c=><span key={c.exam_id}>{c.code} · {c.title}</span>)}
      </div>}
      <p className="resolution-warning"><LockKeyhole size={16}/> {result.advisory}</p>
    </div>}
  </section>
}

function Bottlenecks({ rows }: { rows: ResolutionPreview['baseline']['bottlenecks'] }) {
  if (!rows.length) return <p className="resolution-empty">No simultaneous-capacity shortfall detected at the inspected start times. Other scheduling constraints may still apply.</p>
  return <div className="resolution-bottleneck-list">{rows.map((r,i)=><div className="resolution-bottleneck" key={`${r.date}-${r.time}-${i}`}>
    <strong>{r.date} · {r.time}</strong>
    <span>{r.simultaneous_courses} courses · {r.eligible_present_chairs} chairs available · <b>{r.minimum_missing_chairs} short</b></span>
    <small>{r.course_codes.join(' · ')}</small>
  </div>)}</div>
}
