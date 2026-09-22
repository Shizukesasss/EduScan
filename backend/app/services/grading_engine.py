"""Pure-function grading calculation engine for EduScan.

All functions in this module are stateless and have no database or ORM
dependencies.  They receive data as plain dicts/lists and return computed
results.  This makes the engine independently testable and ensures that
every grade produced is deterministic and reproducible.

The calculation flow is:

    Assessment Scores
         ↓
    Component Percentage  (total_earned / total_possible × 100)
         ↓
    Weighted Component Grade  (percentage × weight / 100)
         ↓
    Initial Grade  (sum of weighted component grades)
         ↓
    Transmutation / Reporting Rule  (policy table lookup)
         ↓
    Reported Grade
         ↓
    Status  (Pass / Below Passing / Incomplete)
"""
from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any


# ---------------------------------------------------------------------------
# Default DepEd K-12 transmutation table
# Based on DO 8, s. 2015 piecewise conversion
# ---------------------------------------------------------------------------

def build_default_transmutation_table() -> list[dict]:
    """Build the standard DepEd piecewise transmutation table.

    Returns a list of {"min": float, "max": float, "value": int} entries,
    sorted ascending by min.  The formula is:
      - initial 100         → 100
      - initial 98.40-99.99 → 99
      - ...down to...
      - initial 0-3.99      → 60

    Equivalent piecewise formula:
      if grade >= 100: return 100
      if grade >= 60:  return floor((grade - 60) / 1.6) + 75
      if grade >= 0:   return floor(grade / 4) + 60
    """
    table = []
    # Below 60: 0-3.99 → 60, 4-7.99 → 61, ... 56-59.99 → 74
    for value in range(60, 75):
        low = (value - 60) * 4
        high = low + 3.99
        table.append({"min": float(low), "max": round(high, 2), "value": value})
    # 60 and above: 60-61.59 → 75, 61.60-63.19 → 76, ... 98.40-99.99 → 99
    for value in range(75, 100):
        low = 60 + (value - 75) * 1.6
        high = low + 1.59
        table.append({"min": round(low, 2), "max": round(high, 2), "value": value})
    # Perfect 100
    table.append({"min": 100.0, "max": 100.0, "value": 100})
    return table


DEFAULT_TRANSMUTATION_TABLE = build_default_transmutation_table()


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

_ROUNDING_MODES = {
    "half_up": ROUND_HALF_UP,
    "floor": ROUND_FLOOR,
    "ceiling": ROUND_CEILING,
}


def round_value(
    value: float,
    decimal_places: int = 2,
    method: str = "half_up",
) -> float:
    """Round a numeric value using the configured policy method.

    All rounding in EduScan must go through this function to ensure
    consistency.
    """
    mode = _ROUNDING_MODES.get(method, ROUND_HALF_UP)
    quantize_str = "1." + "0" * decimal_places if decimal_places > 0 else "1"
    result = Decimal(str(value)).quantize(Decimal(quantize_str), rounding=mode)
    return float(result)


# ---------------------------------------------------------------------------
# Component Percentage
# ---------------------------------------------------------------------------

def calculate_component_percentage(
    scores: list[dict],
    items: list[dict],
) -> dict:
    """Calculate the percentage score for a single assessment component.

    Uses the total-score / total-possible method (DepEd standard).
    Partial grading is supported: computation is done using only the
    items that have been graded so far.  'complete' reflects whether
    every item has been scored (used for status labelling only).

    Args:
        scores: list of {"item_id": int, "score": float|None, "status": str}
        items: list of {"id": int, "max_score": float}

    Returns:
        {
            "total_earned": float,
            "total_possible": float,  # only the scored items' max
            "percentage": float|None,
            "complete": bool,
            "scored_count": int,
            "item_count": int,
        }
    """
    score_map = {s["item_id"]: s for s in scores}
    total_earned = 0.0
    total_possible = 0.0  # sum of max_score for scored items only
    scored_count = 0
    complete = True

    for item in items:
        entry = score_map.get(item["id"])
        if not entry or entry.get("status", "Missing") != "Scored":
            complete = False
            continue
        score_val = entry.get("score")
        if score_val is None:
            complete = False
            continue
        total_earned += float(score_val)
        total_possible += float(item["max_score"])
        scored_count += 1

    if total_possible <= 0 or scored_count == 0:
        return {
            "total_earned": 0.0,
            "total_possible": 0.0,
            "percentage": None,
            "complete": False,
            "scored_count": 0,
            "item_count": len(items),
        }

    # Percentage is computed from the graded items only
    percentage = (total_earned / total_possible) * 100.0

    return {
        "total_earned": total_earned,
        "total_possible": total_possible,
        "percentage": percentage,
        "complete": complete,
        "scored_count": scored_count,
        "item_count": len(items),
    }


