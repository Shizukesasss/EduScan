import { useEffect, useMemo, useState } from 'react';
import { Search, Phone, MoreVertical } from 'lucide-react';
import StudentProfileModal from '../../components/Teacher/StudentProfileModal';
import { api, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { buildTeacherRosters } from '../../services/teacherRoster';

export default function MyAdvisory() {
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [students, setStudents] = useState([]);
  const [advisorySections, setAdvisorySections] = useState([]);
  const [studentGroup, setStudentGroup] = useState('advisory');
  const [query, setQuery] = useState('');
  const { showError } = useToast();

  useEffect(() => {
    Promise.all([
      api.get('/persons?role=Student&scope=assigned'),
      api.get('/my/advisory-sections'),
      api.get(`/attendance?date=${localDate()}&scope=assigned`),
    ]).then(([people, sections, attendance]) => {
      setAdvisorySections(sections);
      if (!sections.length) setStudentGroup('teaching');
      setStudents(people.map((person) => ({
        ...person,
        name: person.full_name,
        attendance: attendance.find((row) => row.person_id === person.id),
      })));
    }).catch((err) => showError(err.message));
  }, [showError]);

  const rosters = useMemo(() => buildTeacherRosters(students, advisorySections), [students, advisorySections]);
  const activeGroup = advisorySections.length ? studentGroup : 'teaching';
  const roster = useMemo(() => rosters[activeGroup].filter((student) =>
    `${student.full_name} ${student.lrn || ''}`.toLowerCase().includes(query.toLowerCase())),
  [rosters, activeGroup, query]);

  return (
    <div className="page-stack animate-fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <label style={{ width: 280, maxWidth: '100%' }}>
          <span className="field-label">Student group</span>
          <select className="input-field" aria-label="Student group" value={activeGroup} onChange={(event) => setStudentGroup(event.target.value)}>
            {advisorySections.length > 0 && <option value="advisory">Advisory Students</option>}
            <option value="teaching">Students I Teach</option>
          </select>
        </label>
        <div style={{ position: 'relative', width: 300, maxWidth: '100%' }}>
          <Search size={16} style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }} />
          <input className="input-field" style={{ paddingLeft: 40 }} aria-label="Search student surname, first name, or LRN" placeholder="Search surname, name or LRN" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
      </div>
      <div className="card-static table-scroll">
        <table className="interactive-table">
          <thead><tr><th>Student name</th><th>LRN / ID</th><th>Grade &amp; section</th><th>Today</th><th>Parent contact</th><th /></tr></thead>
          <tbody>
            {roster.length === 0 && <tr><td colSpan="6" className="empty-cell">{query ? 'No students match your search.' : activeGroup === 'advisory' ? 'No students are assigned to your advisory section. Ask an administrator to check your advisory assignment.' : 'No students are in your assigned classes outside your advisory. Ask an administrator to check your current-year subject assignments.'}</td></tr>}
            {roster.map((student) => (
              <tr key={student.id} onClick={() => setSelectedStudent(student)}>
                <td><strong>{student.full_name}</strong></td>
                <td>{student.lrn || student.external_id}</td>
                <td>Grade {student.grade} — {student.section}</td>
                <td><span className={`tag ${student.attendance?.status === 'Absent' ? 'tag-danger' : student.attendance?.status === 'Late' ? 'tag-warning' : student.attendance?.time_in ? 'tag-success' : 'tag-gray'}`}>{student.attendance?.status || 'No scan'}</span></td>
                <td><span className="status-inline"><Phone size={14} /> {student.guardian_phone || 'Not recorded'}</span></td>
                <td><button className="icon-btn" onClick={(event) => { event.stopPropagation(); setSelectedStudent(student); }}><MoreVertical size={18} /><span className="control-label">View details</span></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <StudentProfileModal student={selectedStudent} onClose={() => setSelectedStudent(null)} />
    </div>
  );
}
