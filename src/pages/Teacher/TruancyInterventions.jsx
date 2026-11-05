import Modal from '../../components/Common/Modal';
import PageHeading from '../../components/Common/PageHeading';
import RequestFeedback from '../../components/Common/RequestFeedback';
import usePagination from '../../hooks/usePagination';
import Pagination from '../../components/Common/Pagination';
import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function TruancyInterventions() {
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(null);
  const { showError, showSuccess } = useToast();
  const [request, setRequest] = useState({ loading: true, error: '' });
  const load = useCallback(() => { setRequest({ loading: true, error: '' }); return api.get('/interventions?days=90&threshold=5').then(data => { setStudents(data); setRequest({ loading: false, error: '' }); }).catch(err => setRequest({ loading: false, error: err.message })); }, []);
  useEffect(() => { load(); }, [load]);
  const paging = usePagination(students, students.map(item=>item.person.id).join('|'));
  return <div className="page-stack animate-fade-in"><PageHeading title="Attendance interventions" description="Review learners with five or more absences in the last 90 days and record follow-up actions." /><RequestFeedback {...request} label="attendance interventions" onRetry={load} />{!request.loading && !request.error && <>{students.length === 0 && <div className="card-static empty-state"><p>No student currently meets the configured five-absence review threshold.</p></div>}{paging.items.map((item) => <section key={item.person.id} className="card-static"><div className="section-heading"><div><h2>{item.person.full_name}</h2><p>{item.person.lrn || item.person.external_id} · Grade {item.person.grade} — {item.person.section}</p></div><span className="tag tag-danger">{item.absence_count} absences</span></div><div className="action-row"><span className="status-inline"> Last absence: {item.last_absence}</span><span className="status-inline"> {item.person.guardian_phone || 'No guardian phone recorded'}</span><button className="btn-secondary" onClick={() => setSelected(item)}> Log intervention</button></div><h3 className="subheading">Intervention history</h3>{item.logs.length === 0 ? <p className="muted-small">No intervention has been logged.</p> : <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Date</th><th>Type</th><th>Authorized actor</th><th>Note</th></tr></thead><PaginatedBody>{item.logs.map((log) => <tr key={log.id}><td>{new Date(log.created_at).toLocaleString('en-PH')}</td><td>{log.intervention_type}</td><td>{log.actor_name}</td><td>{log.note}</td></tr>)}</PaginatedBody></table></div>}</section>)}<Pagination {...paging} label="learners" /></>}{selected && <InterventionModal student={selected.person} onClose={() => setSelected(null)} onSaved={async () => { setSelected(null); await load(); }} showError={showError} showSuccess={showSuccess} />}</div>;
}

function InterventionModal({ student, onClose, onSaved, showError, showSuccess }) {
  const [type, setType] = useState('Parent Conference');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event) => { event.preventDefault(); if (saving) return; setSaving(true); setError(''); try { await api.post('/interventions', { person_id: student.id, intervention_type: type, note }); showSuccess('Intervention logged.'); await onSaved(); } catch (err) { setError(err.message); showError(err.message); } finally { setSaving(false); } };
  return <Modal onClose={onClose} label="Log attendance intervention" busy={saving}><form className="modal-card" onSubmit={submit}><div className="modal-header"><div><p className="eyebrow">Attributable intervention record</p><h2>{student.full_name}</h2></div><button type="button" className="text-control" disabled={saving} onClick={onClose}><span className="control-label">Close</span></button></div><label><span className="field-label">Intervention type</span><select className="input-field" value={type} onChange={(e) => setType(e.target.value)}><option>Parent Conference</option><option>Home Visitation</option><option>Guidance Referral</option><option>Written Notice</option><option>Other Follow-up</option></select></label><label><span className="field-label">Factual notes and outcome</span><textarea placeholder="Enter factual notes and outcome" className="text-area" value={note} onChange={(e) => setNote(e.target.value)} /></label>{error && <p className="error-text" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="btn-secondary" disabled={saving} onClick={onClose}>Cancel</button><button className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save intervention log'}</button></div></form></Modal>;
}
