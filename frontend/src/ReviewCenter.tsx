import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, ClipboardCheck, LockKeyhole, RefreshCw, UserRoundCheck } from './ui/DeltaIcons'
import {
  getDrafts, getDraftReadiness, getInternalReviews, requestInternalReview, respondInternalReview,
  getStaffAccess, linkStaffAccount, type InternalReviewRecord, type ReadinessReport, type StaffAccessRecord,
} from './api'
import type { ScheduleDraft } from './types'

export default function ReviewCenter({periodId}:{periodId:string}) {
  const [drafts,setDrafts]=useState<ScheduleDraft[]>([])
  const [reviews,setReviews]=useState<InternalReviewRecord[]>([])
  const [staff,setStaff]=useState<StaffAccessRecord[]>([])
  const [versionId,setVersionId]=useState('')
  const [report,setReport]=useState<ReadinessReport|null>(null)
  const [requestNote,setRequestNote]=useState('')
  const [replyNote,setReplyNote]=useState('')
  const [chosenStaff,setChosenStaff]=useState('')
  const [staffAuthId,setStaffAuthId]=useState('')
  const [linkReason,setLinkReason]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')

  async function reload() {
    const [d,r,s] = await Promise.all([getDrafts(periodId),getInternalReviews(periodId),getStaffAccess()])
    setDrafts(d);setReviews(r);setStaff(s)
    setVersionId(v=>d.some(x=>x.id===v)?v:d[0]?.id??'')
  }
  useEffect(()=>{let active=true
    Promise.all([getDrafts(periodId),getInternalReviews(periodId),getStaffAccess()]).then(([d,r,s])=>{
      if(!active)return
      setDrafts(d);setReviews(r);setStaff(s);setVersionId(d[0]?.id??'');setReport(null)
      setError('');setMessage('')
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:String(e))})
    return ()=>{active=false}
  },[periodId])
  async function act(fn:()=>Promise<unknown>,messageAfter:string){
    setBusy(true);setError('');setMessage('')
    try{await fn();await reload();setMessage(messageAfter)}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  async function validate(){
    if(!versionId)return
    setBusy(true);setError('')
    try{setReport(await getDraftReadiness(periodId,versionId))}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const selected=drafts.find(x=>x.id===versionId)
  const pending=reviews.some(x=>x.schedule_version_id===versionId&&x.state==='submitted')
  return <div className="phase14-layout">
    <div className="phase13-title"><span className="phase13-icon"><ClipboardCheck size={23}/></span><div>
      <h2>Review Workflow & Staff Access</h2>
      <p>Internal review and personal-account onboarding. Formal approval and publishing are NOT enabled.</p></div>
      <span className="pill pill-warn">Drafts remain private</span>
    </div>
    {error&&<div className="phase11-message phase11-error" role="alert"><AlertCircle size={18}/>{error}</div>}
    {message&&<div className="phase11-message phase11-success" role="status"><CheckCircle2 size={18}/>{message}</div>}
    <section className="surface phase14-card">
      <div className="panel-heading"><div><h2>1 · Request an internal schedule review</h2>
        <p>The saved version is NOT approved. Current blockers are attached to the request for the reviewer.</p></div>
        <span className="pill pill-warn"><LockKeyhole size={14}/> Approval locked</span></div>
      <div className="phase14-fields">
        <label>Saved version
          <select className="phase11-input" value={versionId} onChange={e=>{setVersionId(e.target.value);setReport(null)}}>
            {drafts.map(x=><option key={x.id} value={x.id}>Version {x.version_number} — {x.status.toUpperCase()}</option>)}
          </select></label>
        <button className="outline-button" onClick={()=>void validate()} disabled={busy||!versionId}>
          {busy?<RefreshCw size={16} className="spin"/>:<ClipboardCheck size={16}/>} Run readiness check</button>
      </div>
      {report && <div className="phase14-report">
        <strong>{report.ready_for_formal_review?'Automated checks passed — review still required':`${report.issues.length} unresolved readiness issue(s)`}</strong>
        <p>{report.checks.invigilator_duties} invigilation duties · {report.checks.chair_assignments}/{report.checks.course_exams} chair duties</p>
        {report.issues.map(i=><div className="phase14-blocker" key={i.code}><AlertCircle size={15}/><span><b>{i.code}</b> — {i.message}</span></div>)}
      </div>}
      <label className="phase14-label">Review purpose, person responsible or reference (at least 12 characters)
        <textarea className="phase13-textarea" value={requestNote} onChange={e=>setRequestNote(e.target.value)} placeholder="Internal academic review of version 3; list issues for the examiner to resolve..."/>
      </label>
      <div className="phase14-actions"><button className="primary-button" disabled={busy||!selected||selected.status!=='draft'||pending||requestNote.trim().length<12} onClick={()=>{
        if(window.confirm('Request an INTERNAL review only? This will not approve, publish or notify staff.'))
          void act(()=>requestInternalReview(periodId,versionId,requestNote),'Internal review request saved. The schedule remains a DRAFT.')
      }}>Request internal review</button><span>Outstanding issues do not disappear when a review is requested.</span></div>
    </section>

    <section className="surface phase14-card">
      <div className="panel-heading"><div><h2>2 · Internal review queue</h2><p>Review activity is logged; only “Return for changes” or “Cancel” is available in this phase.</p></div>
        <button className="outline-button" disabled={busy} onClick={()=>void act(async()=>{},'Review queue refreshed.')}><RefreshCw size={16}/> Refresh</button></div>
      {reviews.length===0?<p className="phase14-empty">No review requests yet. Submitted versions are still kept as DRAFTs.</p>
        :<div className="phase14-review-list">{reviews.map(r=><article key={r.id} className="phase14-review-row">
          <div><b>Version {drafts.find(d=>d.id===r.schedule_version_id)?.version_number??'?'}</b>
            <span className={`phase14-state ${r.state==='submitted'?'state-open':''}`}>{r.state.replaceAll('_',' ')}</span>
            <p>{r.request_note}</p><small>{new Date(r.requested_at).toLocaleString()} · {r.observed_blockers.length} blocker(s) at submission</small>
            {r.response_note&&<p><b>Feedback:</b> {r.response_note}</p>}
          </div>{r.state==='submitted'&&<div className="phase14-review-actions"><textarea className="phase13-textarea" value={replyNote} onChange={e=>setReplyNote(e.target.value)} placeholder="Concrete changes needed (12+ chars)"/>
            <button className="outline-button" disabled={busy||replyNote.trim().length<12} onClick={()=>void act(()=>respondInternalReview(r.id,'changes_requested',replyNote),'Review returned for changes. No schedule data altered.')}>Return for changes</button>
          </div>}
        </article>)}</div>}
    </section>

    <section className="surface phase14-card">
      <div className="panel-heading"><div><h2>3 · Link a faculty account securely</h2><p>Create an Auth user in Supabase → Authentication → Users, then link the Auth User UUID to one staff record.</p></div><UserRoundCheck size={23}/></div>
      <div className="phase14-account-metrics"><span>Active staff: <b>{staff.filter(s=>s.is_active).length}</b></span><span>Linked staff: <b>{staff.filter(s=>!!s.auth_user_id).length}</b></span></div>
      <div className="phase14-fields">
        <label>Unlinked staff member<select className="phase11-input" value={chosenStaff} onChange={e=>setChosenStaff(e.target.value)}><option value="">Select a member</option>
          {staff.filter(s=>s.is_active&&!s.auth_user_id).map(s=><option key={s.id} value={s.id}>{s.source_ref} — {s.full_name}</option>)}
        </select></label>
        <label>Supabase Auth User ID (UUID)<input className="phase11-input" value={staffAuthId} onChange={e=>setStaffAuthId(e.target.value.trim())} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"/></label>
      </div>
      <label className="phase14-label">Authorized reason for account linking
        <textarea className="phase13-textarea" value={linkReason} onChange={e=>setLinkReason(e.target.value)} placeholder="Account verified for this staff member by examination administration..."/></label>
      <div className="phase14-actions"><button className="primary-button" disabled={busy||!chosenStaff||!(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(staffAuthId))||linkReason.trim().length<12}
        onClick={()=>{if(window.confirm('Have you verified the Auth User ID belongs to THIS staff member?'))void act(()=>linkStaffAccount(chosenStaff,staffAuthId,linkReason),'Account linked. The staff member can sign in, but can see only PUBLISHED duties.') }}>Link verified account</button>
        <span>No passwords or service-role secrets are entered here. This does not publish a schedule.</span></div>
    </section>
  </div>
}
