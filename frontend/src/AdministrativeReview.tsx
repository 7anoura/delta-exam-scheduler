import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, ClipboardCheck, RefreshCw, ShieldCheck } from './ui/DeltaIcons'
import { getAdministration, getDraftReadiness, getDrafts, recordAdminDecision,
  type AdministrationOverview, type ReadinessReport } from './api'
import type { ScheduleDraft } from './types'

export default function AdministrativeReview({periodId,onChange}:{periodId:string;onChange:()=>void}){
  const [data,setData]=useState<AdministrationOverview|null>(null)
  const [versions,setVersions]=useState<ScheduleDraft[]>([])
  const [versionId,setVersionId]=useState('')
  const [report,setReport]=useState<ReadinessReport|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const [decisionStaff,setDecisionStaff]=useState('')
  const [eligible,setEligible]=useState(true)
  const [dailyHours,setDailyHours]=useState('5')
  const [dailyReason,setDailyReason]=useState('')
  const [eligibilityReason,setEligibilityReason]=useState('')
  const [sourceName,setSourceName]=useState('Final Mid Term Exam Fall 2026-2027(1).pdf')
  const [sourceReason,setSourceReason]=useState('')
  const [sourceConfirmed,setSourceConfirmed]=useState(false)
  async function reload(){
    const [a,v]=await Promise.all([getAdministration(periodId),getDrafts(periodId)])
    setData(a);setVersions(v);setVersionId(old=>v.some(d=>d.id===old)?old:v[0]?.id??'')
  }
  useEffect(()=>{
    let ok=true
    Promise.all([getAdministration(periodId),getDrafts(periodId)]).then(([a,v])=>{
      if(!ok)return
      setData(a);setVersions(v);setVersionId(v[0]?.id??'');setReport(null)
    }).catch(e=>{if(ok)setError(String(e))})
    return ()=>{ok=false}
  },[periodId])
  async function transact(action:()=>Promise<unknown>){
    setBusy(true);setMessage('');setError('');setReport(null)
    try{await action();await reload();onChange();setMessage('Administrative decision recorded. Revalidate the current draft before further action.')}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  async function verify(){if(!versionId)return
    setBusy(true);setMessage('');setError('')
    try{setReport(await getDraftReadiness(periodId,versionId))}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  return <section className="phase13-section" aria-label="Administrative approval preparation">
    <div className="phase13-title">
      <span className="phase13-icon"><ShieldCheck size={22}/></span><div><h2>Administrative Decisions & Final Validation</h2>
      <p>Record authorized university rules, then audit the actual SAVED draft. This is not an approval or publishing screen.</p></div>
      <span className="pill pill-warn">Drafts only</span>
    </div>
    {error&&<div className="phase11-message phase11-error" role="alert"><AlertCircle size={17}/>{error}</div>}
    {message&&<div className="phase11-message phase11-success" role="status"><CheckCircle2 size={17}/>{message}</div>}
    <div className="phase13-cards">
      <div className="surface phase13-card">
        <h3>1 · Assistant Lecturer chair eligibility</h3>
        <p>Change eligibility ONLY if your faculty has formally authorized that person to chair exams.</p>
        <label>Staff member
          <select className="phase11-input" value={decisionStaff} onChange={e=>setDecisionStaff(e.target.value)}>
            <option value="">Select Assistant Lecturer</option>
            {data?.assistant_lecturers.map(s=><option key={s.id} value={s.id}>{s.source_ref} — {s.full_name} ({s.can_chair?'enabled':'disabled'})</option>)}
          </select></label>
        <label>Faculty decision
          <select className="phase11-input" value={String(eligible)} onChange={e=>setEligible(e.target.value==='true')}>
            <option value="true">Authorize chair eligibility</option><option value="false">Revoke chair eligibility</option>
          </select></label>
        <label>Official justification / reference
          <textarea className="phase13-textarea" value={eligibilityReason} onChange={e=>setEligibilityReason(e.target.value)} placeholder="Faculty approval reference, authority, and date"/>
        </label>
        <button className="primary-button" disabled={busy||!decisionStaff||eligibilityReason.trim().length<12} onClick={()=>{
          if(window.confirm('Confirm that the faculty has officially authorized this eligibility decision?'))
            void transact(()=>recordAdminDecision(periodId,{kind:'chair_eligibility',staff_id:decisionStaff,can_chair:eligible,reason:eligibilityReason}))
        }}>Record faculty decision</button>
      </div>
      <div className="surface phase13-card">
        <h3>2 · Maximum daily invigilation hours</h3>
        <p>Current rule: {data?.max_daily_minutes==null?'Not set':`${data.max_daily_minutes} minutes`}. Enter the official limit.</p>
        <label>Hours (0.75 – 12)
          <input className="phase11-input" inputMode="decimal" type="number" min="0.75" max="12" step="0.25" value={dailyHours} onChange={e=>setDailyHours(e.target.value)}/></label>
        <label>Official justification / reference
          <textarea className="phase13-textarea" value={dailyReason} onChange={e=>setDailyReason(e.target.value)} placeholder="Faculty rule/reference and who authorized it"/></label>
        <button className="primary-button" disabled={busy||dailyReason.trim().length<12||!(Number(dailyHours)>=.75&&Number(dailyHours)<=12)} onClick={()=>{
          if(window.confirm('Confirm that this is the authorized DAILY limit, not an estimated number?'))
            void transact(()=>recordAdminDecision(periodId,{kind:'daily_limit',max_daily_minutes:Math.round(Number(dailyHours)*60),reason:dailyReason}))
        }}>Record official limit</button>
      </div>
      <div className="surface phase13-card">
        <h3>3 · Source PDF sign-off</h3>
        <p>{data?.source_attestation ? `${data.source_attestation.matches_live_source?'Current signed-off source':'Source changed — sign-off expired'}: ${data.source_attestation.document_name}` : 'No staff member has attested that the source timetable matches the imported records.'}</p>
        <label>Reviewed PDF filename
          <input className="phase11-input" value={sourceName} onChange={e=>setSourceName(e.target.value)}/></label>
        <label>Review notes / reference
          <textarea className="phase13-textarea" value={sourceReason} onChange={e=>setSourceReason(e.target.value)} placeholder="I manually compared every course, session, date, room and student count to the official PDF; review record..."/></label>
        <label className="phase13-checkbox"><input type="checkbox" checked={sourceConfirmed} onChange={e=>setSourceConfirmed(e.target.checked)}/>
          I personally checked the official PDF against the imported timetable. This is a real human attestation.</label>
        <button className="primary-button" disabled={busy||!sourceConfirmed||sourceReason.trim().length<12||!sourceName.trim()} onClick={()=>{
          if(window.confirm('This records YOUR attestation of completed manual source verification. Proceed?'))
            void transact(()=>recordAdminDecision(periodId,{kind:'source_signoff',checked_original_document:true,source_name:sourceName,reason:sourceReason}))
        }}>Record source review</button>
      </div>
    </div>
    <div className="surface phase13-validation">
      <div className="phase13-validation-header"><div><h3>4 · Validate a saved schedule version</h3>
        <p>Re-reads ALL saved duties and chairs from Supabase, checking against CURRENT roles and rules.</p></div>
        <span className="pill pill-warn">Approval & publishing unavailable</span></div>
      <div className="phase13-actions">
        <select className="phase11-input" value={versionId} onChange={e=>{setVersionId(e.target.value);setReport(null)}}>
          {versions.map(v=><option key={v.id} value={v.id}>Version {v.version_number} · {v.status.toUpperCase()}</option>)}
        </select>
        <button className="primary-button" disabled={busy||!versionId} onClick={()=>void verify()}>
          {busy?<RefreshCw size={16} className="spin"/>:<ClipboardCheck size={16}/>} Run final validation</button>
        <button className="outline-button" disabled={busy} onClick={()=>void reload()}>Refresh</button>
      </div>
      {report&&<div className="phase13-report">
        <div className={`phase11-message ${report.ready_for_formal_review?'phase11-success':'phase11-error'}`}>
          {report.ready_for_formal_review?<CheckCircle2 size={18}/>:<AlertCircle size={18}/>}
          Version {report.version_number}: {report.ready_for_formal_review?'Passed automated checks — requires formal review':'NOT READY — blockers found'}. Nothing has been approved or published.
        </div>
        <div className="phase13-metrics"><span>{report.checks.room_sittings} room sittings</span><span>{report.checks.invigilator_duties} duties</span><span>{report.checks.chair_assignments}/{report.checks.course_exams} chairs</span></div>
        {report.issues.length>0?<div className="phase13-issues">{report.issues.map(i=><div key={i.code}><AlertCircle size={15}/><div><strong>{i.code.replaceAll('_',' ')}</strong><p>{i.message}</p></div></div>)}</div>:<p className="fine-print">All implemented automatic checks passed. Human decisions and independent faculty verification are still required.</p>}
      </div>}
    </div>
    <p className="phase13-notice">Existing Version 3 still has 58/59 course chairs. Recording new eligibility does NOT fix that draft: regenerate and save a NEW full chair plan, then revalidate. No existing versions are overwritten.</p>
  </section>
}