# ---------------------------------------------------------------------------
# Weighted Grade
# ---------------------------------------------------------------------------

def calculate_weighted_grade(
    component_results: list[dict],
    rounding_decimal_places: int = 2,
    rounding_method: str = "half_up",
) -> dict:
    """Calculate the initial grade from component percentages and weights.

    Partial grading is supported: components that have at least one scored
    item (percentage is not None) contribute to the initial grade.  The
    weights of active components are re-normalised to always sum to 100%
    so that a gradebook with 2 out of 3 components partially filled still
    yields a meaningful grade.  When ALL items in ALL components are scored
    the normalisation factor is 1 and the result is identical to the original
    full-completion formula.

    Args:
        component_results: list of {
            "name": str,
            "weight": float,
            "percentage": float|None,
            "complete": bool,
        }
        rounding_decimal_places: decimal places for intermediate rounding
        rounding_method: rounding method name

    Returns:
        {
            "initial_grade": float|None,
            "complete": bool,
            "component_grades": list of {
                "name": str,
                "percentage": float|None,
                "weight": float,
                "weighted_score": float|None,
            },
        }
    """
    all_complete = True
    component_grades = []

    # Separate components with a computed percentage from empty ones
    active_results = [r for r in component_results if r.get("percentage") is not None]
    inactive_results = [r for r in component_results if r.get("percentage") is None]

    # Check overall completeness
    for result in component_results:
        if result.get("percentage") is None or not result.get("complete", False):
            all_complete = False

    if not active_results:
        # Nothing scored at all
        for result in component_results:
            component_grades.append({
                "name": result.get("name", ""),
                "percentage": None,
                "weight": float(result.get("weight", 0)),
                "weighted_score": None,
            })
        return {
            "initial_grade": None,
            "complete": False,
            "component_grades": component_grades,
        }

    # Re-normalise weights: active components' weights sum → their proportion of 100%
    total_active_weight = sum(float(r.get("weight", 0)) for r in active_results)
    total_all_weight = sum(float(r.get("weight", 0)) for r in component_results)
    # Only re-normalise when some components are inactive
    need_normalise = len(inactive_results) > 0 and total_active_weight > 0
    normalisation_factor = (total_all_weight / total_active_weight) if need_normalise else 1.0

    initial_grade = 0.0
    active_set = {id(r) for r in active_results}

    for result in component_results:
        pct = result.get("percentage")
        weight = float(result.get("weight", 0))
        effective_weight = weight * normalisation_factor if id(result) in active_set else weight

        if pct is None:
            component_grades.append({
                "name": result.get("name", ""),
                "percentage": None,
                "weight": weight,
                "weighted_score": None,
            })
            continue

        weighted = pct * (effective_weight / 100.0)
        initial_grade += weighted
        component_grades.append({
            "name": result.get("name", ""),
            "percentage": round_value(pct, rounding_decimal_places, rounding_method),
            "weight": weight,
            "weighted_score": round_value(weighted, rounding_decimal_places, rounding_method),
        })

    return {
        "initial_grade": round_value(initial_grade, rounding_decimal_places, rounding_method),
        "complete": all_complete,
        "component_grades": component_grades,
    }


# ---------------------------------------------------------------------------
# Transmutation
# ---------------------------------------------------------------------------

