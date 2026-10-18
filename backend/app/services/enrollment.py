from datetime import date

STUDENT_STATUSES = {"Regular", "Transferred In", "Transferred Out", "Dropped Out", "Withdrawn", "Graduated", "Other"}
STAFF_STATUSES = {"Regular", "Appointed", "Transferred In", "Transferred Out", "Resigned", "Retired", "Contract Ended", "Other"}
DEPARTURE_STATUSES = {"Transferred Out", "Dropped Out", "Withdrawn", "Graduated", "Resigned", "Retired", "Contract Ended", "Other"}


def enrollment_error(role, status, starts_on, ends_on, note=None):
    if len(note or "") > 1000:
        return "Enrollment / employment notes must be at most 1000 characters"
    if status not in (STUDENT_STATUSES if role == "Student" else STAFF_STATUSES):
        return "Choose an enrollment or employment status appropriate to this person's role"
    if starts_on and ends_on and starts_on > ends_on:
        return "The start date cannot be after the last enrolled / duty date"
    if status in {"Transferred In", "Appointed"} and not starts_on:
        return "A start date is required for an appointment or transfer in"
    if status in DEPARTURE_STATUSES and not ends_on:
        return "A last enrolled / duty date is required for a departure"
    if status == "Other" and not (note or "").strip():
        return "Describe the departure reason when selecting Other"


def enrollment_block(person, day: date):
    if person.enrollment_start_date and day < person.enrollment_start_date:
        return "Not Enrolled" if person.role == "Student" else "Not Started"
    if person.enrollment_end_date and day > person.enrollment_end_date:
        if person.enrollment_status in DEPARTURE_STATUSES:
            return person.enrollment_status
        return "Enrollment Ended" if person.role == "Student" else "Service Ended"
    if person.enrollment_status in DEPARTURE_STATUSES and not person.enrollment_end_date:
        # Legacy departures without dates cannot safely create new attendance.
        return person.enrollment_status


def enrollment_remark(person, through: date):
    status = person.enrollment_status
    if status in DEPARTURE_STATUSES:
        if person.enrollment_end_date and person.enrollment_end_date > through:
            return ""
        detail = f"Last enrolled / duty date: {person.enrollment_end_date or 'not recorded'}"
    elif status == "Transferred In":
        if person.enrollment_start_date and person.enrollment_start_date > through:
            return ""
        detail = f"Start date: {person.enrollment_start_date or 'not recorded'}"
    else:
        return ""
    if status in {"Transferred In", "Transferred Out"} and person.transfer_school:
        detail += f"; {person.transfer_school}"
    if person.enrollment_note:
        detail += f"; {person.enrollment_note}"
    return f"{status.upper()}: {detail}"
