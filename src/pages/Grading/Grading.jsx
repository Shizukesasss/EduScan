import { MAPEH_AREAS, formatMapehFinalizeIssue, mapehAreaContext, sameMapehContext } from '../../services/mapehLearningAreas';
import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { api, auth } from '../../api/client';
import { normalizeGradeName, subjectMatchesGrade, availableOptionId } from '../../services/academicContext';
import { buildScoreUpdates, validateGradebookForFinalization } from '../../services/gradingWorkflow';
import { groupAdminGradebooks } from '../../services/gradebookSelection';
import { watchGradebookUpdates } from '../../services/gradebookRefresh';

import GradebookSummary from '../../components/Grading/GradebookSummary';
import GradebookActions from '../../components/Grading/GradebookActions';
import GradingSheet from '../../components/Grading/GradingSheet';
import AssessmentConfig from '../../components/Grading/AssessmentConfig';
import CalculationBreakdown from '../../components/Grading/CalculationBreakdown';
import AuditHistory from '../../components/Grading/AuditHistory';
import AdjustmentRequestsModal from '../../components/Grading/AdjustmentRequestsModal';
import ValidationChecklist from '../../components/Grading/ValidationChecklist';
import GlobalAdjustmentsTab from '../../components/Grading/GlobalAdjustmentsTab';
import { Loader2, Search } from 'lucide-react';
import { useToast } from '../../contexts/useToast';

