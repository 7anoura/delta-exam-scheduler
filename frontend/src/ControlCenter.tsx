import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, RefreshCw, ShieldCheck, Sparkles, Save, Users2 } from './ui/DeltaIcons'
import { appointControlHead, getControl, getDrafts, getSavedChairs, previewChairs, saveChairDraft,
         type ChairPreview, type ControlOverview } from './api'
import type { Audit, ScheduleDraft, Snapshot } from './types'
import ResolutionLab from './ResolutionLab'
import AdministrativeReview from './AdministrativeReview'

type ChairRow = {exam_id:string; code:string; title:string}

export default function ControlCenter({ periodId, audit, snapshot, onChange }:
    {periodId:string; audit:Audit; snapshot:Snapshot; onChange:()=>void}) {
  const [overview, setOverview] = useState<ControlOverview|null>(null)
  const [drafts, setDrafts] = useState<ScheduleDraft[]>([])
  const [versionId, setVersionId] = useState('')
  const [headId, setHeadId] = useState('')
  const [plan, setPlan] = useState<ChairPreview|null>(null)
  const [selection,setSelection] = useState<Record<string,string>>({})
  const [note,setNote] = useState('')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [success,setSuccess] = useState('')
  const [search,setSearch] = useState('')

  const load = useCallback(async () => {
    const [o,d] = await Promise.all([getControl(periodId), getDrafts(periodId)])
    setOverview(o);setHeadId(o.head_staff_id ?? '');setDrafts(d)
    setVersionId(id=>d.some(v=>v.id===id) ? id : d[0]?.id ?? '')
  },[periodId])
  useEffect(()=>{
    let current=true
    Promise.all([getControl(periodId),getDrafts(periodId)]).then(([o,d])=>{
      if(!current)return
      setOverview(o);setHeadId(o.head_staff_id ?? '');setDrafts(d);setVersionId(d[0]?.id??'')
    }).catch(e=>{if(current)setError(String(e))})
    return ()=>{current=false}
  },[periodId])
  const chairs = useMemo(()=>overview?.staff.filter(s=>s.eligible_for_this_plan)??[],[overview])
  const exams = useMemo(()=>snapshot.exams.map(e=>({
    code:e.code,title:e.title,exam_id:plan?.assignments.find(a=>a.code===e.code)?.exam_id
      ??plan?.unassigned_exams.find(a=>a.code===e.code)?.exam_id??'',
  })).filter(e=>e.exam_id).sort((a,b)=>a.code.localeCompare(b.code)),[plan,snapshot.exams])
  const filtered = useMemo(()=>exams.filter(e=>`${e.code} ${e.title}`.toLowerCase().includes(search.toLowerCase())),[exams,search])
  const selectedCount = Object.values(selection).filter(Boolean).length
  const missingCount = Math.max(0, snapshot.exams.length-selectedCount)
  const changedHead = !!overview && headId !== (overview.head_staff_id??'')

  async function handleHead(){
    if(!overview || !changedHead)return
    if(!window.confirm('This appointment may reduce the chair pool and invalidate existing DRAFT chair plans. Continue?'))return
    setBusy(true);setError('');setSuccess('')
    try{
      const result=await appointControlHead(periodId,headId||null)
      setPlan(null);setSelection({})
      await load();onChange()
      setSuccess(result.message)
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  }
  async function handlePreview(){
    setBusy(true);setError('');setSuccess('')
    try {
      const p=await previewChairs(periodId)
      setPlan(p)
      setSelection(Object.fromEntries(p.assignments.map(a=>[a.exam_id,a.staff_id])))
      if (p.status==='POLICY_REVIEW_REQUIRED') setError(p.reason)
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  }
  async function loadSaved(){
    if(!versionId)return
    setBusy(true);setError('');setSuccess('')
    try{
      const saved=await getSavedChairs(periodId,versionId)
      // use preview to get complete exam UUIDs and eligibility, then load persisted values
      const p=await previewChairs(periodId)
      setPlan(p)
      setSelection(Object.fromEntries(saved.chairs.map(x=>[x.exam_id,x.staff_id])))
      setSuccess(`Loaded ${saved.chair_count} saved chair assignments from version ${saved.version.version_number}.`)
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  }
  async function handleSave(){
    if(!plan||!versionId||!overview)return
    if (plan.coverage==='not_generated' || plan.status==='POLICY_REVIEW_REQUIRED') return
    if(!window.confirm(`Save ${selectedCount}/${snapshot.exams.length} chair assignments as a NEW DRAFT? No schedule will be published.`))return
    setBusy(true);setError('');setSuccess('')
    try{
      const chairs=Object.entries(selection).filter(([,id])=>id).map(([exam_id,staff_id])=>({exam_id,staff_id:String(staff_id)}))
      const saved=await saveChairDraft(periodId,versionId,chairs,note)
      await load();setVersionId(saved.version.id)
      setSuccess(`Version ${saved.version.version_number} saved. ${saved.version.chairs_saved}/${saved.version.total_exams} course chairs. Publication stays BLOCKED.`)
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  }
  return <div className="phase11-control">
    <div className="control-banner"><AlertCircle size={22}/><div>
      <strong>Exam Control · Draft management only</strong>
      <p>Appoint the Head of Control and prepare one doctor per course exam. Publication is still disabled.</p>
    </div></div>
    {error && <div role="alert" className="phase11-message phase11-error"><AlertCircle size={18}/>{error}</div>}
    {success && <div role="status" className="phase11-message phase11-success"><CheckCircle2 size={18}/>{success}</div>}
    <div className="phase11-grid">
      <section className="surface phase11-box">
        <div className="panel-heading"><div><h2>Head of Examination Control</h2><p>Administrative role above the committee chairpersons</p></div><ShieldCheck size={22}/></div>
        <label className="phase11-label">Select Faculty Head</label>
        <select className="phase11-input" value={headId} onChange={e=>setHeadId(e.target.value)} disabled={!overview||busy}>
          <option value="">Not appointed</option>
          {(overview?.staff??[]).filter(c=>c.can_chair).map(c=><option key={c.id} value={c.id}>{c.source_ref} — {c.full_name}</option>)}
        </select>
        <p className="fine-print">Default policy: the Head of Control cannot simultaneously serve as a course chair. This can increase shortages.</p>
        <button className="primary-button" onClick={handleHead} disabled={busy||!changedHead}>
          <ShieldCheck size={16}/> Save appointment
        </button>
      </section>
      <section className="surface phase11-box">
        <div className="panel-heading"><div><h2>Chair Capacity</h2><p>Distinct doctors assigned per course, not per lab</p></div><Users2 size={22}/></div>
        <div className="phase11-metrics">
          <div><span>Course exams</span><strong>{snapshot.exams.length}</strong></div>
          <div><span>Available chairs</span><strong>{chairs.length}</strong></div>
          <div><span>Lower-bound shortages</span><strong>{audit.chair_shortages.length}</strong></div>
        </div>
        <p className="fine-print">Capacity is recalculated after the Head appointment. The CP-SAT preview independently checks all course sessions.</p>
        <button className="outline-button" onClick={handlePreview} disabled={busy||!overview||!versionId}>
          {busy?<RefreshCw size={16} className="spin"/>:<Sparkles size={16}/>} Generate chair plan
        </button>
      </section>
    </div>
    <ResolutionLab key={periodId+'|'+String(overview?.head_staff_id??'none')} periodId={periodId} staff={overview?.staff??[]} currentHeadId={overview?.head_staff_id??null} currentHeadCanChair={overview?.head_can_chair??false}/>
    <section className="surface phase11-box">
      <div className="panel-heading"><div><h2>Committee Chair Plan</h2><p>Every course exam should have one assigned doctor across all its sessions.</p></div>
        <span className="phase11-chip">{plan?`${selectedCount}/${snapshot.exams.length} assigned`:'Not generated'}</span>
      </div>
      <div className="phase11-toolbar">
        <label className="phase11-label">Base on saved invigilation draft
          <select className="phase11-input" value={versionId} onChange={e=>setVersionId(e.target.value)} disabled={busy}>
            {drafts.map(d=><option value={d.id} key={d.id}>Version {d.version_number} · {d.status.toUpperCase()}</option>)}
          </select>
        </label>
        <button className="outline-button" disabled={busy||!versionId} onClick={loadSaved}>View saved chair plan</button>
        <label className="phase11-label">Find a course
          <input className="phase11-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by code or name"/>
        </label>
      </div>
      {plan ? <>
        <div className={`phase11-message ${missingCount>0?'phase11-error':'phase11-success'}`}>
          {missingCount>0 ? <AlertCircle size={18}/> : <CheckCircle2 size={18}/>}
          {missingCount} unassigned course(s). {plan.reason}
        </div>
        <div className="table-scroll phase11-scroll"><table><thead><tr><th>Course</th><th>Title</th><th>Assigned chairperson</th><th>Status</th></tr></thead>
        <tbody>{filtered.map((e:ChairRow)=>{
          const staffId=selection[e.exam_id]??''
          return <tr key={e.exam_id}><td><span className="course-code">{e.code}</span></td><td>{e.title}</td><td>
            <select className="phase11-input" disabled={busy} value={staffId} onChange={ev=>setSelection(old=>({...old,[e.exam_id]:ev.target.value}))}>
              <option value="">Unassigned (requires resolution)</option>
              {chairs.map(c=><option key={c.id} value={c.id}>{c.source_ref} — {c.full_name}</option>)}
            </select>
          </td><td>{staffId?<span className="pill pill-blue">Assigned</span>:<span className="pill pill-warn">Missing</span>}</td></tr>
        })}</tbody></table></div>
        <div className="phase11-save">
          <label className="phase11-label">Change note<input className="phase11-input" value={note} onChange={e=>setNote(e.target.value)} placeholder="Administrative review / suggested plan" maxLength={450}/></label>
          <button className="primary-button" disabled={busy||!versionId||selectedCount===0} onClick={handleSave}><Save size={17}/> Save as NEW draft version</button>
        </div>
        <p className="fine-print">The database validates ALL course sessions and approved absences atomically. A manual chair change conflicting with another course will be rejected; no existing draft is changed.</p>
      </>:<p className="fine-print padded">Choose an existing invigilation draft, then Generate chair plan. The optimizer can produce a PARTIAL plan when resources are insufficient.</p>}
    </section>
    <AdministrativeReview periodId={periodId} onChange={onChange}/>
    <section className="surface phase11-box"><div className="panel-heading"><div><h2>What remains before publication</h2><p>These are mandatory administrative checks, not software errors</p></div></div>
      {audit.issues.map(i=><div className="phase11-issue" key={i}><AlertCircle size={16}/>{i.replaceAll('_',' ')}</div>)}
      <p className="fine-print">Phase 13 records reviewed decisions and validates saved drafts. Formal approval and publishing are still unavailable.</p>
    </section>
  </div>
}
