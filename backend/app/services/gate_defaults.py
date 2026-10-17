"""Apply the requested faster cooldown only after the updated server starts."""
from sqlalchemy.orm import Session
from .attendance import attendance_config
from .audit import add_audit
from .settings_store import get_json, set_json


def configure_fast_gate(db: Session) -> bool:
    if get_json(db, 'gate.fast_scan_version', 0) >= 1:
        return False
    before = attendance_config(db)
    after = {**before, 'duplicate_cooldown_seconds': 5}
    set_json(db, 'attendance', after, commit=False)
    set_json(db, 'gate.fast_scan_version', 1, commit=False)
    audit = add_audit(db, None, 'Update', 'AttendanceSettings', 'attendance',
                      'Apply requested five-second gate cooldown with per-visit duplicate protection', before, after)
    audit.actor_name = 'EduScan configuration update'
    db.commit()
    return True
