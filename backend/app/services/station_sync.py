"""Move durable station operations from local SQLite to the school database."""
from datetime import date, datetime, time
import json
import logging
import os
from threading import Event, Thread
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import AttendanceEvent, Person, SchoolYear, StationSyncOperation, User
from ..schemas import PersonCreate
from .enrollment import enrollment_block
from .gate_network import gate_network_settings
from .settings_store import get_json, set_json


logger = logging.getLogger(__name__)
policy_key = "station.last_school_network_policy"
remote_url = os.getenv("EDUSCAN_SYNC_DATABASE_URL", "").strip()
enabled = bool(remote_url and settings.database_url.startswith("sqlite"))
cipher = Fernet(settings.encryption_key)
stop_event = Event()
worker: Thread | None = None


def check_operator(db: Session, user: User, *, gate: bool = False) -> None:
    if not enabled or db.get_bind().dialect.name != "sqlite":
        return
    if user.is_demo:
        raise HTTPException(403, "Use a provisioned school account on this syncing station.")
    if gate and get_json(db, policy_key, None) != "unrestricted":
        raise HTTPException(503, "Gate recording is paused until the school's network policy can be verified.")


def enqueue(db: Session, kind: str, actor: User, payload: dict, *, local_person_id: int,
            operation_id: str | None = None) -> None:
    if not enabled or db.get_bind().dialect.name != "sqlite":
        return
    check_operator(db, actor)
    encoded = cipher.encrypt(json.dumps({"operator": actor.username, **payload}).encode())
    db.add(StationSyncOperation(id=operation_id or str(uuid4()), kind=kind, status="pending",
                                payload=encoded, local_person_id=local_person_id))


def status(db: Session, *, detailed: bool = False) -> dict:
    if not enabled:
        return {"enabled": False}
    counts = dict(db.execute(select(StationSyncOperation.status, func.count())
                             .group_by(StationSyncOperation.status)).all())
    result = {"enabled": True, **{state: counts.get(state, 0) for state in ("pending", "synced", "conflict")}}
    if detailed:
        issues = db.scalars(select(StationSyncOperation).where(StationSyncOperation.status == "conflict")
                           .order_by(StationSyncOperation.created_at.desc(), StationSyncOperation.id.desc()).limit(30))
        result["conflicts"] = [{"id": row.id, "kind": row.kind, "message": row.error} for row in issues]
    return result


class SyncConflict(ValueError):
    pass


def _apply(remote: Session, operation: StationSyncOperation, create_person, *, local_person: Person | None = None) -> None:
    if remote.get(StationSyncOperation, operation.id):
        return
    try:
        data = json.loads(cipher.decrypt(operation.payload or b""))
    except (InvalidToken, ValueError) as error:
        raise SyncConflict("The operation could not be decrypted with this station's key.") from error
    roles = ("admin",) if operation.kind == "enrollment" else ("admin", "scanner")
    actor = remote.scalar(select(User).where(User.username == data["operator"], User.active.is_(True),
                                           User.is_demo.is_(False), User.role.in_(roles)))
    if not actor:
        raise SyncConflict("The school database could not authorize the station operator.")
    if operation.kind == "enrollment":
        payload = data["record"]
        if local_person is not None and (
            local_person.external_id != payload["external_id"] or local_person.lrn != payload["lrn"]
            or local_person.role != payload["role"] or local_person.biometric_consent != payload["biometric_consent"]
        ):
            raise SyncConflict("The local learner ID, role, or consent changed after enrollment.")
        year = remote.scalar(select(SchoolYear.id).where(SchoolYear.name == data["school_year"],
                                                        SchoolYear.deleted_at.is_(None)))
        if not year:
            raise SyncConflict("The student's school year could not be matched.")
        payload["school_year_id"] = year
        create_person(PersonCreate.model_validate(payload), remote, actor, track_sync=False)
    elif operation.kind == "attendance":
        if gate_network_settings(remote).restricted:
            raise SyncConflict("School network restrictions require attendance verification by staff.")
        person = remote.scalar(select(Person).where(Person.external_id == data["external_id"]))
        if (not person or not person.active or person.role != data["role"] or person.lrn != data["lrn"]
                or not person.biometric_consent):
            raise SyncConflict("The student's school record or consent could not be verified.")
        day = date.fromisoformat(data["date"])
        clock = time.fromisoformat(data["time"])
        from .attendance import latest_day_reset
        if enrollment_block(person, day) or latest_day_reset(remote, day):
            raise SyncConflict("Enrollment status or an attendance reset requires staff review.")
        if remote.scalar(select(AttendanceEvent.id).where(
            AttendanceEvent.person_id == person.id, AttendanceEvent.event_date == day,
            AttendanceEvent.event_time == clock, AttendanceEvent.direction == data["direction"],
        )):
            raise SyncConflict("An equivalent attendance event already exists in the school database.")
        remote.add(AttendanceEvent(id=operation.id, person_id=person.id, event_date=day, event_time=clock,
                                   direction=data["direction"], status=data["status"],
                                   recognition_distance=data["distance"], source="Offline gate station",
                                   created_at=datetime.fromisoformat(data["created_at"])))
        from .audit import add_audit
        add_audit(remote, actor, "Sync", "AttendanceEvent", operation.id, "Imported gate attendance",
                  after={"station_id": data["station_id"]})
        from .sms import queue_notice
        event_type = data["sms_type"]
        queue_notice(remote, person, event_type, data["sms_values"],
                     idempotency_key=f"attendance:{operation.id}:{event_type}", commit=False)
    else:
        raise SyncConflict("Unknown station operation.")
    remote.add(StationSyncOperation(id=operation.id, kind=operation.kind, status="receipt"))
    remote.commit()