export default function Grading() {
  const currentRole = String(auth.role()).toLowerCase();
  const isTeacher = currentRole === 'teacher';
  const isReviewer = ['admin', 'records_officer', 'school_head'].includes(currentRole);
  const canReviewAdjustments = currentRole === 'records_officer';
  const [structure, setStructure] = useState({
    school_years: [],
    grading_periods: [],
    grade_levels: [],
    sections: [],
    subjects: [],
  });

  // Selector state
  const [schoolYearId, setSchoolYearId] = useState('');
  const [termOrder, setTermOrder] = useState(1);
  const [gradeId, setGradeId] = useState('');
  const [sectionId, setSectionId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [mapehArea,setMapehArea] = useState('music_arts');
  const [existingGradebooks, setExistingGradebooks] = useState([]);
  const [existingGradebooksLoading, setExistingGradebooksLoading] = useState(isReviewer);
  const [existingGradebooksError, setExistingGradebooksError] = useState('');
  const [includeHistoricalGradebooks, setIncludeHistoricalGradebooks] = useState(false);
  const [adminGradebookId, setAdminGradebookId] = useState('');
  const [adminGradebookSearch, setAdminGradebookSearch] = useState('');

  // Active Gradebook data from API
  const [gradebookId, setGradebookId] = useState(null);
  const [fullGradebook, setFullGradebook] = useState(null);
  const [loading, setLoading] = useState(false);
  const [structureLoading, setStructureLoading] = useState(!isReviewer);
  const [saving, setSaving] = useState(false);
  const loadRequestRef = useRef(0);
  const { showSuccess, showError } = useToast();

  // Unsaved score & status changes
  const [scoreEdits, setScoreEdits] = useState({});
  const [statusEdits, setStatusEdits] = useState({});
  const [isDirty, setIsDirty] = useState(false);

  // Form states for export templates
  const region = 'V';
  const division = 'V';
  const schoolId = '301874';

  // Modal / drawer states
  const [showConfig, setShowConfig] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [showAdjustments, setShowAdjustments] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [breakdownData, setBreakdownData] = useState(null);
  const [auditList, setAuditList] = useState([]);
  const [adjustmentsList, setAdjustmentsList] = useState([]);

  // Navigation State
  const [activeTab, setActiveTab] = useState('gradebook');

  // Badge States
  const [adminPendingCount, setAdminPendingCount] = useState(0);
  const [teacherAdjustmentCount, setTeacherAdjustmentCount] = useState(0);
  const lastAdminPendingCount = useRef(null);

  const updateAdminPendingCount = useCallback((data) => {
    const count = data.filter(request => request.status === 'Pending').length;
    lastAdminPendingCount.current = count;
    setAdminPendingCount(count);
  }, []);

  const loadAdminPendingCount = useCallback(() => {
    if (canReviewAdjustments) {
      api.get('/admin/grade-adjustments')
        .then(data => {
          const count = data.filter(request => request.status === 'Pending').length;
          if (lastAdminPendingCount.current !== null && count > lastAdminPendingCount.current) {
            if (document.visibilityState === 'visible') showSuccess('A new teacher grade adjustment request is waiting for review.');
            else return setAdminPendingCount(count);
          }
          lastAdminPendingCount.current = count;
          setAdminPendingCount(count);
        })
        .catch(console.error);
    }
  }, [canReviewAdjustments, showSuccess]);

  useEffect(() => {
    loadAdminPendingCount();
    if (!canReviewAdjustments) return undefined;
    const interval = window.setInterval(loadAdminPendingCount, 15000);
    return () => window.clearInterval(interval);
  }, [canReviewAdjustments, loadAdminPendingCount]);

  useEffect(() => {
    if (!isTeacher) return undefined;
    let stopped = false;
    const notified = new Set();
    const checkNotifications = async () => {
      try {
        if (document.visibilityState !== 'visible') return;
        const notifications = await api.get('/teacher/grade-adjustment-notifications');
        if (stopped || notifications.length === 0) return;
        const unseen = notifications.filter(item => !notified.has(item.id));
        for (const item of unseen) {
          notified.add(item.id);
          const outcome = item.status === 'Approved' ? 'approved' : 'rejected';
          const context = [item.person_name, item.grading_period_name, item.subject_name].filter(Boolean).join(' · ');
          const requestLabel = item.request_type === 'criteria' ? 'criteria adjustment' : 'grade adjustment';
          const message = `Your ${requestLabel} was ${outcome}${context ? `: ${context}` : ''}${item.review_note ? `. ${item.review_note}` : ''}`;
          (item.status === 'Approved' ? showSuccess : showError)(message);
        }
        if (unseen.length) {
          await api.post('/teacher/grade-adjustment-notifications/read', { request_ids: unseen.map(item => item.id) });
        }
      } catch (error) {
        if (!stopped) console.error('Failed to check grade adjustment notifications:', error);
      }
    };
    checkNotifications();
    const interval = window.setInterval(checkNotifications, 15000);
    return () => { stopped = true; window.clearInterval(interval); };
  }, [isTeacher, showError, showSuccess]);

  // Load specific gradebook adjustments count for teachers
  const loadTeacherAdjustmentCount = useCallback(() => {
    const currentRole = String(auth.role()).toLowerCase();
    if (currentRole === 'teacher' && gradebookId) {
      api.get(`/gradebooks/${gradebookId}/adjustments`)
        .then(data => {
          setTeacherAdjustmentCount(data.filter(request => request.status === 'Pending').length);
        })
        .catch(console.error);
    }
  }, [gradebookId]);

  useEffect(() => {
    loadTeacherAdjustmentCount();
  }, [loadTeacherAdjustmentCount]);

  // 1. Initial Load: Academic Structure
  useEffect(() => {
    if (isReviewer) return undefined;
    let stopped = false;
    api.get('/admin/academic-structure?context=grading')
      .then((data) => {
        if (stopped) return;
        setStructure(data);

        const activeYear = data.school_years?.find((y) => y.active) || data.school_years?.[0];
        if (activeYear) setSchoolYearId(activeYear.id);

        const activeGrade = data.grade_levels?.find((g) => g.active) || data.grade_levels?.[0];
        if (activeGrade) {
          setGradeId(activeGrade.id);
          const firstSection = data.sections?.find((s) => s.grade_level_id === activeGrade.id && s.active);
          if (firstSection) setSectionId(firstSection.id);
        }

        const activeSubject = data.subjects?.find((s) => s.active) || data.subjects?.[0];
        if (activeSubject) setSubjectId(activeSubject.id);
      })
      .catch((err) => { if (!stopped) showError(err.message); })
      .finally(() => { if (!stopped) setStructureLoading(false); });
    return () => { stopped = true; };
  }, [showError, isReviewer]);

  useEffect(() => {
    if (!isReviewer) return undefined;
    let stopped = false;
    let inFlight = false;
    const refresh = () => {
      if (stopped || inFlight) return;
      inFlight = true;
      api.get(`/gradebooks?current_only=${!includeHistoricalGradebooks}`, { signal: AbortSignal.timeout(30000) })
        .then((books) => { if (!stopped) { setExistingGradebooks(books); setExistingGradebooksError(''); } })
        .catch((err) => { if (!stopped) { setExistingGradebooksError(err.message); showError(err.message); } })
        .finally(() => { inFlight = false; if (!stopped) setExistingGradebooksLoading(false); });
    };
    refresh();
    const stopWatching = watchGradebookUpdates(refresh);
    return () => { stopped = true; stopWatching(); };
  }, [isReviewer, showError, includeHistoricalGradebooks]);

  const { count: filteredGradebookCount, groups: groupedAdminGradebooks } = useMemo(
    () => groupAdminGradebooks(existingGradebooks, adminGradebookSearch),
    [existingGradebooks, adminGradebookSearch],
  );


  // Filter sections when selected grade changes
  const availableSections = useMemo(() => {
    return (structure.sections || [])
      .filter((s) => !gradeId || s.grade_level_id === Number(gradeId))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [structure.sections, gradeId]);

  const sortedSchoolYears = useMemo(() => {
    return [...(structure.school_years || [])].sort((a, b) => b.name.localeCompare(a.name));
  }, [structure.school_years]);

  const availablePeriods = useMemo(() => (structure.grading_periods || [])
    .filter(period => period.school_year_id === Number(schoolYearId))
    .sort((a, b) => a.term_order - b.term_order), [structure.grading_periods, schoolYearId]);

  const sortedGradeLevels = useMemo(() => {
    return [...(structure.grade_levels || [])].sort((a, b) => {
      const numA = Number(normalizeGradeName(a.name));
      const numB = Number(normalizeGradeName(b.name));
      if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
      return a.name.localeCompare(b.name);
    });
  }, [structure.grade_levels]);

  const teacherSubjectIds = useMemo(() => new Set(
    (structure.subject_assignments || [])
      .filter((assignment) => assignment.school_year_id === Number(schoolYearId)
        && assignment.teacher_user_id === structure.current_user_id)
      .map((assignment) => assignment.subject_id),
  ), [structure.subject_assignments, structure.current_user_id, schoolYearId]);
  const teacherAssignmentConflict = isTeacher && teacherSubjectIds.size > 1;

  const sortedSubjects = useMemo(() => {
    const selectedSection = (structure.sections || []).find((section) => section.id === Number(sectionId));
    const assignments = (structure.subject_assignments || []).filter((assignment) =>
      assignment.school_year_id === Number(schoolYearId));
    const assignedSubjectKeys = new Set((structure.subject_assignment_subjects || []).map(([yearId, subjectKey]) =>
      `${yearId}:${subjectKey}`));
    const filtered = (structure.subjects || []).filter((s) => {
      const assignedHere = assignments.some(assignment => assignment.subject_id === s.id && assignment.section_id === Number(sectionId) && assignment.teacher_user_id === structure.current_user_id);
      if (!subjectMatchesGrade(s, structure.grade_levels.find(grade => grade.id === Number(gradeId))?.name) && !(isTeacher && assignedHere)) return false;
      if (s.is_elective && s.elective_track
        && selectedSection?.track?.trim().toLowerCase() !== s.elective_track.trim().toLowerCase()) return false;
      if (!isTeacher) return true;
      if (teacherSubjectIds.size > 1) return false;
      const subjectAssignments = assignments.filter((assignment) => assignment.subject_id === s.id);
      if (teacherSubjectIds.size === 1) {
        return teacherSubjectIds.has(s.id) && subjectAssignments.some((assignment) =>
          assignment.section_id === Number(sectionId)
            && assignment.teacher_user_id === structure.current_user_id);
      }
      if (assignedSubjectKeys.has(`${schoolYearId}:${s.id}`)) {
        return subjectAssignments.some((assignment) => assignment.section_id === Number(sectionId)
          && assignment.teacher_user_id === structure.current_user_id);
      }
      return false;
    });
    return [...filtered].sort((a, b) => a.name.localeCompare(b.name));
  }, [structure.subjects, structure.sections, structure.subject_assignments, structure.subject_assignment_subjects,
    structure.current_user_id, teacherSubjectIds,
    structure.grade_levels, gradeId, schoolYearId, sectionId, isTeacher]);

  // Resolve dependent selections before rendering a class from the new context.
  const validSectionId = availableOptionId(availableSections, sectionId);
  const validSubjectId = availableOptionId(sortedSubjects, subjectId);
  if (sectionId !== validSectionId) setSectionId(validSectionId);
  if (subjectId !== validSubjectId) setSubjectId(validSubjectId);

  // Match the selected academic period for the current school year.
  const gradingPeriodId = useMemo(() => {
    const period = (structure.grading_periods || []).find(
      (p) => p.school_year_id === Number(schoolYearId) && p.term_order === Number(termOrder)
    );
    return period ? period.id : null;
  }, [structure.grading_periods, schoolYearId, termOrder]);

  const learningArea=mapehAreaContext((structure.subjects||[]).find(s=>s.id===Number(subjectId)),mapehArea);
  const contextKey = `${schoolYearId}:${gradingPeriodId}:${gradeId}:${sectionId}:${subjectId}:${learningArea}`;
  const validContext = Boolean(schoolYearId && gradeId && sectionId && subjectId && gradingPeriodId
    && availableSections.some(section => section.id === Number(sectionId))
    && sortedSubjects.some(subject => subject.id === Number(subjectId)));
  const [previousContext, setPreviousContext] = useState(contextKey);
  if (previousContext !== contextKey) {
    setPreviousContext(contextKey);
    setLoading(isTeacher && validContext);
    setScoreEdits({});
    setStatusEdits({});
    setIsDirty(false);
    if (isTeacher && !validContext) { setFullGradebook(null); setGradebookId(null); }
  }

  // 2. Fetch or Create Gradebook
  const loadGradebook = useCallback(() => {
    if ((isReviewer && !adminGradebookId) || (isTeacher && !validContext)) return undefined;
    const requestId = ++loadRequestRef.current;
    const context = {
      school_year_id: Number(schoolYearId),
      grading_period_id: Number(gradingPeriodId),
      grade_level_id: Number(gradeId),
      section_id: Number(sectionId),
      subject_id: Number(subjectId),
      learning_area: learningArea==='legacy'?'':learningArea,
    };
    // Viewing a class must not create or modify its record for Admin.
    const request = isReviewer
      ? api.get(`/gradebooks/${adminGradebookId}`, { signal: AbortSignal.timeout(30000) })
      : learningArea==='legacy'
        ? api.get('/gradebooks').then(books=>({id:books.find(book=>book.school_year_id===context.school_year_id && book.grading_period_id===context.grading_period_id && book.section_id===context.section_id && book.subject_id===context.subject_id && !book.learning_area)?.id}))
        : api.post('/gradebooks', context);
    return request.then(async (res) => {
      if (requestId !== loadRequestRef.current) return;
      if (isReviewer) {
        setGradebookId(Number(adminGradebookId));
        setFullGradebook(res);
        return;
      }
      if (!res.id) {
        setFullGradebook(null);
        setGradebookId(null);
        return;
      }

      const gbId = res.id;
      if (requestId !== loadRequestRef.current) return;
      setGradebookId(gbId);

      // Load full gradebook data
      const full = await api.get(`/gradebooks/${gbId}`);
      if (requestId !== loadRequestRef.current) return;
      setFullGradebook(full);
    }).catch((err) => {
      if (requestId !== loadRequestRef.current) return;
      showError(err.message);
      setFullGradebook(null);
      setGradebookId(null);
    }).finally(() => {
      if (requestId === loadRequestRef.current) setLoading(false);
    });
  }, [schoolYearId, gradingPeriodId, gradeId, sectionId, subjectId, learningArea, validContext, showError, isTeacher, isReviewer, adminGradebookId]);

  useEffect(() => {
    loadGradebook();
    return () => { loadRequestRef.current += 1; };
  }, [loadGradebook]);

  // Refresh gradebook when switching tabs to ensure changes from other tabs (like Adjustments) are reflected
  useEffect(() => {
    let cancelled = false;
    const requestId = loadRequestRef.current;
    if ((activeTab !== 'gradebook' && activeTab !== 'metrics') || !gradebookId || saving || isDirty) return undefined;
    let inFlight = false;
    const refresh = () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      api.get(`/gradebooks/${gradebookId}`, { signal: AbortSignal.timeout(30000) })
        .then(data => { if (!cancelled && requestId === loadRequestRef.current) setFullGradebook(data); })
        .catch(err => console.error('Failed to refresh gradebook:', err))
        .finally(() => { inFlight = false; });
    };
    refresh();
    const stopWatching = isReviewer ? watchGradebookUpdates(refresh) : () => {};
    return () => { cancelled = true; stopWatching(); };
  }, [activeTab, gradebookId, saving, isDirty, isReviewer]);

  // 3. Handle Score and Status Edits in Memory
  const handleScoreChange = (studentId, itemId, value) => {
    const sId = String(studentId);
    setScoreEdits((prev) => ({
      ...prev,
      [sId]: {
        ...(prev[sId] || {}),
        [itemId]: value,
      },
    }));
    setStatusEdits(prev => ({ ...prev, [sId]: { ...(prev[sId] || {}), [itemId]: value === '' ? 'Missing' : 'Scored' } }));
    setIsDirty(true);
  };

  const handleStatusChange = (studentId, itemId, status) => {
    const sId = String(studentId);
    setStatusEdits((prev) => ({
      ...prev,
      [sId]: {
        ...(prev[sId] || {}),
        [itemId]: status,
      },
    }));
    // If status changed to non-Scored, clear the entered score
    if (status !== 'Scored') {
      setScoreEdits((prev) => ({
        ...prev,
        [sId]: {
          ...(prev[sId] || {}),
          [itemId]: '',
        },
      }));
    }
    setIsDirty(true);
  };

  // 4. Save Draft
  const handleSaveDraft = async (silent = false) => {
    if (!gradebookId || !fullGradebook) return false;
    const payloadScores = buildScoreUpdates(fullGradebook.students || [], fullGradebook.components || [], scoreEdits, statusEdits);
    const hasChanges = Object.keys(payloadScores).length > 0;
    loadRequestRef.current += 1;

    setSaving(true);

    try {
      if (hasChanges) {
        await api.put(`/gradebooks/${gradebookId}/scores`, {
          scores: payloadScores,
          change_reason: 'Teacher saved class record scores',
        });
      }

      // Reload gradebook calculations from authority
      const refreshed = await api.get(`/gradebooks/${gradebookId}`);
      setFullGradebook(refreshed);
      setIsDirty(false);
      setScoreEdits({});
      setStatusEdits({});
      if (!silent) {
        const incomplete = Number(refreshed.statistics?.incomplete || 0);
        showSuccess(hasChanges
          ? incomplete
            ? `Scores saved. Grades stay blank for learners missing an activity used in this class (${incomplete} learner(s) incomplete).`
            : 'Scores saved and grades recalculated.'
          : incomplete
            ? `No unsaved scores. Grades stay blank for learners missing an activity used in this class (${incomplete} learner(s) incomplete).`
            : 'Scores are already saved and grades are up to date.');
      }
      return true;
    } catch (err) {
      showError(err.message);
      if (silent) throw err;
      return false;
    } finally {
      setSaving(false);
    }
  };

  // 5. Update Assessment Components & Items
  const handleSaveComponents = async (updatedComponents, changeReason) => {
    if (!gradebookId) return;
    if (isDirty && !await handleSaveDraft()) return;
    loadRequestRef.current += 1;
    setSaving(true);
    try {
      await api.put(`/gradebooks/${gradebookId}/components`, {
        components: updatedComponents,
        change_reason: changeReason,
      });
      // Refresh
      const refreshed = await api.get(`/gradebooks/${gradebookId}`);
      setFullGradebook(refreshed);
      setShowConfig(false);
      showSuccess('Assessment components and activities updated successfully.');
      setScoreEdits({});
      setStatusEdits({});
      setIsDirty(false);
    } catch (err) {
      showError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // 6. Workflow Transitions
  const validateHeaderFields = () => {
    const missingFields = [];
    if (!region.trim()) missingFields.push('REGION');
    if (!division.trim()) missingFields.push('DIVISION');
    if (!schoolId.trim()) missingFields.push('SCHOOL ID');

    if (missingFields.length > 0) {
      showError(`Please complete the following fields: ${missingFields.join(', ')}`);
      return false;
    }

    const romanRegex = /^[IVXLCDM\s-]+$/i;

    if (!romanRegex.test(region.trim())) {
      showError('REGION must use ONLY Roman Numerals (e.g., I, II, IV, IV-A).');
      return false;
    }

    if (!/^\d+$/.test(schoolId.trim())) {
      showError('SCHOOL ID must contain only numbers.');
      return false;
    }

    return true;
  };

  const handleValidateFinalize = async () => {
    // 1. Validate required header fields
    if (!validateHeaderFields()) {
      return false;
    }

    try {
      const valid = validateGradebookForFinalization(fullGradebook.students, fullGradebook.components, scoreEdits, statusEdits);
      if (fullGradebook.gradebook.learning_area) {
        const validation = await api.post(`/gradebooks/${gradebookId}/validate`, {});
        const partnerIssue = validation.issues?.find(issue => issue.code === 'MAPEH_PARTNER_INCOMPLETE');
        if (partnerIssue) {
          showError(partnerIssue.message);
          return false;
        }
      }
      return valid;
    } catch (error) {
      const gradebook=fullGradebook?.gradebook;
      const context = {
        ...(gradebook?.learning_area ? { learningArea: activeMapehArea?.label || 'MAPEH learning area' } : {}),
        term: gradebook?.term_order,
      };
      if (error.finalizationIssues) {
        return {
          ...error.finalizationIssues,
          message: gradebook?.learning_area
            ? formatMapehFinalizeIssue(error.message, context.learningArea, gradebook.term_order)
            : error.message,
          context,
        };
      }
      const message=gradebook?.learning_area
        ? formatMapehFinalizeIssue(error.message,activeMapehArea?.label||'learning area',gradebook.term_order)
        : error.message;
      showError(message);
      return false;
    }
  };

  const handleFinalizeGradebook = async (reason) => {
    if (!gradebookId) return;
    if (isDirty) {
      await handleSaveDraft(true);
    }
    loadRequestRef.current += 1;
    setSaving(true);
    try {
      await api.post(`/gradebooks/${gradebookId}/finalize`, { reason });
      showSuccess('Gradebook finalized! Term grades have been officially computed.');
      const refreshed = await api.get(`/gradebooks/${gradebookId}`);
      setFullGradebook(refreshed);
    } catch (err) {
      if (err.code !== 'INCOMPLETE_GRADEBOOK') showError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const handleLockGradebook = async (reason) => {
    if (!gradebookId) return;
    loadRequestRef.current += 1;
    setSaving(true);
    try {
      await api.post(`/gradebooks/${gradebookId}/lock`, { reason });
      showSuccess('Gradebook locked and archived.');
      const refreshed = await api.get(`/gradebooks/${gradebookId}`);
      setFullGradebook(refreshed);
    } catch (err) {
      showError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const handleReopenGradebook = async (reason) => {
    if (!gradebookId) return;
    loadRequestRef.current += 1;
    setSaving(true);
    try {
      await api.post(`/gradebooks/${gradebookId}/reopen`, { reason });
      showSuccess('Gradebook reopened into Draft status.');
      const refreshed = await api.get(`/gradebooks/${gradebookId}`);
      setFullGradebook(refreshed);
    } catch (err) {
      showError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  // 7. Audit and Adjustments Fetchers
  const handleOpenAudit = async () => {
    if (!gradebookId) return;
    try {
      const data = await api.get(`/gradebooks/${gradebookId}/audit`);
      setAuditList(data);
      setShowAudit(true);
    } catch (err) {
      showError(err.message);
    }
  };

  const handleOpenAdjustments = async () => {
    if (!gradebookId) return;
    try {
      const data = await api.get(`/gradebooks/${gradebookId}/adjustments`);
      setAdjustmentsList(data);
      setTeacherAdjustmentCount(data.filter(request => request.status === 'Pending').length);
      setShowAdjustments(true);
    } catch (err) {
      showError(err.message);
    }
  };

  // 8. Breakdown Modal Fetcher
  const handleStudentBreakdown = async (personId) => {
    if (!gradebookId) return;
    if (isDirty) return showError('Save your scores before viewing the official calculation breakdown.');
    try {
      const data = await api.get(`/gradebooks/${gradebookId}/calculation/${personId}`);
      setBreakdownData(data);
    } catch (err) {
      showError(err.message);
    }
  };

  // 9. Export & Print Handlers
  const handleExportXlsx = async (allTerms = false, throughTerm = null) => {
    if (!gradebookId || !fullGradebook) return;
    if (isDirty) return showError('Save your scores before exporting the class record.');

    // Validate required fields
    if (!validateHeaderFields()) {
      return;
    }

    const gb = fullGradebook.gradebook;
    const filename = `ClassRecord-${gb.grade_name}-${gb.section_name}-${gb.subject_name}-${throughTerm === 2 ? 'Terms1-2' : allTerms ? 'AllTerms' : `Term${gb.term_order}`}.xlsx`;
    try {
      const q = new URLSearchParams({
        region,
        division,
        school_id: schoolId,
        all_terms: String(allTerms)
      });
      if (throughTerm) q.set('through_term', String(throughTerm));
      await api.download(`/gradebooks/${gradebookId}/report.xlsx?${q.toString()}`, filename);
    } catch (err) {
      showError(err.message);
    }
  };

  const gb = fullGradebook?.gradebook;
  const activeMapehAreaId = isReviewer ? (gb?.learning_area || 'legacy') : mapehArea;
  const activeMapehArea = MAPEH_AREAS.find((area) => area.id === activeMapehAreaId);
  const sheetLoading = structureLoading || loading;
  const sheetData = sheetLoading ? null : fullGradebook;
  const isEditable = gb && !gb.is_legacy_readonly && ['Draft', 'Submitted'].includes(gb.status) && currentRole === 'teacher';
  const changeContext = (setter, value) => {
    if (saving) return;
    if (isDirty) {
      showError('Save your score changes before switching to another class record.');
      return;
    }
    setter(value);
    return true;
  };

  return (
    <div className="page-stack">


      {/* Tab Navigation */}
      <div className="setup-tabs mb-4">
        <button
          className={activeTab === 'gradebook' ? 'active' : ''}
          onClick={() => setActiveTab('gradebook')}
        >
          Gradebook
        </button>
        <button
          className={activeTab === 'metrics' ? 'active' : ''}
          onClick={() => setActiveTab('metrics')}
        >
          Class Performance Metrics
        </button>
        {canReviewAdjustments && <button className={activeTab === 'adjustments' ? 'active' : ''} onClick={() => setActiveTab('adjustments')}>
          Adjustment Requests
          {adminPendingCount > 0 && <span className="notification-badge">{adminPendingCount}</span>}
        </button>}

      </div>

      {teacherAssignmentConflict && <div className="notice notice-warning" role="alert">
        Your account has active subject assignments in more than one subject for this school year. Gradebooks are unavailable until an administrator corrects the assignments.
      </div>}
      {isTeacher && teacherSubjectIds.size === 0 && <div className="notice notice-warning" role="status">
        No subject is assigned to your account for this school year. Ask an administrator to assign your subject in Administration → Subject Teaching Assignments.
      </div>}

      {(isReviewer ? gb?.subject_name?.trim().toUpperCase()==='MAPEH' : Boolean(learningArea)) && <section className="card-static mapeh-area-selector" aria-labelledby="mapeh-area-heading">
        <div className="mapeh-area-selector__header">
          <div>
            <h3 id="mapeh-area-heading">MAPEH learning areas</h3>
            <p className="muted-small">Choose an area to open its gradebook.</p>
          </div>
          <p className="mapeh-area-selector__current" aria-live="polite">
            <span>Current gradebook</span>
            <strong>{activeMapehArea?.label || 'Legacy MAPEH record'}</strong>
          </p>
        </div>
        <div className="mapeh-area-selector__options" role="group" aria-label="Select a MAPEH learning area">{MAPEH_AREAS.map(area=>{
          const isActive = activeMapehAreaId === area.id;
          return <button type="button" className={`btn-secondary mapeh-area-selector__option${isActive ? ' is-active' : ''}`} key={area.id}
          aria-pressed={isActive}
          onClick={()=>{
            if(isReviewer){const match=existingGradebooks.find(book=>sameMapehContext(book,gb,area.id));if(match)changeContext(setAdminGradebookId,String(match.id));else showError('This learning-area record has not been created yet.');}
            else changeContext(setMapehArea,area.id);
          }}>{area.label}{isActive && <span className="mapeh-area-selector__badge" aria-hidden="true">Current</span>}</button>;
        })}</div>
        {gb?.is_legacy_readonly && <p className="notice">Preserved legacy MAPEH record. Scores and grading rules are read-only; new learning areas start empty.</p>}
        {gb?.learning_area && <p className="muted-small">WW 20% · PT 60% · Exams 20%. Each requested term export requires both learning areas complete and finalized.</p>}
      </section>}

      {activeTab === 'adjustments' && canReviewAdjustments && <GlobalAdjustmentsTab onRefresh={updateAdminPendingCount} />}

      {(activeTab === 'gradebook' || activeTab === 'metrics') && (
        <>
          {isReviewer && <section className="card-static admin-gradebook-picker mb-4" aria-labelledby="admin-gradebook-picker-title">
            <div className="admin-gradebook-picker__header">
              <div>
                <h2 id="admin-gradebook-picker-title">Class records</h2>
                <p>Choose a record to review its grades. Each subject and term has its own record.</p>
              </div>
              {!existingGradebooksLoading && !existingGradebooksError && <span className="admin-gradebook-picker__count" aria-live="polite">
                {filteredGradebookCount} {includeHistoricalGradebooks ? 'saved' : 'current'} {filteredGradebookCount === 1 ? 'record' : 'records'}
              </span>}
            </div>
            <label className="admin-gradebook-picker__search">
              <span className="field-label">Search class records</span>
              <span className="admin-gradebook-picker__search-control">
                <Search size={18} aria-hidden="true" />
                <input className="input-field" type="search" value={adminGradebookSearch}
                  aria-label="Search class records"
                  placeholder="Teacher, subject, grade, section, term, or school year"
                  onChange={(event) => {
                    setAdminGradebookSearch(event.target.value);
                    setAdminGradebookId('');
                    setFullGradebook(null);
                    setGradebookId(null);
                    setLoading(false);
                  }} />
              </span>
            </label>
            {existingGradebooksLoading && <p className="admin-gradebook-picker__message" role="status">Loading class records…</p>}
            {!existingGradebooksLoading && !existingGradebooksError && filteredGradebookCount > 0 && <div className="admin-gradebook-picker__list" aria-label="Available class records">
              {groupedAdminGradebooks.map((group) => <section className="admin-gradebook-picker__group" key={group.label} aria-label={group.label}>
                <div className="admin-gradebook-picker__group-heading">
                  <h3>{group.label}</h3>
                  <span>{group.books.length} {group.books.length === 1 ? 'record' : 'records'}</span>
                </div>
                <div className="admin-gradebook-picker__records">
                  {group.books.map((book) => {
                    const selected = String(book.id) === adminGradebookId;
                    const status = String(book.status || 'Status unavailable');
                    const statusClass = status.toLowerCase() === 'finalized' ? 'is-finalized' : status.toLowerCase() === 'draft' ? 'is-draft' : 'is-unknown';
                    const area = book.learning_area === 'music_arts' ? 'Music and Arts'
                      : book.learning_area === 'pe_health' ? 'PE and Health'
                        : book.is_legacy_readonly ? 'Legacy record' : '';
                    return <button type="button" key={book.id}
                      className={`admin-gradebook-record${selected ? ' is-selected' : ''}`}
                      aria-pressed={selected}
                      onClick={() => {
                        setAdminGradebookId(String(book.id));
                        setFullGradebook(null);
                        setGradebookId(null);
                        setLoading(true);
                      }}>
                      <span className="admin-gradebook-record__topline">
                        <strong>{book.subject_name || 'Subject unavailable'}</strong>
                        <span className={`admin-gradebook-record__status ${statusClass}`}>{status}</span>
                      </span>
                      <span className="admin-gradebook-record__details">
                        <span>Grade {normalizeGradeName(book.grade_name) || '—'} · Section {book.section_name || 'Unassigned'}</span>
                        <span>Teacher: {book.teacher_name || 'Unassigned'}</span>
                      </span>
                      {(area || selected) && <span className="admin-gradebook-record__footer">
                        {area && <span className="admin-gradebook-record__area">{area}</span>}
                        {selected && <span className="admin-gradebook-record__viewing">Viewing</span>}
                      </span>}
                    </button>;
                  })}
                </div>
              </section>)}
            </div>}
            {!existingGradebooksLoading && !existingGradebooksError && existingGradebooks.length === 0 && <p className="admin-gradebook-picker__message">
              {includeHistoricalGradebooks ? 'No saved class records are available.' : 'No current class records are available. Include older records to browse saved history.'}
            </p>}
            {!existingGradebooksLoading && !existingGradebooksError && existingGradebooks.length > 0 && filteredGradebookCount === 0 && <p className="admin-gradebook-picker__message">No records match that search. Try a teacher, subject, section, or term.</p>}
            <label className="checkbox-field admin-gradebook-picker__history">
              <input type="checkbox" checked={includeHistoricalGradebooks}
                onChange={(event) => {
                  setIncludeHistoricalGradebooks(event.target.checked);
                  setExistingGradebooksLoading(true);
                  setExistingGradebooksError('');
                  setAdminGradebookId('');
                  setFullGradebook(null);
                  setGradebookId(null);
                  setLoading(false);
                }} />
              <span>Include older or inactive records</span>
            </label>
            {existingGradebooksError && <p className="notice notice-danger mt-2" role="alert">Could not load class records: {existingGradebooksError}</p>}
          </section>}

          {/* Loading indicator */}
          {activeTab === 'metrics' && sheetLoading && (
            <div className="loading-state-card card-static text-center py-8">
              <Loader2 size={32} className="spin text-primary mx-auto mb-2" />
              <p className="text-muted">Loading gradebook and assessment records...</p>
            </div>
          )}
          {activeTab === 'metrics' && !sheetLoading && !sheetData && isReviewer && (
            <div className="card-static text-center py-8 text-muted">Select an existing class record to view its performance metrics.</div>
          )}

          {/* Main Gradebook Workspace */}
          <>

              {activeTab === 'metrics' && sheetData && (
                <GradebookSummary
                  statistics={fullGradebook.statistics}
                  passingGrade={fullGradebook.gradebook?.passing_grade || 75}
                />
              )}

              {activeTab === 'gradebook' && (
                <>
                  {/* Validation Checklist Panel (when toggled) */}
                  {showValidation && sheetData && (
                    <ValidationChecklist
                      components={fullGradebook.components}
                      students={fullGradebook.students}
                      status={fullGradebook.gradebook?.status}
                      passingGrade={fullGradebook.gradebook?.passing_grade || 75}
                      hasPendingEdits={isDirty}
                      onClose={() => setShowValidation(false)}
                    />
                  )}

                  {/* Interactive Spreadsheet Sheet */}
                  <GradingSheet
                    key={isReviewer ? `admin:${adminGradebookId}` : `${schoolYearId}:${termOrder}:${gradeId}:${sectionId}:${subjectId}:${learningArea}`}
                    gradebook={sheetData?.gradebook}
                    students={sheetData?.students || []}
                    components={sheetData?.components || []}
                    scores={scoreEdits}
                    scoreStatuses={statusEdits}
                    passingGrade={sheetData?.gradebook?.passing_grade || 75}
                    transmutationTable={sheetData?.policy?.transmutation_table}
                    roundingDecimalPlaces={sheetData?.policy?.rounding_decimal_places ?? 2}
                    roundingFinalDecimalPlaces={sheetData?.policy?.rounding_final_decimal_places ?? 0}
                    roundingMethod={sheetData?.policy?.rounding_method ?? 'half_up'}
                    reportingMethod={sheetData?.policy?.reporting_method ?? 'legacy'}
                    disabled={sheetLoading || saving || !isEditable}
                    emptyMessage={isReviewer ? 'Select an existing class record above to view its grades.' : undefined}
                    loading={sheetLoading}
                    onScoreChange={handleScoreChange}
                    onStatusChange={handleStatusChange}
                    onStudentBreakdown={handleStudentBreakdown}
                    region={region}
                    division={division}
                    schoolId={schoolId}
                    selectors={isReviewer ? {} : {
                      schoolYear: (
                        <select className="deped-header-select" value={schoolYearId} onChange={(e) => {
                          const nextYearId = Number(e.target.value);
                          if (changeContext(setSchoolYearId, nextYearId)) {
                            const nextPeriod = (structure.grading_periods || []).find(period => period.school_year_id === nextYearId);
                            if (nextPeriod) setTermOrder(nextPeriod.term_order);
                          }
                        }}>
                          {sortedSchoolYears.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                        </select>
                      ),
                      termOrder: (
                        <select className="deped-header-select" value={termOrder} onChange={(e) => changeContext(setTermOrder, Number(e.target.value))}>
                          {availablePeriods.length === 0 && <option value="">No periods available</option>}
                          {availablePeriods.map((period) => <option key={period.id} value={period.term_order}>{period.name}</option>)}
                        </select>
                      ),
                      grade: (
                        <select className="deped-header-select" value={gradeId} onChange={(e) => changeContext(setGradeId, Number(e.target.value))}>
                          {sortedGradeLevels.map((item) => <option key={item.id} value={item.id}>Grade {normalizeGradeName(item.name)}</option>)}
                        </select>
                      ),
                      section: (
                        <select className="deped-header-select" value={sectionId} onChange={(e) => changeContext(setSectionId, Number(e.target.value))}>
                          {availableSections.length === 0 && <option value="">No sections available</option>}
                          {availableSections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                        </select>
                      ),
                      subject: (
                        <select className="deped-header-select" value={subjectId} onChange={(e) => changeContext(setSubjectId, Number(e.target.value))}>
                          {sortedSubjects.length === 0 && <option value="">No subjects available</option>}
                          {sortedSubjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                        </select>
                      ),
                    }}
                  />

                  {/* Action Toolbar */}
                  {sheetData && <GradebookActions
                    gradebook={fullGradebook.gradebook}
                    isDirty={isDirty}
                    isSaving={saving}
                    onSaveDraft={handleSaveDraft}
                    onOpenConfig={() => setShowConfig(true)}
                    onFinalize={handleFinalizeGradebook}
                    onLock={handleLockGradebook}
                    onReopen={handleReopenGradebook}
                    onOpenAudit={handleOpenAudit}
                    onOpenAdjustments={handleOpenAdjustments}
                    adjustmentCount={teacherAdjustmentCount}
                    onToggleValidation={() => setShowValidation((prev) => !prev)}
                    onExportXlsx={handleExportXlsx}
                    onExportAllTerms={() => Number(fullGradebook.gradebook.term_order) === 2 ? handleExportXlsx(false, 2) : handleExportXlsx(true)}
                    disabled={loading || saving}
                    onValidateFinalize={handleValidateFinalize}
                    finalizationContext={{
                      ...(gb?.learning_area ? { learningArea: activeMapehArea?.label || 'MAPEH learning area' } : {}),
                      term: gb?.term_order,
                    }}
                  />}
                </>
              )}
            </>

          {/* Assessment Component Setup Modal */}
          {showConfig && fullGradebook && isEditable && (
            <AssessmentConfig
              components={fullGradebook.components}
              onSave={handleSaveComponents}
              onClose={() => setShowConfig(false)}
              disabled={saving}
            />
          )}

          {/* Step-by-Step Calculation Breakdown Modal */}
          {breakdownData && (
            <CalculationBreakdown
              breakdown={breakdownData}
              onClose={() => setBreakdownData(null)}
            />
          )}

          {/* Audit History Log Modal */}
          {showAudit && (
            <AuditHistory
              audit={auditList}
              onClose={() => setShowAudit(false)}
            />
          )}

          {/* Post-Finalization Grade Adjustment Requests Modal */}
          {showAdjustments && fullGradebook && (
            <AdjustmentRequestsModal
              gradebookId={gradebookId}
              students={fullGradebook.students}
              components={fullGradebook.components}
              adjustments={adjustmentsList}
              onClose={() => setShowAdjustments(false)}
              onRefresh={handleOpenAdjustments}
            />
          )}
        </>
      )}
    </div>
  );
}
