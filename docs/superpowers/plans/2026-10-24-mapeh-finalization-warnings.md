# MAPEH Finalization Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give teachers a clear, term-specific error when they try to finalize an incomplete MAPEH learning area or when its partner area is not complete.

**Architecture:** Reuse the existing Finalize validation and error toast. Add a small formatter in the existing MAPEH frontend service for score-completeness errors, and include the selected gradebook's term in the existing server-side partner-area error. Keep both frontend and backend finalization checks in place.

**Tech Stack:** React, JavaScript `node:test`, Python `unittest`, SQLAlchemy.

**Spec:** `docs/superpowers/specs/2026-10-24-mapeh-finalization-warning-design.md`

## Global Constraints

- Keep current score completeness rules, grading calculations, and draft-save behavior unchanged.
- Invalid Finalize attempts show an error after the click and do not open confirmation or finalize either area.
- Drafts remain saveable independently for each area and term.
- Verification uses isolated tests only; do not write to or finalize a live class record.

## Review Focus

- Empty or incomplete selected area in Terms 1, 2, and 3 names that area and term, and says the draft can still be saved.
- Incomplete learner details remain visible in the selected-area warning.
- Missing and incomplete partner areas name the correct partner and selected term.
- Non-score validation errors and complete MAPEH pairs retain their existing behavior.

---

### Task 1: Contextualize selected-area finalization errors

**Files:**
- Modify: `src/services/mapehLearningAreas.js`
- Modify: `src/pages/Grading/Grading.jsx`
- Test: `src/services/mapehLearningAreas.test.js`

**Interfaces:**
- Produce `formatMapehFinalizeIssue(message, areaLabel, term)`, returning a contextualized message only for existing score-completeness errors and otherwise returning the original message unchanged.
- Call the formatter from the existing finalize validation catch only for an active MAPEH learning-area gradebook.

- [x] **Step 1: Add failing formatter tests**

Assert that Terms 1–3 score-completeness messages include `MAPEH Term N`, the selected learning-area label, the original reason, and a Save Draft reminder; incomplete-score messages retain affected learner names; unrelated validation errors remain unchanged.

- [x] **Step 2: Run the focused tests and confirm failure**

Run: `node --test src/services/mapehLearningAreas.test.js`
Expected: FAIL because the formatter is not implemented.

- [x] **Step 3: Implement and connect the formatter**

Implement the formatter in `src/services/mapehLearningAreas.js`. In `Grading.jsx`, pass the error message, selected MAPEH area label, and `fullGradebook.gradebook.quarter` through it in `handleValidateFinalize`; leave non-MAPEH errors unchanged.

- [x] **Step 4: Run the focused frontend tests**

Run: `node --test src/services/mapehLearningAreas.test.js src/services/gradingWorkflow.test.js`
Expected: PASS; existing gradebook validation behavior remains intact.

### Task 2: Name the term in partner-area errors

**Files:**
- Modify: `backend/app/services/mapeh_learning_areas.py`
- Test: `backend/tests/test_mapeh_area_exports.py`

**Interfaces:**
- Keep `partner_gradebook_issue(db, book)` and its server-side finalization guard; include `book.quarter` in messages for a missing or incomplete partner gradebook.

- [x] **Step 1: Add failing partner-message tests**

Using isolated gradebook fixtures for Terms 1–3, assert missing and incomplete partner messages contain the partner area's name and `Term N`. Retain the existing complete-pair test proving finalization can proceed when both areas are complete.

- [x] **Step 2: Run the focused backend test and confirm failure**

Run from `backend`: `.venv\Scripts\python.exe -m unittest tests.test_mapeh_area_exports`
Expected: FAIL because partner-area messages currently say only “this term.”

- [x] **Step 3: Update the existing partner-area messages**

Use the selected book's quarter in both missing-partner and incomplete-partner messages; do not change lookup, completeness rules, or finalization behavior.

- [x] **Step 4: Run MAPEH backend tests**

Run from `backend`: `.venv\Scripts\python.exe -m unittest tests.test_mapeh_area_exports tests.test_mapeh_learning_areas`
Expected: PASS with the finalization guard still blocking an incomplete pair and allowing a complete pair.
