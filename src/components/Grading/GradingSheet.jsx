import React, { useState, useMemo, useRef } from 'react';
import { Search, Calculator, ArrowUpDown } from 'lucide-react';
import { calculateComponentPercentage, calculateStudentGrade, isBlankScore, resolveScoreEntry, roundGradeValue } from '../../services/gradingCalculations';
import { useToast } from '../../contexts/useToast';
import { gradingPeriodLabel } from '../../services/academicContext';
import './GradingSheet.css';

const STATUS_CONFIG = {
  Draft: { label: 'DRAFT', cls: 'deped-status-draft' },
  Submitted: { label: 'SUBMITTED', cls: 'deped-status-submitted' },
  Finalized: { label: 'FINALIZED', cls: 'deped-status-finalized' },
  Locked: { label: 'LOCKED', cls: 'deped-status-locked' },
};

export default function GradingSheet({
  gradebook,
  students,
  components,
  scores,
  scoreStatuses,
  passingGrade,
  transmutationTable,
  roundingDecimalPlaces = 2,
  roundingFinalDecimalPlaces = 0,
  roundingMethod = 'half_up',
  reportingMethod = 'legacy',
  disabled,
  loading = false,
  emptyMessage,
  onScoreChange,
  onStatusChange,
  onStudentBreakdown,
  selectors = {},
  region,
  division,
  schoolId,
}) {
  const { showError } = useToast();
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('All');
  const [sortBy, setSortBy] = useState('name');
  const [activeComponentId, setActiveComponentId] = useState(components[0]?.id);
  const inputRefs = useRef(new Map());
  const [scoreCell, setScoreCell] = useState(null);
  const openScoreStatus = (event, student, item, value, status) => {
    if (disabled) return;
    event.preventDefault();
    setScoreCell({ personId: student.person_id, learner: student.full_name, item, value, status });
  };

  // Flattened assessment items for column index tracking
  const flatItems = useMemo(() =>
    components.flatMap(c => (c.items || []).map(item => ({ ...item, componentId: c.id }))),
    [components]
  );

  // Unused configured columns are capacity, not part of this class's grade.
  const liveGradebook = useMemo(() => {
    const rows = students.map(student => {
      const sId = String(student.person_id);
      const liveScores = scores[sId] || {};
      const liveStatuses = scoreStatuses[sId] || {};
      const formattedScores = flatItems.map(item => {
        const val = liveScores[item.id] !== undefined
          ? liveScores[item.id]
          : (student.scores?.[item.id] ?? '');
        const explicitStat = liveStatuses[item.id] || student.score_statuses?.[item.id];
        return { itemId: item.id, active: !isBlankScore(val) || Boolean(explicitStat && explicitStat !== 'Missing'), ...resolveScoreEntry(val, explicitStat) };
      });
      return { student, liveScores, liveStatuses, formattedScores };
    });
    const activeItemIds = new Set(flatItems
      .filter(item => rows.some(row => row.formattedScores.find(entry => entry.itemId === item.id)?.active))
      .map(item => item.id));
    return { rows, activeItemIds };
  }, [students, scores, scoreStatuses, flatItems]);

  const hpsPerComponent = useMemo(() => {
    const map = {};
    for (const comp of components) {
      map[comp.id] = (comp.items || [])
        .filter(item => liveGradebook.activeItemIds.has(item.id))
        .reduce((s, item) => s + Number(item.max_score || 0), 0);
    }
    return map;
  }, [components, liveGradebook.activeItemIds]);

  // Compute live student data including per-component PS / WS
  const computedStudents = useMemo(() => {
    return liveGradebook.rows.map(({ student, liveScores, liveStatuses, formattedScores }) => {
      // Per-component computed values: total raw score, PS (%), WS (weighted)
      const componentCalcs = components.map(comp => {
        const items = (comp.items || []).filter(item => comp.component_type === 'Term Examinations' || liveGradebook.activeItemIds.has(item.id));
        const scoreCalc = calculateComponentPercentage(formattedScores, items, comp.component_type);
        const total = scoreCalc.scoredCount ? scoreCalc.totalEarned : null;
        const hps = scoreCalc.totalPossible;
        const ps = scoreCalc.percentage;
        const ws = ps !== null ? roundGradeValue(ps * (comp.weight / 100), roundingDecimalPlaces, roundingMethod) : null;

        return { compId: comp.id, total, hps, ps, ws };
      });

      const calc = calculateStudentGrade({
        studentScores: formattedScores,
        components: components.map(comp => ({
          ...comp,
          items: (comp.items || []).filter(item => comp.component_type === 'Term Examinations' || liveGradebook.activeItemIds.has(item.id)),
        })),
        transmutationTable,
        passingGrade,
        roundingDecimalPlaces,
        roundingFinalDecimalPlaces,
        roundingMethod,
        reportingMethod,
      });

      return { ...student, liveScores, liveStatuses, componentCalcs, calc };
    });
  }, [liveGradebook, components, transmutationTable, passingGrade, roundingDecimalPlaces, roundingFinalDecimalPlaces, roundingMethod, reportingMethod]);

  // Filter + sort
  const displayedStudents = useMemo(() => {
    let list = computedStudents.filter(s => {
      if (filterStatus === 'PASSED' && s.calc.status !== 'PASSED') return false;
      if (filterStatus === 'FAILED' && s.calc.status !== 'FAILED') return false;
      if (filterStatus === 'INCOMPLETE' && s.calc.status !== 'INCOMPLETE') return false;
      if (!search.trim()) return true;
      const term = search.toLowerCase();
      return s.full_name.toLowerCase().includes(term)
        || (s.lrn && s.lrn.toLowerCase().includes(term))
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
    const isMale = s => (s.sex || '').toUpperCase().startsWith('M');
    const isFemale = s => (s.sex || '').toUpperCase().startsWith('F');

    const males = displayedStudents.filter(isMale);
    const females = displayedStudents.filter(isFemale);
    const others = displayedStudents.filter(s => !isMale(s) && !isFemale(s));

    const groups = [
      { label: 'MALE', students: males },
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
  const isGradeSummary = activeComponentId === 'grade-summary';
  const activeComponent = components.find(component => component.id === activeComponentId) || components[0];
  const visibleItems = activeComponent?.items || [];

  // Column count for the empty-state row colspan
  const totalColSpan = isGradeSummary ? 5 : 2 + visibleItems.length + 3;

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
      if (colIdx < visibleItems.length - 1) nextCol = colIdx + 1;
    } else if (e.key === 'ArrowLeft' && e.target.selectionStart === 0) {
      if (colIdx > 0) nextCol = colIdx - 1;
    }

    if (nextRow !== navRowIdx || nextCol !== colIdx) {
      const target = inputRefs.current.get(`${nextRow}-${nextCol}`);
      if (target) { target.focus(); target.select(); }
    }
  };

  // Derived header values
  const termLabel = gradebook?.grading_period_name || (gradebook?.term_order
    ? gradingPeriodLabel(gradebook.term_order)
    : 'TERM');
  const statusCfg = STATUS_CONFIG[gradebook?.status] || STATUS_CONFIG.Draft;

  return (
    <section className="deped-class-record" aria-busy={loading}>

      {/* â• â•  DepEd Class Record Header Block â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•  */}
      <div className="deped-header-block">

        {/* Title row */}
        <div className="deped-header-top">
          <div style={{ width: '90px', flexShrink: 0 }}></div> {/* Spacer to center the title */}
          <div className="deped-header-center">
            <div className="deped-header-title">Class Record</div>
            <div className="deped-header-subtitle">(Pursuant to DepEd Order #15, s. 2026)</div>
          </div>
          <div className="deped-header-right">
            <div className={`deped-status-badge ${statusCfg.cls}`} role={loading ? 'status' : undefined}>
              {loading ? 'LOADING…' : gradebook ? statusCfg.label : 'NO RECORD'}
            </div>
          </div>
        </div>

        {/* School info rows */}
        <table className="deped-info-table">
          <tbody>
            <tr>
              <th>REGION</th>
              <td>
                {region}
              </td>
              <th>DIVISION</th>
              <td>
                {division}
              </td>
              <th>SCHOOL HEAD</th>
              <td>{gradebook ? (gradebook.school_head || 'Not configured') : ''}</td>
            </tr>
            <tr>
              <th>SCHOOL NAME</th>
              <td>San Jose National High School</td>
              <th>SCHOOL ID</th>
              <td>
                {schoolId}
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
              <th className="deped-meta-quarter">{selectors.termOrder || termLabel}</th>
              <th>GRADE &amp; SECTION:</th>
              <td>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  {selectors.grade || (gradebook?.grade_name ? `Grade ${gradebook.grade_name}` : '')}
                  {(selectors.grade || gradebook?.grade_name) && (selectors.section || gradebook?.section_name) ? <span>-</span> : null}
                  {selectors.section || gradebook?.section_name || (!(selectors.grade || gradebook?.grade_name) ? '-' : '')}
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
              {!disabled && <span>Right-click a score or press Shift+F10 to set its status. </span>}
              {displayedStudents.length} / {students.length} learners
            </span>
            {computedStudents.some(student => !student.calc.complete) && (
              <span className="deped-learner-count" role="status">
                Initial and term grades appear after every activity used in this class is scored for each learner.
              </span>
            )}
          </div>

          <div className="deped-assessment-tabs" role="group" aria-label="Class record view">
            {components.map(component => {
              const label = component.component_type === 'Term Examinations' ? 'Quarterly Assessment' : component.name;
              const selected = component.id === activeComponent?.id;
              return (
                <button key={component.id} type="button" aria-pressed={selected}
                  className={`deped-assessment-tab${selected ? ' deped-assessment-tab-active' : ''}`}
                  onClick={() => setActiveComponentId(component.id)}>
                  {label} <span>{component.weight}%</span>
                </button>
              );
            })}
            <button type="button" aria-pressed={isGradeSummary}
              className={`deped-assessment-tab${isGradeSummary ? ' deped-assessment-tab-active' : ''}`}
              onClick={() => setActiveComponentId('grade-summary')}>
              Grades &amp; Calculation
            </button>
          </div>

          {/* â• â•  DepEd Spreadsheet Table â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•  */}
          <div className="deped-table-scroll">
            <table className="deped-sheet-table">
              <thead>
                {isGradeSummary ? (
                  <tr className="deped-tier-1">
                    <th className="deped-th deped-th-no">No.</th>
                    <th className="deped-th deped-th-name deped-sticky-col">LEARNERS' NAMES</th>
                    <th className="deped-th deped-th-grade-col">Initial Grade</th>
                    <th className="deped-th deped-th-quarterly-col">Term Grade</th>
                    <th className="deped-th deped-th-action-col"><Calculator size={11} /><span className="control-label">Calculation</span></th>
                  </tr>
                ) : (
                  <>
                    <tr className="deped-tier-1">
                      <th rowSpan={2} className="deped-th deped-th-no">No.</th>
                      <th rowSpan={2} className="deped-th deped-th-name deped-sticky-col">LEARNERS' NAMES</th>
                      {activeComponent && (
                        <th key={activeComponent.id} colSpan={visibleItems.length + 3} className="deped-th deped-th-comp-group">
                          {(activeComponent.component_type === 'Term Examinations' ? 'Quarterly Assessment' : activeComponent.name).toUpperCase()} ({activeComponent.weight}%)
                        </th>
                      )}
                    </tr>
                    <tr className="deped-tier-2">
                      {activeComponent && [
                        ...visibleItems.map((item, i) => (
                          <th key={`${activeComponent.id}-item-${i}`} className="deped-th deped-th-item">{activeComponent.component_type === 'Term Examinations' ? item.label : i + 1}</th>
                        )),
                        <th key={`${activeComponent.id}-total`} className="deped-th deped-th-computed-label">Total</th>,
                        <th key={`${activeComponent.id}-ps`} className="deped-th deped-th-computed-label">PS</th>,
                        <th key={`${activeComponent.id}-ws`} className="deped-th deped-th-ws-label">WS</th>,
                      ]}
                    </tr>
                    <tr className="deped-hps-row">
                      <th className="deped-hps-cell deped-hps-no">-</th>
                      <th className="deped-hps-cell deped-hps-label deped-sticky-col">HIGHEST POSSIBLE SCORE</th>
                      {activeComponent && (() => {
                        const comp = activeComponent;
                        const hps = hpsPerComponent[comp.id] || 0;
                        return [
                          ...(comp.items || []).map(item => (
                            <th key={`hps-${item.id}`} className="deped-hps-cell">{item.max_score}</th>
                          )),
                          <th key={`hps-${comp.id}-total`} className="deped-hps-cell">{hps}</th>,
                          <th key={`hps-${comp.id}-ps`} className="deped-hps-cell">100.00</th>,
                          <th key={`hps-${comp.id}-ws`} className="deped-hps-cell deped-hps-ws">{comp.weight}%</th>,
                        ];
                      })()}
                    </tr>
                  </>
                )}
              </thead>

              <tbody>
                {displayedStudents.length === 0 ? (
                  <tr>
                    <td colSpan={totalColSpan} className="deped-empty-cell">
                      {loading
                        ? 'Loading class record…'
                        : !gradebook
                          ? (emptyMessage || 'Choose a school year, grading period, grade, section, and subject in the header to open a class record.')
                          : 'No learners match the current filter or search criteria.'}
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

                            {isGradeSummary ? (
                              <>
                                <td className="deped-cell deped-cell-initial">
                                  {student.calc.initialGrade != null ? student.calc.initialGrade.toFixed(2) : ''}
                                </td>
                                <td className={`deped-cell deped-cell-quarterly${isPassing ? ' deped-passing' : isFailing ? ' deped-failing' : ''}`}>
                                  {student.calc.reportedGrade != null ? <strong>{student.calc.reportedGrade}</strong> : ''}
                                </td>
                                <td className="deped-cell deped-cell-action">
                                  <button type="button" className="deped-calc-btn" title="View step-by-step DepEd computation" onClick={() => onStudentBreakdown?.(student.person_id)}>
                                    <Calculator size={11} /><span className="control-label">Calculation</span>
                                  </button>
                                </td>
                              </>
                            ) : (
                              <>
                            {/* Score cells + computed columns per component */}
                            {activeComponent && (() => {
                              const comp = activeComponent;
                              const compIdx = components.findIndex(component => component.id === comp.id);
                              const items = visibleItems;
                              const cc = student.componentCalcs[compIdx];

                              if (items.length === 0) {
                                return <td key={`${comp.id}-empty`} className="deped-cell deped-cell-computed" colSpan={3}>-</td>;
                              }

                              const scoreCells = items.map(item => {
                                const itemColIdx = colCounter++;
                                const currentVal = student.liveScores[item.id] !== undefined
                                  ? student.liveScores[item.id]
                                  : (student.scores?.[item.id] ?? '');
                                const explicitStatus = student.liveStatuses[item.id] || student.score_statuses?.[item.id];
                                const currentStatus = resolveScoreEntry(currentVal, explicitStatus).status;
                                const isScored = currentStatus === 'Scored';
                                const isOverMax = isScored && Number(currentVal) > item.max_score;
                                const isNeg = isScored && Number(currentVal) < 0;
                                const hasError = isOverMax || isNeg;

                                return (
                                  <td
                                    key={item.id}
                                    className={`deped-cell deped-cell-score${hasError ? ' deped-cell-error' : ''}`}
                                  >
                                    <input
                                      ref={el => {
                                        if (el) inputRefs.current.set(`${student.navIdx}-${itemColIdx}`, el);
                                        else inputRefs.current.delete(`${student.navIdx}-${itemColIdx}`);
                                      }}
                                      type="number"
                                      step="any"
                                      min="0"
                                      max={item.max_score}
                                      className={`deped-score-input${hasError ? ' deped-input-error' : ''}`}
                                      disabled={disabled}
                                      value={currentVal}
                                      placeholder={['Finalized', 'Locked'].includes(gradebook?.status) ? '' : 'Score'}
                                      onChange={e => onScoreChange?.(student.person_id, item.id, e.target.value)}
                                      aria-label={`${student.full_name} — ${item.label}`}
                                      onContextMenu={event => openScoreStatus(event, student, item, currentVal, currentStatus)}
                                      onKeyDown={event => {
                                        if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
                                          openScoreStatus(event, student, item, currentVal, currentStatus);
                                        } else handleKeyDown(event, student.navIdx, itemColIdx);
                                      }}
                                      title={hasError
                                        ? `Score must be between 0 and ${item.max_score}`
                                        : `${item.label} (Max: ${item.max_score})`}
                                    />
                                    {!['Scored', 'Missing'].includes(currentStatus) && (
                                      <div className="deped-excused-tag" title={currentStatus}>{currentStatus === 'Not Applicable' ? 'N/A' : currentStatus.slice(0, 3).toUpperCase()}</div>
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
                            })()}

                              </>
                            )}
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
      {scoreCell && (
        <div className="modal-backdrop">
          <form className="modal-card modal-sm" role="dialog" aria-modal="true" aria-labelledby="score-status-title" onSubmit={event => {
            event.preventDefault();
            if (disabled) return;
            if (scoreCell.status === 'Scored') {
              if (isBlankScore(scoreCell.value) || !Number.isFinite(Number(scoreCell.value)) || Number(scoreCell.value) < 0 || Number(scoreCell.value) > scoreCell.item.max_score) {
                showError(`Enter a score between 0 and ${scoreCell.item.max_score}.`);
                return;
              }
              onScoreChange?.(scoreCell.personId, scoreCell.item.id, scoreCell.value);
            }
            onStatusChange?.(scoreCell.personId, scoreCell.item.id, scoreCell.status);
            setScoreCell(null);
          }}>
            <div className="modal-header"><h3 id="score-status-title">Assessment score &amp; status</h3></div>
            <p>{scoreCell.learner}<br />{scoreCell.item.label}</p>
            <label><span className="field-label">Status</span><select autoFocus className="input-field" value={scoreCell.status} disabled={disabled} onChange={event => setScoreCell({ ...scoreCell, status: event.target.value })}>
              {['Scored', 'Missing', 'Absent', 'Excused', 'Incomplete', 'Not Applicable'].map(status => <option key={status}>{status}</option>)}
            </select></label>
            {scoreCell.status === 'Scored' && <label><span className="field-label">Score (0–{scoreCell.item.max_score})</span><input placeholder="Enter a score" className="input-field" type="number" step="any" min="0" max={scoreCell.item.max_score} value={scoreCell.value} disabled={disabled} onChange={event => setScoreCell({ ...scoreCell, value: event.target.value })} required /></label>}
            <div className="modal-actions"><button className="btn-secondary" type="button" onClick={() => setScoreCell(null)}>Cancel</button><button className="btn-primary" type="submit" disabled={disabled}>Apply to draft</button></div>
          </form>
        </div>
      )}
    </section>
  );
}