def apply_transmutation(
    initial_grade: float,
    transmutation_table: list[dict] | None = None,
) -> int | None:
    """Apply the transmutation/reporting rule to convert an initial grade.

    If no transmutation table is provided, the default DepEd piecewise
    formula is used as a fallback.

    Args:
        initial_grade: the computed initial grade (0-100)
        transmutation_table: list of {"min", "max", "value"} entries

    Returns:
        The transmuted/reported grade as an integer, or None if the initial
        grade is outside all ranges.
    """
    if initial_grade is None:
        return None

    grade = max(0.0, min(100.0, float(initial_grade)))

    if transmutation_table:
        # Use the table: find the range that contains the grade
        for entry in transmutation_table:
            if float(entry["min"]) <= grade <= float(entry["max"]):
                return int(entry["value"])
        # If somehow not found but grade is 100, return 100
        if grade >= 100:
            return 100
        return None

    # Fallback: piecewise formula (same as original EduScan)
    if grade >= 100:
        return 100
    if grade >= 60:
        return int(((grade - 60) + 1e-9) // 1.6) + 75
    return int((grade + 1e-9) // 4) + 60


# ---------------------------------------------------------------------------
# Grade Status
# ---------------------------------------------------------------------------

def determine_grade_status(
    reported_grade: int | None,
    passing_grade: int = 75,
    all_complete: bool = True,
) -> str:
    """Determine the learner's grade status.

    Returns one of: 'Passing', 'Below Passing', 'Incomplete', 'For Remediation'.
    """
    if reported_grade is None or not all_complete:
        return "Incomplete"
    if reported_grade >= passing_grade:
        return "Passing"
    # Below passing — could trigger remediation at school's discretion
    return "Below Passing"


# ---------------------------------------------------------------------------
# Full Student Grade Calculation
# ---------------------------------------------------------------------------

def calculate_student_grade(
    student_scores: list[dict],
    components: list[dict],
    items_by_component: dict[int, list[dict]],
    transmutation_table: list[dict] | None = None,
    passing_grade: int = 75,
    rounding_decimal_places: int = 2,
    rounding_final_decimal_places: int = 0,
    rounding_method: str = "half_up",
) -> dict:
    """Calculate a single student's complete grade from raw scores.

    This is the main entry point that orchestrates the full calculation
    pipeline.

    Args:
        student_scores: all scores for this student across all items
        components: list of {"id", "name", "weight", "component_type"}
        items_by_component: {component_id: [{"id", "max_score", ...}]}
        transmutation_table: policy transmutation table
        passing_grade: configured passing threshold
        rounding_decimal_places: intermediate rounding
        rounding_final_decimal_places: final grade rounding
        rounding_method: rounding method name

    Returns:
        Full calculation result with breakdown.
    """
    score_by_item = {s["item_id"]: s for s in student_scores}

    component_results = []
    for comp in components:
        comp_id = comp["id"]
        comp_items = items_by_component.get(comp_id, [])
        comp_scores = [
            {"item_id": item["id"], "score": score_by_item.get(item["id"], {}).get("score"),
             "status": score_by_item.get(item["id"], {}).get("status", "Missing")}
            for item in comp_items
        ]
        pct_result = calculate_component_percentage(comp_scores, comp_items)
        component_results.append({
            "name": comp.get("name", ""),
            "weight": comp.get("weight", 0),
            "percentage": pct_result["percentage"],
            "complete": pct_result["complete"],
            "total_earned": pct_result["total_earned"],
            "total_possible": pct_result["total_possible"],
            "scored_count": pct_result["scored_count"],
            "item_count": pct_result["item_count"],
        })

    weighted = calculate_weighted_grade(
        component_results, rounding_decimal_places, rounding_method,
    )

    initial_grade = weighted["initial_grade"]
    reported_grade = None
    if initial_grade is not None:
        reported_grade = apply_transmutation(initial_grade, transmutation_table)

    status = determine_grade_status(reported_grade, passing_grade, weighted["complete"])

    return {
        "initial_grade": initial_grade,
        "reported_grade": reported_grade,
        "status": status,
        "complete": weighted["complete"],
        "component_grades": weighted["component_grades"],
        "component_details": component_results,
    }


# ---------------------------------------------------------------------------
# Gradebook Validation
# ---------------------------------------------------------------------------

def validate_gradebook(
    components: list[dict],
    items_by_component: dict[int, list[dict]],
    all_student_scores: dict[int, list[dict]],
    student_ids: list[int],
    weight_total_required: float = 100.0,
) -> list[dict]:
    """Run a validation checklist on a gradebook before saving/submitting.

    Returns a list of validation issues, each as:
        {"level": "error"|"warning", "code": str, "message": str,
         "component_id": int|None, "person_id": int|None}

    An empty list means the gradebook passes all validations.
    """
    issues: list[dict] = []

    # 1. At least one component required
    if not components:
        issues.append({
            "level": "error", "code": "NO_COMPONENTS",
            "message": "At least one assessment component is required.",
            "component_id": None, "person_id": None,
        })
        return issues

    # 2. Weight total
    total_weight = sum(float(c.get("weight", 0)) for c in components)
    if abs(total_weight - weight_total_required) > 0.01:
        issues.append({
            "level": "error", "code": "WEIGHT_TOTAL_INVALID",
            "message": f"Component weights total {total_weight:.2f}% but must be exactly {weight_total_required:.0f}%.",
            "component_id": None, "person_id": None,
        })

    # 3. Individual component validation
    seen_names: set[str] = set()
    for comp in components:
        name = comp.get("name", "").strip()
        comp_id = comp.get("id")

        if not name:
            issues.append({
                "level": "error", "code": "COMPONENT_NO_NAME",
                "message": f"Component at position {comp.get('sequence', '?')} has no name.",
                "component_id": comp_id, "person_id": None,
            })

        name_lower = name.lower()
        if name_lower in seen_names:
            issues.append({
                "level": "warning", "code": "COMPONENT_DUPLICATE_NAME",
                "message": f'Duplicate component name: "{name}".',
                "component_id": comp_id, "person_id": None,
            })
        seen_names.add(name_lower)

        weight = float(comp.get("weight", 0))
        if weight <= 0:
            issues.append({
                "level": "error", "code": "COMPONENT_ZERO_WEIGHT",
                "message": f'Component "{name}" has no weight assigned.',
                "component_id": comp_id, "person_id": None,
            })

        comp_items = items_by_component.get(comp_id, [])
        if not comp_items:
            issues.append({
                "level": "error", "code": "COMPONENT_NO_ITEMS",
                "message": f'Component "{name}" has no assessment items.',
                "component_id": comp_id, "person_id": None,
            })

        # Check items
        for item in comp_items:
            max_score = float(item.get("max_score", 0))
            if max_score <= 0:
                issues.append({
                    "level": "error", "code": "ITEM_INVALID_MAX",
                    "message": f'"{item.get("label", "?")}\" in "{name}" has an invalid maximum score ({max_score}).',
                    "component_id": comp_id, "person_id": None,
                })

    # 4. Student score completeness
    all_item_ids = set()
    for comp_items in items_by_component.values():
        for item in comp_items:
            all_item_ids.add(item["id"])

    for student_id in student_ids:
        scores = all_student_scores.get(student_id, [])
        score_by_item = {s["item_id"]: s for s in scores}
        missing = []
        for item_id in all_item_ids:
            entry = score_by_item.get(item_id)
            if not entry or entry.get("status", "Missing") == "Missing":
                missing.append(item_id)
        if missing:
            issues.append({
                "level": "warning", "code": "STUDENT_MISSING_SCORES",
                "message": f"Student {student_id} has {len(missing)} missing score(s).",
                "component_id": None, "person_id": student_id,
            })

    return issues


# ---------------------------------------------------------------------------
# Calculation Breakdown (for "Why This Grade?" UI)
# ---------------------------------------------------------------------------

def generate_calculation_breakdown(
    student_name: str,
    calculation_result: dict,
    policy_name: str = "",
    passing_grade: int = 75,
) -> dict:
    """Generate a human-readable calculation breakdown for transparency.

    Intended for the "View Calculation" modal in the UI.
    """
    lines = []
    for cg in calculation_result.get("component_grades", []):
        pct = cg.get("percentage")
        weight = cg.get("weight", 0)
        ws = cg.get("weighted_score")
        if pct is not None and ws is not None:
            lines.append({
                "component": cg["name"],
                "percentage": pct,
                "weight": weight,
                "weighted_score": ws,
                "formula": f"{pct:.2f} × {weight:.0f}% = {ws:.2f}",
            })
        else:
            lines.append({
                "component": cg["name"],
                "percentage": pct,
                "weight": weight,
                "weighted_score": ws,
                "formula": "Incomplete",
            })

    return {
        "student_name": student_name,
        "policy_name": policy_name,
        "passing_grade": passing_grade,
        "components": lines,
        "initial_grade": calculation_result.get("initial_grade"),
        "reported_grade": calculation_result.get("reported_grade"),
        "status": calculation_result.get("status"),
        "complete": calculation_result.get("complete", False),
    }
