"""Coalesce gate Excel updates outside the attendance response path."""
import logging
import threading
from datetime import date

from ..database import SessionLocal
from .sf2 import generate_temporary_log

logger = logging.getLogger(__name__)
_state_lock = threading.Lock()
_pending_days: set[date] = set()
_running = False


def update_gate_export(day: date):
    with _state_lock:
        _pending_days.add(day)
    retry_gate_exports()


def retry_gate_exports():
    global _running
    with _state_lock:
        if _running:
            return
        _running = True
    failed: set[date] = set()
    while True:
        with _state_lock:
            available = _pending_days - failed
            if not available:
                _running = False
                return
            target = min(available)
            _pending_days.remove(target)
        try:
            # A response's session has already ended; the worker owns its session.
            with SessionLocal() as db:
                generate_temporary_log(db, target)
        except Exception:
            # shortcut: retries are process-local; persist them if they must survive server restarts.
            with _state_lock:
                _pending_days.add(target)
            failed.add(target)
            logger.exception('Could not refresh the temporary gate attendance export for %s', target)
