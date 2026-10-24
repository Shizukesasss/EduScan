# Ten-record pagination design

Approved in conversation on 24 October 2026.

Reduce scrolling across growing record tables and selectable lists for every authorized role. The user chose fixed 10 records per page over a 10/25/50 selector or Load more.

Each independent list owns its page. Show Previous/Next, bounded numbered pages and “1–10 of 83 records”. Hide controls for 10 or fewer records. Preserve empty states. Filter and sort the whole collection before slicing; reset on search/filter/context changes and clamp after removal. Refresh alone should not unnecessarily reset the page.

Preserve selected section IDs and unsaved scores across pages. Select all continues to mean all eligible sections. Preserve global learner numbering and male/female groups, counting learners toward the ten-row limit. Totals, validation, saves and exports always use complete collections.

Apply to growing lists in Administration, Oversight, Attendance, Reports, System Setup and teacher workspaces, including gradebook learner rows and section-selection cards. Exclude short static reference tables, school metadata and assessment/calculation detail fields. Inspect existing API response caps and never present loaded-record counts as complete database totals.

No database writes, grading changes, permission changes, new dependencies or destructive cleanup. Verify empty/10/11/21 records, off-page search, independent tables, page clamping, cross-page selection/score edits, keyboard navigation and complete exports using isolated fixtures.
