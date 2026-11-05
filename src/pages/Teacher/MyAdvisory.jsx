import PaginatedBody from '../../components/Common/PaginatedBody';
import { useEffect, useMemo, useState } from 'react';
import PageHeading from '../../components/Common/PageHeading';
import RequestFeedback from '../../components/Common/RequestFeedback';
import StudentProfileModal from '../../components/Teacher/StudentProfileModal';
import { api, displayTime, localDate } from '../../api/client';
import { buildTeacherRosters } from '../../services/teacherRoster';

export default function MyAdvisory() {
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [students, setStudents] = useState([]);
  const [advisorySections, setAdvisorySections] = useState([]);
  const [studentGroup, setStudentGroup] = useState('advisory');
  const [sectionFilter, setSectionFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [request, setRequest] = useState({ loading: true, error: '' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRequest({ loading: true, error: '' });
    Promise.all([
      api.get('/persons?role=Student&scope=assigned'),
      api.get('/my/advisory-sections'),
      api.get(`/attendance?date=${localDate()}&scope=assigned`),
    ]).then(([people, sections, attendance]) => {
      if (cancelled) return;
      setAdvisorySections(sections);
      if (!sections.length) setStudentGroup('teaching');
      setStudents(people.map((person) => ({
        ...person,
        name: person.full_name,
        attendance: attendance.find((row) => row.person_id === person.id),
      })));
      setRequest({ loading: false, error: '' });
    }).catch((err) => { if (!cancelled) setRequest({ loading: false, error: err.message }); });
    return () => { cancelled = true; };
  }, [attempt]);

  const rosters = useMemo(() => buildTeacherRosters(students, advisorySections), [students, advisorySections]);
  const activeGroup = advisorySections.length ? studentGroup : 'teaching';
  const groupRoster = rosters[activeGroup];

  const availableSections = useMemo(() => {
    const seen = new Map();
    groupRoster.forEach((student) => {
      if (!student.grade && !student.section) return;
      const key = `${student.grade || ''}::${student.section || ''}`;
      if (!seen.has(key)) {
        seen.set(key, {
          key,
          label: `Grade ${student.grade || '—'} — ${student.section || '—'}`,
        });
      }
    });
    return [...seen.values()];
  }, [groupRoster]);

  const activeSectionFilter = availableSections.some((item) => item.key === sectionFilter) ? sectionFilter : 'all';

  const sectionFilteredRoster = useMemo(() => {
    if (activeSectionFilter === 'all') return groupRoster;
    return groupRoster.filter((student) => `${student.grade || ''}::${student.section || ''}` === activeSectionFilter);
  }, [groupRoster, activeSectionFilter]);

  const normalizeStatus = (student) => {
    const raw = student.attendance?.status;
    if (raw === 'Present' || raw === 'Time Out') return 'present';
    if (raw === 'Late') return 'late';
    if (raw === 'Absent') return 'absent';
    if (raw === 'Excused') return 'excused';
    if (student.attendance?.time_in) return 'present';
    return 'noscan';
  };

  const counts = useMemo(() => {
    const summary = { total: sectionFilteredRoster.length, present: 0, late: 0, absent: 0, noscan: 0 };
    sectionFilteredRoster.forEach((student) => {
      const bucket = normalizeStatus(student);
      if (bucket === 'present' || bucket === 'excused') summary.present += 1;
      else if (bucket === 'late') summary.late += 1;
      else if (bucket === 'absent') summary.absent += 1;
      else summary.noscan += 1;
    });
    return summary;
  }, [sectionFilteredRoster]);

  const roster = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return sectionFilteredRoster.filter((student) => {
      if (statusFilter !== 'all' && normalizeStatus(student) !== statusFilter) return false;
      if (!normalizedQuery) return true;
      return `${student.full_name} ${student.lrn || ''} ${student.external_id || ''} ${student.grade || ''} ${student.section || ''}`
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [sectionFilteredRoster, statusFilter, query]);

  const advisoryHeadingLabel = advisorySections.length
    ? advisorySections.map((item) => `Grade ${item.grade} — ${item.section}`).join(' · ')
    : '';

  return (
    <div className="page-stack animate-fade-in">
      <PageHeading title="My advisory" description="Review assigned learners, today's attendance, and guardian contact details." />
      <RequestFeedback {...request} label="your learners" onRetry={() => setAttempt((value) => value + 1)} />

      {!request.loading && !request.error && (
        <>
          <dl className="advisory-summary-grid" aria-label="Assigned learner attendance summary">
            <div className="advisory-summary-card">
              <dt>{activeGroup === 'advisory' ? 'Advisory learners' : 'Assigned learners'}</dt>
              <dd>{counts.total}</dd>
            </div>
            <div className="advisory-summary-card is-present">
              <dt>Present today</dt>
              <dd>{counts.present}</dd>
            </div>
            <div className="advisory-summary-card is-late">
              <dt>Late today</dt>
              <dd>{counts.late}</dd>
            </div>
            <div className="advisory-summary-card is-absent">
              <dt>Absent / no scan</dt>
              <dd>{counts.absent + counts.noscan}</dd>
            </div>
          </dl>

          <section className="card-static setup-card advisory-roster-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">{activeGroup === 'advisory' ? 'Advisory class roster' : 'Subject class roster'}</p>
                <h2>
                  {activeGroup === 'advisory'
                    ? (advisoryHeadingLabel ? `Advisory — ${advisoryHeadingLabel}` : 'Advisory students')
                    : 'Students I teach'}
                </h2>
                <p className="section-copy">
                  Select any learner row to inspect their full profile, gate scan timestamps, and guardian phone number.
                </p>
              </div>
              <span className="setup-count-badge">
                {roster.length} of {sectionFilteredRoster.length} {sectionFilteredRoster.length === 1 ? 'learner' : 'learners'}
              </span>
            </div>

            <div className="setup-form-panel advisory-toolbar">
              <div className="form-grid three-columns">
                <label>
                  <span className="field-label">Student group</span>
                  <select
                    className="input-field"
                    aria-label="Student group"
                    value={activeGroup}
                    onChange={(event) => {
                      setStudentGroup(event.target.value);
                      setSectionFilter('all');
                      setStatusFilter('all');
                    }}
                  >
                    {advisorySections.length > 0 && <option value="advisory">Advisory Students</option>}
                    <option value="teaching">Students I Teach</option>
                  </select>
                </label>

                <label>
                  <span className="field-label">Class section</span>
                  <select
                    className="input-field"
                    aria-label="Class section"
                    value={activeSectionFilter}
                    onChange={(event) => setSectionFilter(event.target.value)}
                  >
                    <option value="all">All assigned sections ({availableSections.length})</option>
                    {availableSections.map((section) => (
                      <option key={section.key} value={section.key}>{section.label}</option>
                    ))}
                  </select>
                </label>

                <label>
                  <span className="field-label">Find a learner</span>
                  <div className="search-box">
                    <input
                      className="input-field"
                      placeholder="Surname, name or LRN"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </div>
                </label>
              </div>

              <div className="academic-filter-bar" role="group" aria-label="Filter learners by today's attendance status">
                {[
                  ['all', 'All statuses', counts.total],
                  ['present', 'Present', counts.present],
                  ['late', 'Late', counts.late],
                  ['absent', 'Absent', counts.absent],
                  ['noscan', 'No scan', counts.noscan],
                ].map(([id, label, count]) => (
                  <button
                    key={id}
                    type="button"
                    className={`academic-filter-pill${statusFilter === id ? ' is-active' : ''}`}
                    aria-pressed={statusFilter === id}
                    onClick={() => setStatusFilter(id)}
                  >
                    <span>{label}</span>
                    <span className="academic-filter-pill__count">{count}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="table-scroll">
              <table className="interactive-table setup-table">
                <thead>
                  <tr>
                    <th>Student name</th>
                    <th>LRN / ID</th>
                    <th>Grade &amp; section</th>
                    <th>Today</th>
                    <th>Parent contact</th>
                    <th className="action-col">Actions</th>
                  </tr>
                </thead>
                <PaginatedBody resetKey={`${query}|${activeGroup}|${activeSectionFilter}|${statusFilter}`}>
                  {roster.length === 0 && (
                    <tr>
                      <td colSpan="6" className="empty-cell">
                        {query || statusFilter !== 'all' || activeSectionFilter !== 'all'
                          ? 'No students match your current filter or search.'
                          : activeGroup === 'advisory'
                            ? 'No students are assigned to your advisory section. Ask an administrator to check your advisory assignment.'
                            : 'No students are in your assigned classes outside your advisory. Ask an administrator to check your current-year subject assignments.'}
                      </td>
                    </tr>
                  )}
                  {roster.map((student) => {
                    const statusLabel = student.attendance?.status || 'No scan';
                    const tagClass = statusLabel === 'Absent'
                      ? 'tag-danger'
                      : statusLabel === 'Late'
                        ? 'tag-warning'
                        : student.attendance?.time_in || statusLabel === 'Present'
                          ? 'tag-success'
                          : 'tag-gray';
                    return (
                      <tr key={student.id} onClick={() => setSelectedStudent(student)}>
                        <td>
                          <strong>{student.full_name}</strong>
                          {student.enrollment_status && student.enrollment_status !== 'Regular' && (
                            <span className="table-subline">{student.enrollment_status}</span>
                          )}
                        </td>
                        <td className="advisory-mono-cell">{student.lrn || student.external_id || '—'}</td>
                        <td>Grade {student.grade || '—'} — {student.section || '—'}</td>
                        <td>
                          <span className={`tag ${tagClass}`}>{statusLabel}</span>
                          {student.attendance?.time_in && (
                            <span className="table-subline">
                              In: {displayTime(student.attendance.time_in)}
                              {student.attendance.time_out ? ` · Out: ${displayTime(student.attendance.time_out)}` : ''}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className={student.guardian_phone ? 'advisory-phone-text' : 'advisory-phone-muted'}>
                            {student.guardian_phone || 'Not recorded'}
                          </span>
                        </td>
                        <td className="action-col">
                          <button
                            type="button"
                            className="btn-secondary advisory-detail-btn"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedStudent(student);
                            }}
                          >
                            View details
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </PaginatedBody>
              </table>
            </div>
          </section>
        </>
      )}

      <StudentProfileModal student={selectedStudent} onClose={() => setSelectedStudent(null)} />
    </div>
  );
}
