import React, { useState, useMemo, useRef } from 'react';
import { Search, Calculator, ArrowUpDown } from 'lucide-react';
import { calculateStudentGrade } from '../../services/gradingCalculations';
import { useToast } from '../../contexts/ToastContext';
import './GradingSheet.css';

const QUARTER_LABELS = ['FIRST', 'SECOND', 'THIRD', 'FOURTH'];

const STATUS_CONFIG = {
  Draft:     { label: 'DRAFT',     cls: 'deped-status-draft' },
  Submitted: { label: 'SUBMITTED', cls: 'deped-status-submitted' },
  Finalized: { label: 'FINALIZED', cls: 'deped-status-finalized' },
  Locked:    { label: 'LOCKED',    cls: 'deped-status-locked' },
};

export default function GradingSheet({
  gradebook,
  students,
  components,
  scores,
  scoreStatuses,
  passingGrade,
  transmutationTable,
  disabled,
  onScoreChange,
  onStatusChange,
  onStudentBreakdown,
  selectors = {},
  isSeniorHigh = false,
  region,
  setRegion,
  division,
  setDivision,
  schoolId,
  setSchoolId,
}) {
  const { showError } = useToast();
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('All');
  const [sortBy, setSortBy] = useState('name');
  const inputRefs = useRef(new Map());

  // Flattened assessment items for column index tracking
  const flatItems = useMemo(() =>
    components.flatMap(c => (c.items || []).map(item => ({ ...item, componentId: c.id }))),
    [components]
  );

  // Compute active items based on live scores (an item is active if ANY student has a non-empty score or explicit status)
  const activeItemIds = useMemo(() => {
    const activeIds = new Set();
    for (const student of students) {
      const sId = String(student.person_id);
      const liveScores = scores[sId] || {};
      const liveStatuses = scoreStatuses[sId] || {};
      
      for (const item of flatItems) {
        const val = liveScores[item.id] !== undefined
          ? liveScores[item.id]
          : (student.scores?.[item.id] ?? '');
        const explicitStat = liveStatuses[item.id] || student.score_statuses?.[item.id];
        
        if (val !== '' || (explicitStat && explicitStat !== 'Missing')) {
          activeIds.add(item.id);
        }
      }
    }
    return activeIds;
  }, [students, scores, scoreStatuses, flatItems]);

  // Highest Possible Score per component (only summing active items)
  const hpsPerComponent = useMemo(() => {
    const map = {};
    for (const comp of components) {
      map[comp.id] = (comp.items || [])
        .filter(item => activeItemIds.has(item.id))
        .reduce((s, item) => s + Number(item.max_score || 0), 0);
    }
    return map;
  }, [components, activeItemIds]);

  // Compute live student data including per-component PS / WS
  const computedStudents = useMemo(() => {
    return students.map(student => {
      const sId = String(student.person_id);
      const liveScores   = scores[sId]        || {};
      const liveStatuses = scoreStatuses[sId]  || {};

      const formattedScores = flatItems.map(item => {
        const val = liveScores[item.id] !== undefined
          ? liveScores[item.id]
          : (student.scores?.[item.id] ?? '');
        const explicitStat = liveStatuses[item.id] || student.score_statuses?.[item.id];
        const stat = val === '' ? (explicitStat === 'Excused' ? 'Excused' : 'Missing') : 'Scored';
        return { itemId: item.id, score: val, status: stat };
      });

      // Per-component computed values: total raw score, PS (%), WS (weighted)
      const componentCalcs = components.map(comp => {
        const items = (comp.items || []).filter(item => activeItemIds.has(item.id));
        const hps   = hpsPerComponent[comp.id] || 0;
        let total    = 0;
        let complete = items.length > 0;

        for (const item of items) {
          const entry = formattedScores.find(f => f.itemId === item.id);
          if (!entry || entry.status !== 'Scored' || entry.score === '' || entry.score == null) {
            complete = false;
          } else {
            total += Number(entry.score);
          }
        }

        const ps = (hps > 0 && complete) ? (total / hps) * 100 : null;
        const ws = ps !== null ? ps * (comp.weight / 100) : null;

        return { compId: comp.id, total: complete ? total : null, hps, ps, ws };
      });

      const filteredComponents = components.map(c => ({
        ...c,
        items: (c.items || []).filter(item => activeItemIds.has(item.id))
      }));

      const calc = calculateStudentGrade({
        studentScores: formattedScores,
        components: filteredComponents,
        transmutationTable,
        passingGrade,
      });

      return { ...student, liveScores, liveStatuses, componentCalcs, calc };
    });
  }, [students, scores, scoreStatuses, flatItems, components, hpsPerComponent, transmutationTable, passingGrade, activeItemIds]);

  // Filter + sort
  const displayedStudents = useMemo(() => {
    let list = computedStudents.filter(s => {
      if (filterStatus === 'PASSED'     && s.calc.status !== 'PASSED')     return false;
      if (filterStatus === 'FAILED'     && s.calc.status !== 'FAILED')     return false;
      if (filterStatus === 'INCOMPLETE' && s.calc.status !== 'INCOMPLETE') return false;
      if (!search.trim()) return true;
      const term = search.toLowerCase();
      return s.full_name.toLowerCase().includes(term)
        || (s.lrn         && s.lrn.toLowerCase().includes(term))
        || (s.external_id && s.external_id.toLowerCase().includes(term));
    });

    if (sortBy === 'grade') {
      list.sort((a, b) => (b.calc.reportedGrade || 0) - (a.calc.reportedGrade || 0));
    } else {
      list.sort((a, b) => a.full_name.localeCompare(b.full_name));
    }

    return list;
  }, [computedStudents, filterStatus, search, sortBy]);

  // Group by sex: Male first, Female second, then other
  const groupedStudents = useMemo(() => {
    const isMale   = s => (s.sex || '').toUpperCase().startsWith('M');
    const isFemale = s => (s.sex || '').toUpperCase().startsWith('F');

    const males   = displayedStudents.filter(isMale);
    const females = displayedStudents.filter(isFemale);
    const others  = displayedStudents.filter(s => !isMale(s) && !isFemale(s));

    const groups = [
      { label: 'MALE',   students: males },
      { label: 'FEMALE', students: females },
      ...(others.length > 0 ? [{ label: 'OTHER', students: others }] : []),
    ];

    // Pre-assign displayNum (1-based row counter within gender) and navIdx (0-based keyboard-nav index)
    let navIdx = 0;
    return groups
      .filter(g => g.students.length > 0)
      .map(g => {
        let displayNum = 0;
        return {
          label: g.label,
          students: g.students.map(s => ({ ...s, displayNum: ++displayNum, navIdx: navIdx++ })),
        };
      });
  }, [displayedStudents]);

  const totalNavRows = displayedStudents.length;

  // Column count for the empty-state row colspan
  const totalColSpan = 2
    + components.reduce((sum, c) => sum + (c.items || []).length + 3, 0)
    + 3; // Initial + Quarterly + Action

  // Keyboard navigation
  const handleKeyDown = (e, navRowIdx, colIdx) => {
    if (e.key.length === 1 && !/^[0-9.]$/.test(e.key)) {
      e.preventDefault();
      showError('Please enter a valid number. Letters and symbols are not allowed.');
      return;
    }

    let nextRow = navRowIdx;
    let nextCol = colIdx;

    if (e.key === 'ArrowDown' || e.key === 'Enter') {
      e.preventDefault();
      nextRow = Math.min(totalNavRows - 1, navRowIdx + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      nextRow = Math.max(0, navRowIdx - 1);
    } else if (e.key === 'ArrowRight' && e.target.selectionStart === e.target.value.length) {
      if (colIdx < flatItems.length - 1) nextCol = colIdx + 1;
    } else if (e.key === 'ArrowLeft' && e.target.selectionStart === 0) {
      if (colIdx > 0) nextCol = colIdx - 1;
    }

    if (nextRow !== navRowIdx || nextCol !== colIdx) {
      const target = inputRefs.current.get(`${nextRow}-${nextCol}`);
      if (target) { target.focus(); target.select(); }
    }
  };

  // Derived header values
  const quarterLabel = gradebook?.quarter
    ? `${QUARTER_LABELS[(gradebook.quarter - 1)] || gradebook.quarter} QUARTER`
    : 'QUARTER';
  const statusCfg = STATUS_CONFIG[gradebook?.status] || STATUS_CONFIG.Draft;

  return (
    <section className="deped-class-record">

      {/* â• â•  DepEd Class Record Header Block â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•  */}
      <div className="deped-header-block">

        {/* Title row */}
        <div className="deped-header-top">
          <div style={{ width: '90px', flexShrink: 0 }}></div> {/* Spacer to center the title */}
          <div className="deped-header-center">
            <div className="deped-header-title">Class Record</div>
            <div className="deped-header-subtitle">(Pursuant to DepEd Order #8, s.2015)</div>
          </div>
          <div className="deped-header-right">
            <div className={`deped-status-badge ${statusCfg.cls}`}>{statusCfg.label}</div>
          </div>
        </div>

        {/* School info rows */}
        <table className="deped-info-table">
          <tbody>
            <tr>
              <th>REGION</th>
              <td>
                <input 
                  type="text" 
                  className="deped-header-input" 
                  placeholder="e.g. I, II, III, IV..." 
                  value={region} 
                  readOnly 
                />
              </td>
              <th>DIVISION</th>
              <td>
                <input 
                  type="text" 
                  className="deped-header-input" 
                  placeholder="e.g. I, II, III, IV..." 
                  value={division} 
                  readOnly 
                />
              </td>
            </tr>
            <tr>
              <th>SCHOOL NAME</th>
              <td>San Jose National High School</td>
              <th>SCHOOL ID</th>
              <td>
                <input 
                  type="text" 
                  className="deped-header-input" 
                  placeholder="e.g. 123456" 
                  value={schoolId} 
                  readOnly 
                />
              </td>
              <th>SCHOOL YEAR</th>
              <td>{selectors.schoolYear || gradebook?.school_year_name || ''}</td>
            </tr>
          </tbody>
        </table>

        {/* Quarter / Grade & Section / Teacher / Subject */}
        <table className="deped-meta-table">
          <tbody>
            <tr>
              <th className="deped-meta-quarter">{selectors.quarter || quarterLabel}</th>
              <th>GRADE &amp; SECTION:</th>
              <td>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  {selectors.grade || `Grade ${gradebook?.grade_name}`}
                  <span>-</span>
                  {selectors.section || gradebook?.section_name}
                </div>
              </td>
              <th>TEACHER:</th>
              <td>{gradebook?.teacher_name || '-'}</td>
              <th>SUBJECT:</th>
              <td>{selectors.subject || gradebook?.subject_name || '-'}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {isSeniorHigh ? (
        <div style={{ padding: '60px 20px', textAlign: 'center', backgroundColor: '#f8fafc', borderBottomLeftRadius: '10px', borderBottomRightRadius: '10px' }}>
          <h3 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#334155', marginBottom: '12px' }}>Senior High School Template Needed</h3>
          <p style={{ color: '#64748b', maxWidth: '500px', margin: '0 auto', lineHeight: '1.5' }}>
            The current class record template is specifically for Junior High School (Grades 7-10). 
            <br/><br/>
            A different template for Senior High School (Grades 11-12) will be implemented here soon. 
            Once provided, it will automatically appear when you select Grade 11 or 12.
          </p>
        </div>
      ) : (
        <>
          {/* â• â•  Controls Bar â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•  */}
          <div className="deped-controls">
            <div className="deped-search-box">
              <Search size={13} className="deped-search-icon" />
              <input
                type="text"
                className="deped-search-input"
                placeholder="Search learner or LRN..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            <div className="deped-filter-group">
              {['All', 'PASSED', 'FAILED', 'INCOMPLETE'].map(f => (
                <button
                  key={f}
                  type="button"
                  className={`deped-filter-pill${filterStatus === f ? ' deped-filter-active' : ''}`}
                  onClick={() => setFilterStatus(f)}
                >
                  {f === 'All' ? 'All' : f.charAt(0) + f.slice(1).toLowerCase()}
                </button>
              ))}
              <button
                type="button"
                className="deped-sort-btn"
                onClick={() => setSortBy(cur => cur === 'name' ? 'grade' : 'name')}
              >
                <ArrowUpDown size={11} />
                <span>{sortBy === 'name' ? 'Name' : 'Grade'}</span>
              </button>
            </div>

            <span className="deped-learner-count">
              {displayedStudents.length} / {students.length} learners
            </span>
          </div>

          {/* â• â•  DepEd Spreadsheet Table â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•  */}
          <div className="deped-table-scroll">
            <table className="deped-sheet-table">
              <thead>

                {/* â”€â”€ Tier 1: Component group headers â”€â”€ */}
                <tr className="deped-tier-1">
                  <th rowSpan={2} className="deped-th deped-th-no">No.</th>
                  <th rowSpan={2} className="deped-th deped-th-name deped-sticky-col">
                    LEARNERS' NAMES
                  </th>

                  {components.map(comp => (
                    <th
                      key={comp.id}
                      colSpan={(comp.items || []).length + 3}
                      className="deped-th deped-th-comp-group"
                    >
                      {comp.name.toUpperCase()} ({comp.weight}%)
                    </th>
                  ))}

                  <th rowSpan={2} className="deped-th deped-th-grade-col">Initial<br />Grade</th>
                  <th rowSpan={2} className="deped-th deped-th-quarterly-col">Quarterly<br />Grade</th>
                  <th rowSpan={2} className="deped-th deped-th-action-col"><Calculator size={11} /></th>
                </tr>

                {/* â”€â”€ Tier 2: Item numbers + Total / PS / WS labels â”€â”€ */}
                <tr className="deped-tier-2">
                  {components.flatMap(comp => [
                    ...(comp.items || []).map((_, i) => (
                      <th key={`${comp.id}-item-${i}`} className="deped-th deped-th-item">{i + 1}</th>
                    )),
                    <th key={`${comp.id}-total`} className="deped-th deped-th-computed-label">Total</th>,
                    <th key={`${comp.id}-ps`}    className="deped-th deped-th-computed-label">PS</th>,
                    <th key={`${comp.id}-ws`}    className="deped-th deped-th-ws-label">WS</th>,
                  ])}
                </tr>

                {/* â”€â”€ HPS Row (Highest Possible Score) â”€â”€ */}
                <tr className="deped-hps-row">
                  <th className="deped-hps-cell deped-hps-no">-</th>
                  <th className="deped-hps-cell deped-hps-label deped-sticky-col">
                    HIGHEST POSSIBLE SCORE
                  </th>
                  {components.flatMap(comp => {
                    const hps = hpsPerComponent[comp.id] || 0;
                    return [
                      ...(comp.items || []).map(item => (
                        <th key={`hps-${item.id}`} className="deped-hps-cell">{item.max_score}</th>
                      )),
                      <th key={`hps-${comp.id}-total`} className="deped-hps-cell">{hps}</th>,
                      <th key={`hps-${comp.id}-ps`}    className="deped-hps-cell">100.00</th>,
                      <th key={`hps-${comp.id}-ws`}    className="deped-hps-cell deped-hps-ws">{comp.weight}%</th>,
                    ];
                  })}
                  <th className="deped-hps-cell"></th>
                  <th className="deped-hps-cell"></th>
                  <th className="deped-hps-cell"></th>
                </tr>

              </thead>

              <tbody>
                {displayedStudents.length === 0 ? (
                  <tr>
                    <td colSpan={totalColSpan} className="deped-empty-cell">
                      No learners match the current filter or search criteria.
                    </td>
                  </tr>
                ) : (
                  groupedStudents.map(group => (
                    <React.Fragment key={group.label}>

                      {/* Sex section divider row */}
                      <tr className="deped-sex-row">
                        <td colSpan={totalColSpan} className="deped-sex-label">
                          {group.label}
                        </td>
                      </tr>

                      {/* Student rows */}
                      {group.students.map(student => {
                        let colCounter = 0;
                        const isPassing = student.calc.status === 'PASSED';
                        const isFailing = student.calc.status === 'FAILED';

                        return (
                          <tr
                            key={student.person_id}
                            className={`deped-student-row${student.navIdx % 2 === 0 ? ' deped-row-even' : ' deped-row-odd'}`}
                          >
                            {/* Row Number */}
                            <td className="deped-cell deped-cell-no">{student.displayNum}</td>

                            {/* Name (sticky) */}
                            <td className="deped-cell deped-cell-name deped-sticky-col">
                              {student.full_name}
                            </td>

                            {/* Score cells + computed columns per component */}
                            {components.flatMap((comp, compIdx) => {
                              const items = comp.items || [];
                              const cc    = student.componentCalcs[compIdx];

                              if (items.length === 0) {
                                return [
                                  <td key={`${comp.id}-empty`} className="deped-cell deped-cell-computed" colSpan={3}>-</td>,
                                ];
                              }

                              const scoreCells = items.map(item => {
                                const itemColIdx = colCounter++;
                                const currentVal = student.liveScores[item.id] !== undefined
                                  ? student.liveScores[item.id]
                                  : (student.scores?.[item.id] ?? '');
                                const explicitStatus = student.liveStatuses[item.id] || student.score_statuses?.[item.id];
                                const currentStatus  = currentVal === ''
                                  ? (explicitStatus === 'Excused' ? 'Excused' : 'Missing')
                                  : 'Scored';
                                const isScored  = currentStatus === 'Scored';
                                const isOverMax = isScored && Number(currentVal) > item.max_score;
                                const isNeg     = isScored && Number(currentVal) < 0;
                                const hasError  = isOverMax || isNeg;

                                return (
                                  <td
                                    key={item.id}
                                    className={`deped-cell deped-cell-score${hasError ? ' deped-cell-error' : ''}`}
                                  >
                                    <input
                                      ref={el => {
                                        if (el) inputRefs.current.set(`${student.navIdx}-${itemColIdx}`, el);
                                        else    inputRefs.current.delete(`${student.navIdx}-${itemColIdx}`);
                                      }}
                                      type="number"
                                      step="0.5"
                                      min="0"
                                      max={item.max_score}
                                      className={`deped-score-input${hasError ? ' deped-input-error' : ''}`}
                                      disabled={disabled}
                                      value={currentVal}
                                      placeholder=""
                                      onChange={e => onScoreChange?.(student.person_id, item.id, e.target.value)}
                                      onKeyDown={e => handleKeyDown(e, student.navIdx, itemColIdx)}
                                      title={hasError
                                        ? `Score must be between 0 and ${item.max_score}`
                                        : `${item.label} (Max: ${item.max_score})`}
                                    />
                                    {currentStatus === 'Excused' && (
                                      <div className="deped-excused-tag">EXC</div>
                                    )}
                                  </td>
                                );
                              });

                              return [
                                ...scoreCells,
                                // Total raw score
                                <td key={`${comp.id}-total`} className="deped-cell deped-cell-computed">
                                  {cc.total !== null ? cc.total : ''}
                                </td>,
                                // Percentage Score
                                <td key={`${comp.id}-ps`} className="deped-cell deped-cell-computed">
                                  {cc.ps !== null ? cc.ps.toFixed(2) : ''}
                                </td>,
                                // Weighted Score
                                <td key={`${comp.id}-ws`} className="deped-cell deped-cell-computed deped-cell-ws">
                                  {cc.ws !== null ? cc.ws.toFixed(2) : ''}
                                </td>,
                              ];
                            })}

                            {/* Initial Grade */}
                            <td className="deped-cell deped-cell-initial">
                              {student.calc.initialGrade != null
                                ? student.calc.initialGrade.toFixed(2)
                                : ''}
                            </td>

                            {/* Quarterly Grade */}
                            <td className={`deped-cell deped-cell-quarterly${isPassing ? ' deped-passing' : isFailing ? ' deped-failing' : ''}`}>
                              {student.calc.reportedGrade != null
                                ? <strong>{student.calc.reportedGrade}</strong>
                                : ''}
                            </td>

                            {/* Step-by-step calculation breakdown */}
                            <td className="deped-cell deped-cell-action">
                              <button
                                type="button"
                                className="deped-calc-btn"
                                title="View step-by-step DepEd computation"
                                onClick={() => onStudentBreakdown?.(student.person_id)}
                              >
                                <Calculator size={11} />
                              </button>
                            </td>

                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
