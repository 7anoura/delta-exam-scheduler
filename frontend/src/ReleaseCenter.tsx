import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, ClipboardCheck, LockKeyhole, RefreshCw, ShieldCheck } from './ui/DeltaIcons'
import { getReleaseOverview, getReleaseValidation, transitionSchedule,
  type ReleaseOverview, type ReleaseValidation } from './api'

export default function ReleaseCenter({ periodId }: { periodId: string }) {
  const [overview, setOverview] = useState<ReleaseOverview|null>(null)
  const [versionId, setVersionId] = useState('')
  const [gate, setGate] = useState<ReleaseValidation|null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reference, setReference] = useState('')
  const [authorized, setAuthorized] = useState(false)
  const selected = overview?.versions.find(v => v.id === versionId)
  const action: 'approve'|'publish'|null = selected?.status === 'draft' ? 'approve' : selected?.status === 'approved' ? 'publish' : null

  async function reload() {
    const data = await getReleaseOverview(periodId)
    setOverview(data)
    setVersionId(old => data.versions.some(v => v.id === old) ? old : (data.versions[0]?.id??''))
    return data
  }
  useEffect(() => {
    let active = true
    getReleaseOverview(periodId).then(data => {
      if(!active)return
      setOverview(data);setVersionId(data.versions[0]?.id??'')
      setGate(null);setError('');setMessage('')
    }).catch(e => {if(active)setError(e instanceof Error?e.message:String(e))})
    return () => {active=false}
  }, [periodId])

  async function validate() {
    if(!versionId)return
    setBusy(true);setError('');setMessage('');setGate(null)
    try {setGate(await getReleaseValidation(periodId,versionId))}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  async function release() {
    if(!versionId || !gate?.ready || !action || !authorized || reference.trim().length < 12)return
    if(!window.confirm(`Confirm ${action.toUpperCase()} of Version ${selected?.version_number}?\nThis operation may expose schedules to staff if publishing. Only proceed with verified university authorization.`))return
    setBusy(true);setError('');setMessage('')
    try {
      const result = await transitionSchedule(periodId,versionId,action,reference.trim())
      await reload();setGate(null);setAuthorized(false);setReference('')
      setMessage(`${result.action.toUpperCase()} recorded. The server rechecked the saved schedule and database rules.`)
    } catch(e) {
      setGate(null)
      setError(e instanceof Error?e.message:String(e))
    } finally {setBusy(false)}
  }

  return <div className="phase14-layout">
    <div className="phase13-title"><span className="phase13-icon"><ShieldCheck size={23}/></span><div>
      <h2>Approval & Publishing Gate</h2>
      <p>Two server-validated transitions. Real university authorization is mandatory. No automatic publication.</p>
    </div><span className="pill pill-warn"><LockKeyhole size={14}/> Safe by default</span></div>
    {error && <div className="phase11-message phase11-error" role="alert"><AlertCircle size={18}/>{error}</div>}
    {message && <div className="phase11-message phase11-success" role="status"><CheckCircle2 size={18}/>{message}</div>}
    <section className="surface phase14-card">
      <div className="panel-heading"><div><h2>1 · Select saved version</h2><p>Only a validated DRAFT may be approved; only an APPROVED version may be published.</p></div>
      <button className="outline-button" onClick={()=>void reload().catch(e=>setError(String(e)))} disabled={busy}><RefreshCw size={16}/> Refresh</button></div>
      <div className="phase14-fields"><label>Version
        <select className="phase11-input" value={versionId} onChange={e=>{setVersionId(e.target.value);setGate(null);setAuthorized(false);setMessage('')}}>
          {(overview?.versions??[]).map(v=><option key={v.id} value={v.id}>Version {v.version_number} — {v.status.toUpperCase()}</option>)}
        </select></label>
        <div className="phase15-info">Currently visible publication: <b>{overview?.versions.find(v=>v.id===overview.current_published_version_id)?.version_number??'None'}</b></div>
      </div>
      <button className="primary-button" onClick={()=>void validate()} disabled={busy||!versionId}>
        {busy?<RefreshCw size={16} className="spin"/>:<ClipboardCheck size={16}/>} Run final release validation
      </button>
      {gate && <div className="phase14-report">
        <strong>{gate.ready? 'Validation PASSED — human authorization still required' : `${gate.issues.length} release blocker(s) detected`}</strong>
        <p>Version status: {gate.status.toUpperCase()} · Saved duties: {gate.python.checks.invigilator_duties} · Chairs: {gate.python.checks.chair_assignments}/{gate.python.checks.course_exams}</p>
        {gate.issues.map(i=><div className="phase14-blocker" key={i.code}><AlertCircle size={15}/><span><b>{i.code}</b> — {i.message}</span></div>)}
      </div>}
    </section>
    <section className="surface phase14-card">
      <div className="panel-heading"><div><h2>2 · Authorized transition</h2><p>Not a simulation. This action writes a formal release event when all checks pass.</p></div>
        <span className={`pill pill-${gate?.ready?'ok':'warn'}`}>{gate?.ready?'Eligible for authorization':'Blocked pending validation'}</span></div>
      <label className="phase14-label">Official university approval reference / responsible authority (at least 12 characters)
        <textarea className="phase13-textarea" value={reference} onChange={e=>setReference(e.target.value)}
          placeholder="Record the actual dated decision / signature reference. Never invent approval details."/></label>
      <label className="phase15-confirm"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>
        I have verified genuine university authorization for this action. I understand publication exposes duties to staff accounts.
      </label>
      <div className="phase14-actions"><button className="primary-button" disabled={busy||!gate?.ready||!action||!authorized||reference.trim().length<12}
        onClick={()=>void release()}><LockKeyhole size={16}/>{action==='approve'?'Approve validated version':action==='publish'?'Publish approved version':'Version not releasable'}</button>
        <span>Version 3 is expected to stay blocked until its unresolved faculty decisions are genuinely resolved and a new draft is generated.</span></div>
    </section>
    <section className="surface phase14-card"><div className="panel-heading"><div><h2>3 · Release audit history</h2><p>Each authorized approval, publication and superseded publication is recorded.</p></div></div>
      {overview?.events.length ? <div className="phase14-review-list">{overview.events.map(e=><article key={e.id} className="phase14-review-row">
        <div><b>Version {overview.versions.find(v=>v.id===e.schedule_version_id)?.version_number??'?'}</b> · {e.action.toUpperCase()}
          <p>{e.decision_reference}</p><small>{new Date(e.created_at).toLocaleString()}</small></div>
      </article>)}</div>:<p className="phase14-empty">No approvals or publications have been recorded. Drafts remain private.</p>}
    </section>
  </div>
}