def sync_pending(local: Session, remote: Session, create_person) -> None:
    policy = "restricted" if gate_network_settings(remote).restricted else "unrestricted"
    if get_json(local, policy_key, None) != policy:
        set_json(local, policy_key, policy)
    for kind in ("enrollment", "attendance"):
        pending = local.scalars(select(StationSyncOperation).where(
            StationSyncOperation.kind == kind, StationSyncOperation.status == "pending",
        ).order_by(StationSyncOperation.created_at, StationSyncOperation.id).limit(100)).all()
        for operation in pending:
            if kind == "attendance" and operation.local_person_id is not None:
                enrollment = local.scalar(select(StationSyncOperation.status).where(
                    StationSyncOperation.kind == "enrollment",
                    StationSyncOperation.local_person_id == operation.local_person_id,
                ).order_by(StationSyncOperation.created_at.desc(), StationSyncOperation.id.desc()).limit(1))
                if enrollment == "pending":
                    continue
                if enrollment == "conflict":
                    operation.status = "conflict"
                    operation.error = "The student's enrollment must be verified before importing attendance."
                    local.commit()
                    continue
            try:
                person = local.get(Person, operation.local_person_id) if operation.local_person_id is not None else None
                local_record_changed = operation.local_person_id is not None and (
                    person is None or not person.active or (kind == "attendance" and not person.biometric_consent)
                )
                if local_record_changed and not remote.get(StationSyncOperation, operation.id):
                    if person is None:
                        operation.payload = None
                    raise SyncConflict("The local school record or consent changed before synchronization.")
                _apply(remote, operation, create_person, local_person=person)
            except (SyncConflict, HTTPException, IntegrityError) as error:
                remote.rollback()
                if remote.get(StationSyncOperation, operation.id):
                    operation.status, operation.payload = "synced", None
                else:
                    operation.status = "conflict"
                    operation.error = str(error) if isinstance(error, SyncConflict) else "The school database rejected the record. Check its ID, LRN, and placement."
            else:
                operation.status, operation.payload = "synced", None
            local.commit()
        if kind == "enrollment" and len(pending) == 100:
            return


def start(create_person) -> None:
    global worker
    if not enabled or (worker and worker.is_alive()):
        return
    try:
        url = make_url(remote_url)
    except ArgumentError:
        logger.error("Station sync database URL is invalid.")
        return
    if url.get_backend_name() != "postgresql" or url.query.get("sslmode") != "verify-full":
        logger.error("Station sync requires a PostgreSQL URL with certificate verification.")
        return
    engine = create_engine(url, pool_size=1, max_overflow=0, pool_pre_ping=True, hide_parameters=True,
                           connect_args={"connect_timeout": 5})
    stop_event.clear()

    def run():
        try:
            while not stop_event.is_set():
                try:
                    with SessionLocal() as local, Session(engine) as remote:
                        sync_pending(local, remote, create_person)
                except SQLAlchemyError:
                    logger.info("School database unavailable for station sync. Pending records will be retried.")
                stop_event.wait(15)
        finally:
            engine.dispose()

    worker = Thread(target=run, name="eduscan-station-sync", daemon=True)
    worker.start()


def stop() -> None:
    stop_event.set()
    if worker:
        worker.join(timeout=2)
