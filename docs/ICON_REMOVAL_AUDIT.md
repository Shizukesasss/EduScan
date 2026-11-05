# EduScan text-only interface audit — 2026-11-05

## Result

Removed authored interface icons throughout the admin, teacher, scanner, login, and account screens, except the notification bell restored at the user’s request. Kept the existing school seal, avatar initials, attendance donut and legend squares, status pills, and functional progress/status indicators. Routes, API operations, permission checks, event handlers, and data calculations are unchanged.

## Files changed

This list compares against the working files at the start of this task, including pre-existing uncommitted work.

| File | Removal / adjustment |
| --- | --- |
| [index.html](../index.html) | Replaced the scaffold SVG favicon with the existing school seal (logo.png). |
| [package-lock.json](../package-lock.json) | Removed only the Lucide root dependency and package entry; preserved unrelated locked packages. |
| [package.json](../package.json) | Removed the lucide-react dependency. |
| [public/favicon.svg](../public/favicon.svg) | Deleted scaffold SVG icon asset. |
| [public/icons.svg](../public/icons.svg) | Deleted scaffold SVG icon asset. |
| [src/App.css](../src/App.css) | Removed unused scaffold icon classes. |
| [src/assets/react.svg](../src/assets/react.svg) | Deleted scaffold SVG icon asset. |
| [src/assets/vite.svg](../src/assets/vite.svg) | Deleted scaffold SVG icon asset. |
| [src/components/Common/WorkspaceHeader.jsx](../src/components/Common/WorkspaceHeader.jsx) | Removed Lucide imports and corresponding rendered icons: Bell, Camera, ChevronDown, KeyRound, LogOut, Menu, User, X. Navigation is text-only; Notifications uses a standalone bell SVG with its accessible name and queue dot; mobile navigation uses Menu / Close menu. |
| [src/components/Grading/AdjustmentRequestsModal.jsx](../src/components/Grading/AdjustmentRequestsModal.jsx) | Removed Lucide imports and corresponding rendered icons: Plus, X, Trash2. |
| [src/components/Grading/AssessmentConfig.jsx](../src/components/Grading/AssessmentConfig.jsx) | Removed Lucide imports and corresponding rendered icons: CheckCircle, ChevronDown, ChevronRight, Plus, Trash2, X. |
| [src/components/Grading/AuditHistory.css](../src/components/Grading/AuditHistory.css) | Removed reserved search-icon padding; aligned uppercase table headings. |
| [src/components/Grading/AuditHistory.jsx](../src/components/Grading/AuditHistory.jsx) | Removed Lucide imports and corresponding rendered icons: X, Search. |
| [src/components/Grading/CalculationBreakdown.jsx](../src/components/Grading/CalculationBreakdown.jsx) | Removed Lucide imports and corresponding rendered icons: X. |
| [src/components/Grading/GlobalAdjustmentsTab.jsx](../src/components/Grading/GlobalAdjustmentsTab.jsx) | Removed Lucide imports and corresponding rendered icons: Loader2, CheckCircle2, XCircle. |
| [src/components/Grading/GradingSheet.css](../src/components/Grading/GradingSheet.css) | Removed orphaned search-icon styles. |
| [src/components/Grading/GradingSheet.jsx](../src/components/Grading/GradingSheet.jsx) | Removed Lucide imports and corresponding rendered icons: Search, Calculator, ArrowUpDown. Sort state reads Name A–Z or Grade high–low. |
| [src/components/Grading/ValidationChecklist.jsx](../src/components/Grading/ValidationChecklist.jsx) | Removed Lucide imports and corresponding rendered icons: X. |
| [src/components/Scanner/StudentRegistrationModal.jsx](../src/components/Scanner/StudentRegistrationModal.jsx) | Removed Lucide imports and corresponding rendered icons: X, Camera, ScanFace, CheckCircle, Database, AlertTriangle. |
| [src/components/Setup/BiometricEnrollmentManager.jsx](../src/components/Setup/BiometricEnrollmentManager.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, Eye, History, RefreshCw, ScanFace, Trash2, UserPlus, X. |
| [src/components/Setup/PersonnelScheduleManager.jsx](../src/components/Setup/PersonnelScheduleManager.jsx) | Removed Lucide imports and corresponding rendered icons: Clock3, Pencil, Save, Trash2. |
| [src/components/Teacher/SF2ReportGenerator.jsx](../src/components/Teacher/SF2ReportGenerator.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, ChevronDown, Download, FileSpreadsheet, Upload. |
| [src/components/Teacher/StudentProfileModal.jsx](../src/components/Teacher/StudentProfileModal.jsx) | Removed Lucide imports and corresponding rendered icons: X. |
| [src/contexts/ToastContext.jsx](../src/contexts/ToastContext.jsx) | Removed Lucide imports and corresponding rendered icons: CheckCircle2, AlertTriangle, X. Added visible Success / Error / Attention / Notice headings. |
| [src/index.css](../src/index.css) | Removed unused scaffold icon-filter styling. |
| [src/layouts/AdminLayout.jsx](../src/layouts/AdminLayout.jsx) | Removed Lucide imports and corresponding rendered icons: Database, FileSpreadsheet, FileText, LayoutDashboard, SlidersHorizontal, Users. |
| [src/layouts/TeacherLayout.jsx](../src/layouts/TeacherLayout.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, CalendarClock, ChevronDown, ChevronUp, ClipboardCheck, FileSpreadsheet, FileText, Users. Welcome-card disclosure uses Expand / Collapse. |
| [src/pages/Account/AccountSecurity.jsx](../src/pages/Account/AccountSecurity.jsx) | Removed Lucide imports and corresponding rendered icons: KeyRound, LogOut, ShieldCheck. |
| [src/pages/Administration/Administration.jsx](../src/pages/Administration/Administration.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, CheckCircle2, ChevronDown, Pencil, Save, ShieldAlert, Trash2, UserCog, Users, UserCheck. Replaced the custom sort SVG with Sort / Ascending / Descending and aria-sort. |
| [src/pages/Attendance/Attendance.css](../src/pages/Attendance/Attendance.css) | Removed search-icon positioning; resized the Clear button and input padding; replaced plus/minus disclosure markers with Show details / Hide details. |
| [src/pages/Attendance/Attendance.jsx](../src/pages/Attendance/Attendance.jsx) | Removed Lucide imports and corresponding rendered icons: ChevronDown, Clock3, Download, Eraser, FileEdit, RefreshCw, Search, ShieldCheck, UserRoundCheck, X. |
| [src/pages/Dashboard/Dashboard.jsx](../src/pages/Dashboard/Dashboard.jsx) | Removed Lucide imports and corresponding rendered icons: Camera. |
| [src/pages/Grading/Grading.css](../src/pages/Grading/Grading.css) | Removed orphaned action SVG sizing. |
| [src/pages/Grading/Grading.jsx](../src/pages/Grading/Grading.jsx) | Removed Lucide imports and corresponding rendered icons: Check, ChevronRight, Loader2, Search. |
| [src/pages/Login/Login.jsx](../src/pages/Login/Login.jsx) | Removed Lucide imports and corresponding rendered icons: Lock, User, AlertCircle, Info, Eye, EyeOff. Password visibility uses Show / Hide. |
| [src/pages/Operations/OperationalControls.jsx](../src/pages/Operations/OperationalControls.jsx) | Removed Lucide imports and corresponding rendered icons: ArchiveRestore, DatabaseBackup, Download, RefreshCw, Search, ShieldCheck. |
| [src/pages/Reports/Reports.css](../src/pages/Reports/Reports.css) | Removed orphaned heading and action SVG styles. |
| [src/pages/Reports/Reports.jsx](../src/pages/Reports/Reports.jsx) | Removed Lucide imports and corresponding rendered icons: Download, FileClock, FileSpreadsheet, Printer. |
| [src/pages/Scanner/Scanner.jsx](../src/pages/Scanner/Scanner.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, Camera, CheckCircle2, ChevronDown, Clock3, KeyRound, LayoutDashboard, LogOut, Maximize2, Menu, Minimize2, RefreshCw, ScanFace, UserPlus, Wifi, WifiOff, X. Removed decorative standby reticle and empty icon containers; kept explicit camera/fullscreen/menu labels. |
| [src/pages/Setup/SystemSetup.jsx](../src/pages/Setup/SystemSetup.jsx) | Removed Lucide imports and corresponding rendered icons: MessageSquareText, Network, Save, ShieldCheck, Smartphone. |
| [src/pages/Teacher/MyAdvisory.jsx](../src/pages/Teacher/MyAdvisory.jsx) | Removed Lucide imports and corresponding rendered icons: Search. |
| [src/pages/Teacher/TruancyInterventions.jsx](../src/pages/Teacher/TruancyInterventions.jsx) | Removed Lucide imports and corresponding rendered icons: AlertTriangle, Phone, Calendar, Plus, X. |
| [src/styles/index.css](../src/styles/index.css) | Removed CSS dropdown/legacy disclosure chevrons, icon sizing/containers, and orphaned SVG styles. Added text-control sizing, visible labels/focus states, alert borders, sort labels, input padding, and responsive header spacing. |
| docs/ICON_REMOVAL_AUDIT.md | Added this file-by-file audit and verification record. |

## Design decisions

- Navigation uses muted labels, consistent gaps, blue underline, semibold weight, and an active tinted background. Header actions wrap where needed to preserve readable labels.
- Scanner and gate-station actions retain primary blue styling and balanced padding. Notification and account controls retain visible hover/focus states.
- Icon-only close, clear, password, mobile menu, and disclosure controls now have visible words. Existing accessible names and interaction handlers are retained.
- Search fields no longer reserve icon gutters. Sort controls use text and the academic table exposes aria-sort. Uppercase table headings use restrained letter-spacing.
- Alerts use semantic tints/borders; toast headings name severity. Empty-state headings and helper text carry the meaning. Decorative containers were removed.

## Verification

- `npm run verify`: lint and production build pass. Existing lint warning in tmp/ui-review/cdp.mjs and the large-chunk build advisory remain.
- `node --test tests/*.test.js src/services/*.test.js`: 99 passed, 1 failed. The attendance-route test expects Recognition review queue during server-side rendering, but the component renders Loading operational records. The identical failure was reproduced against the pre-edit source snapshot (icon imports stubbed solely to load that snapshot).
- Local isolated-browser checks used synthetic data, without changing school records. Checked admin routes at desktop size; overview at 1920, 1440, 1024, and 390 pixels; scanner at 768 and 390; login at 390. Fixed scanner tablet overflow and mobile overlay spacing. A focused review also restored the Captured text badge contrast over camera video. Confirmed no empty text controls in those rendered states, and the mobile notification popover stays in the viewport.
- Final source search covers src, public, backend, scripts, index.html, package.json, and package-lock.json for icon libraries/fonts, inline SVGs, SVG data URLs, icon-font tags, and emoji. No icon-library imports, icon fonts, CSS image icons, or emoji icons remain. The frontend SVGs are the **notification bell explicitly retained by the user** in WorkspaceHeader.jsx and the **functional attendance donut** in Dashboard.jsx. No standalone SVG assets remain in src or public.

## Review notes and intentional boundaries

- Text actions require more space: the workspace header wraps at intermediate widths; the mobile header keeps the name and role visible and exposes navigation through Menu. Review this header density with your usual screen size.
- Notifications still indicates configured review queues, matching existing behavior. There is no unread-count/read-state model; this change does not invent one.
- Google Identity renders its own branded sign-in button when configured. That externally controlled branding is retained to preserve the existing authentication integration. It is not an authored icon dependency or SVG in this codebase.
- Native browser affordances (select/date controls, checkbox marks) and official SF2 attendance checkmarks remain functional controls/report data. They are not decorative interface icons.
- Camera recognition/enrollment, live school data, and externally rendered Google sign-in were not exercised; layout checks used empty/sample states.

## Notification bell follow-up

Restored the notification bell as a standalone inline SVG, without reinstalling an icon package. The compact button retains its Notifications accessible name, queue indicator, hover/focus states, and existing popover behavior. Other controls remain text-only.
