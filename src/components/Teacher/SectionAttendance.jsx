import PaginatedBody from '../Common/PaginatedBody';
import { useMemo, useState } from 'react';
import { CheckCircle, FileEdit, Search, XCircle } from 'lucide-react';
import { displayTime } from '../../api/client';

export default function SectionAttendance({ students, isLocked, onStudentClick }) {
  const [query, setQuery] = useState('');
  const visibleStudents = useMemo(() => {
    const wanted = query.trim().toLocaleLowerCase('en-PH');
    if (!wanted) return students;
    return students.filter((student) => [student.name, student.external_id, student.lrn]
      .some((value) => String(value || '').toLocaleLowerCase('en-PH').includes(wanted)));
  }, [query, students]);
  const statusClass = (status) => {
    if (status === 'Absent') return 'tag-danger';
    if (status === 'Late') return 'tag-warning';
    if (status === 'No scan') return 'tag-gray';
    return 'tag-success';
  };

  return (
    <div className="card-static animate-fade-in delay-200">
      <div className="section-heading">
        <div><p className="eyebrow">Read-only daily view</p><h2>Today’s roster & gate result</h2></div>
        <div style={{ position: 'relative', width: '300px' }}><Search size={16} style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} /><input type="search" placeholder="Search name, LRN, or ID" className="input-field" style={{ paddingLeft: '40px', background: '#f8fafc' }} value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      </div>
      <p className="section-copy">Use the Corrections page to change a record. That workflow preserves the gate event and requires an auditable reason.</p>
      <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Student</th><th>Gate evidence</th><th>Current SF2 status</th><th>Latest reason</th><th>Action</th></tr></thead><PaginatedBody resetKey={query}>
        {visibleStudents.length === 0 && <tr><td colSpan="5" className="empty-cell">No learner matches this search.</td></tr>}
        {visibleStudents.map((student) => <tr key={student.id}>
          <td className="student-cell" onClick={() => onStudentClick(student)}><strong>{student.name}</strong><span>{student.lrn || student.external_id} · {student.sex}</span></td>
          <td>{student.timeIn ? <span className="status-inline success-text"><CheckCircle size={14} /> Time in {displayTime(student.timeIn)}</span> : <span className="status-inline danger-text"><XCircle size={14} /> No time-in scan</span>}</td>
          <td><span className={`tag ${statusClass(student.override)}`}>{student.override}</span></td>
          <td>{student.remark || '—'}</td>
          <td><button className="btn-link" disabled={isLocked} onClick={() => { window.location.href = '/teacher/attendance'; }}><FileEdit size={15} /> Open correction</button></td>
        </tr>)}
      </PaginatedBody></table></div>
    </div>
  );
}
