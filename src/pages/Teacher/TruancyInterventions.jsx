import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Phone, Calendar, Plus, X } from 'lucide-react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function TruancyInterventions() {
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(null);
  const { showError, showSuccess } = useToast();
  const load = useCallback(() => api.get('/interventions?days=90&threshold=5').then(setStudents).catch((err) => showError(err.message)), [showError]);
  useEffect(() => { load(); }, [load]);
  return <div className="page-stack animate-fade-in">{students.length === 0 && <div className="card-static empty-state"><AlertTriangle size={32} /><p>No student currently meets the configured five-absence review threshold.</p></div>}{students.map((item) => <section key={item.person.id} className="card-static" style={{ borderLeft: '4px solid var(--danger)' }}><div className="section-heading"><div><h2>{item.person.full_name}</h2><p>{item.person.lrn || item.person.external_id} · Grade {item.person.grade} — {item.person.section}</p></div><span className="tag tag-danger">{item.absence_count} absences</span></div><div className="action-row"><span className="status-inline"><Calendar size={15} /> Last absence: {item.last_absence}</span><span className="status-inline"><Phone size={15} /> {item.person.guardian_phone || 'No guardian phone recorded'}</span><button className="btn-secondary" onClick={() => setSelected(item)}><Plus size={15} /> Log intervention</button></div><h3 className="subheading">Intervention history</h3>{item.logs.length === 0 ? <p className="muted-small">No intervention has been logged.</p> : <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Date</th><th>Type</th><th>Authorized actor</th><th>Note</th></tr></thead><tbody>{item.logs.map((log) => <tr key={log.id}><td>{new Date(log.created_at).toLocaleString('en-PH')}</td><td>{log.intervention_type}</td><td>{log.actor_name}</td><td>{log.note}</td></tr>)}</tbody></table></div>}</section>)}{selected && <InterventionModal student={selected.person} onClose={() => setSelected(null)} onSaved={async () => { setSelected(null); await load(); }} showError={showError} showSuccess={showSuccess} />}</div>;
}

function InterventionModal({ student, onClose, onSaved, showError, showSuccess }) {
  const [type, setType] = useState('Parent Conference');
  const [note, setNote] = useState('');
  const submit = async (event) => { event.preventDefault(); try { await api.post('/interventions', { person_id: student.id, intervention_type: type, note }); showSuccess('Intervention logged.'); await onSaved(); } catch (err) { showError(err.message); } };
  return <div className="modal-backdrop"><form className="modal-card" onSubmit={submit}><div className="modal-header"><div><p className="eyebrow">Attributable intervention record</p><h2>{student.full_name}</h2></div><button type="button" className="icon-btn" onClick={onClose}><X size={20} /><span className="control-label">Close</span></button></div><label><span className="field-label">Intervention type</span><select className="input-field" value={type} onChange={(e) => setType(e.target.value)}><option>Parent Conference</option><option>Home Visitation</option><option>Guidance Referral</option><option>Written Notice</option><option>Other Follow-up</option></select></label><label><span className="field-label">Factual notes and outcome</span><textarea placeholder="Enter factual notes and outcome" className="text-area" value={note} onChange={(e) => setNote(e.target.value)} /></label><div className="modal-actions"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary">Save intervention log</button></div></form></div>;
}
