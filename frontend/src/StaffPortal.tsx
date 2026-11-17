/* DELTA_UNIVERSITY_PRODUCTION_VISUAL_V1 */
import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CalendarDays, LogOut, RefreshCw, ShieldCheck } from './ui/DeltaIcons'
import { getPersonalPublishedSchedule, type Me, type PersonalSchedule } from './api'

export default function StaffPortal({me,logout}:{me:Me;logout:()=>void}) {
  const [data,setData]=useState<PersonalSchedule|null>(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)
  async function refresh(){setLoading(true);setError('');try{setData(await getPersonalPublishedSchedule())}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setLoading(false)}}
  useEffect(()=>{void refresh()},[])
  const grouped=useMemo(()=>{
    const map=new Map<string,NonNullable<PersonalSchedule['duties']>>()
    for(const duty of data?.duties??[])map.set(duty.date,[...(map.get(duty.date)??[]),duty])
    return [...map.entries()].sort(([a],[b])=>a.localeCompare(b))
  },[data])
  return <div className="staff-shell">
    <header className="staff-header"><div className="brand delta-staff-brand"><img className="delta-university-logo" src="/delta-university-logo.png" alt="Delta University logo"/><div className="delta-brand-caption"><strong>Delta Exam Scheduler</strong><small>Personal published duties</small></div></div>
      <button className="outline-button" onClick={logout}><LogOut size={16}/> Sign out</button></header>
    <main className="staff-content phase14-portal">
      <span className="eyebrow">SECURE STAFF PORTAL · PUBLISHED ONLY</span><h1>Welcome, {me.full_name||me.email}</h1>
      <p>Your personal examination schedule. Unpublished drafts and internal review requests are never shown here.</p>
      <div className="phase14-portal-top"><div><ShieldCheck size={18}/> Authenticated faculty account</div>
        <button className="outline-button" disabled={loading} onClick={()=>void refresh()}><RefreshCw size={16} className={loading?'spin':''}/> Refresh</button></div>
      {error&&<div className="phase11-message phase11-error" role="alert"><AlertCircle size={18}/>{error}</div>}
      <div className="phase14-portal-stats"><div className="surface"><span>Published duties</span><strong>{data?.total_duties??0}</strong></div>
        <div className="surface"><span>Working days</span><strong>{data?.total_days??0}</strong></div>
        <div className="surface"><span>Total duty time</span><strong>{data?`${Math.floor(data.total_minutes/60)}h ${data.total_minutes%60}m`:'—'}</strong></div></div>
      <section className="surface phase14-card"><div className="panel-heading"><div><h2>My published schedule</h2><p>Dates and times are shown in Egypt local time (Africa/Cairo).</p></div><CalendarDays size={20}/></div>
        {loading?<p className="phase14-empty">Loading published duties...</p>:
         grouped.length===0?<div className="phase14-empty"><ShieldCheck size={24}/><strong>No published duties yet.</strong><p>Your faculty has not published a schedule. Drafts cannot be viewed in this account.</p></div>:
         grouped.map(([date,duties])=><div className="phase14-day" key={date}><h3>{date}</h3><div className="table-scroll"><table>
           <thead><tr><th>Time</th><th>Role</th><th>Course(s)</th><th>Room</th><th>Exam period</th></tr></thead>
           <tbody>{duties.map((d,i)=><tr key={`${date}-${i}`}><td>{d.start}–{d.end}</td><td>{d.type==='committee_chair'?'Committee Chair':'Invigilator'}</td><td>{d.course_codes.join(', ')||'—'}</td><td>{d.room_code??'Multiple rooms'} {d.room_number?`(${d.room_number})`:''}</td><td>{d.period}</td></tr>)}</tbody>
         </table></div></div>)}
      </section><p className="phase14-footer">Only the approved faculty process can publish schedules. Contact Exam Control if a published duty needs correction.</p>
    </main>
  </div>
}
