"""DepEd identity and API boundaries, using disposable SQLite and no Google calls."""
from dataclasses import replace
from datetime import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text, create_engine, inspect

import test_attendance_sync as fixtures
from app import auth, main
from app.models import User, ClassSchedule
from app.migrations import MIGRATIONS, run_migrations
from app.services import google_login, password_recovery


def claims(**changes):
    return {"sub": "google-sub-123", "email": "new.teacher@deped.gov.ph",
            "email_verified": True, "hd": "deped.gov.ph", "name": "New Teacher",
            "nonce": "a" * 40, **changes}


@pytest.fixture
def school(monkeypatch):
    fixture = fixtures.AttendanceSyncTest()
    fixture.setUp()
    configured = replace(main.settings, google_client_id="school.apps.googleusercontent.com", deped_only=True,
                         deped_password_recovery=False)
    for module in (main, auth, google_login, password_recovery):
        monkeypatch.setattr(module, "settings", configured)
    yield fixture
    fixture.tearDown()


def test_verified_deped_identity_creates_one_teacher_without_password_or_assignments(school):
    first = google_login.google_user(school.db, claims())
    second = google_login.google_user(school.db, claims(name="Changed display name"))
    assert first.id == second.id
    assert first.role == "teacher"
    assert first.google_email == "new.teacher@deped.gov.ph"
    assert first.google_sub == "google-sub-123"
    assert not first.must_change_password
    assert not auth.verify_password("", first.password_hash)
    assert main.adviser_sections(school.db, first) == []
    assert school.db.scalar(select(User).where(User.google_sub == "google-sub-123")).id == first.id


@pytest.mark.parametrize("changes", [
    {"hd": None}, {"hd": "gmail.com"}, {"hd": "sub.deped.gov.ph"},
    {"email": "teacher@gmail.com"}, {"email": "teacher@deped.gov.ph.evil.test"},
    {"email_verified": False}, {"email_verified": "true"}, {"sub": ""},
])
def test_invalid_domain_or_unverified_identity_is_rejected(school, changes):
    with pytest.raises(HTTPException) as failure:
        google_login.google_user(school.db, claims(**changes))
    assert failure.value.status_code in (401, 403)
    assert school.db.query(User).count() == 2


def test_google_verifier_checks_audience_and_nonce(school):
    with patch.object(google_login.id_token, "verify_oauth2_token", return_value=claims()) as verify:
        assert google_login.verify_google_credential("signed-token", "a" * 40)["sub"] == "google-sub-123"
        assert verify.call_args.kwargs["audience"] == "school.apps.googleusercontent.com"
        with pytest.raises(HTTPException) as failure:
            google_login.verify_google_credential("signed-token", "b" * 40)
        assert failure.value.status_code == 401


def test_verifier_rejects_bad_signatures_expiry_and_network_errors(school):
    from google.auth.exceptions import TransportError
    for error, status in [(ValueError("bad token"), 401), (TransportError("offline"), 503)]:
        with patch.object(google_login.id_token, "verify_oauth2_token", side_effect=error):
            with pytest.raises(HTTPException) as failure:
                google_login.verify_google_credential("bad-token", "a" * 40)
            assert failure.value.status_code == status


def test_explicit_email_reservation_preserves_admin_and_binds_verified_subject(school):
    google_login.reserve_google_email(school.db, "admin", "Head@deped.gov.ph")
    result = google_login.google_user(school.db, claims(email="head@deped.gov.ph"))
    assert result.id == school.admin.id
    assert result.role == "admin"
    assert result.google_sub == "google-sub-123"
    assert not result.must_change_password


def test_display_name_or_username_never_links_an_existing_admin(school):
    result = google_login.google_user(school.db, claims(name=school.admin.full_name, email="admin@deped.gov.ph"))
    assert result.id != school.admin.id
    assert result.role == "teacher"


def test_inactive_and_changed_subject_cannot_take_over_linked_account(school):
    result = google_login.google_user(school.db, claims())
    with pytest.raises(HTTPException) as failure:
        google_login.google_user(school.db, claims(sub="another-subject"))
    assert failure.value.status_code == 409
    result.active = False
    school.db.commit()
    with pytest.raises(HTTPException) as failure:
        google_login.google_user(school.db, claims())
    assert failure.value.status_code == 403


def test_reservation_rejects_duplicates_relinking_and_wrong_domain(school):
    google_login.reserve_google_email(school.db, "admin", "head@deped.gov.ph")
    for username, email in [("teacher", "head@deped.gov.ph"), ("admin", "other@deped.gov.ph"),
                            ("teacher", "person@gmail.com"), ("missing", "person@deped.gov.ph")]:
        with pytest.raises((ValueError, HTTPException)):
            google_login.reserve_google_email(school.db, username, email)


def test_identity_migration_preserves_legacy_users_and_runs_once():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description VARCHAR(255), applied_at TIMESTAMP)"))
        for version, description in MIGRATIONS:
            if version != "0032_google_identity":
                connection.execute(text("INSERT INTO schema_migrations VALUES (:v,:d,CURRENT_TIMESTAMP)"), {"v": version, "d": description})
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80))"))
        connection.execute(text("INSERT INTO users VALUES (1,'admin')"))
    assert run_migrations(engine) == ["0032_google_identity"]
    assert run_migrations(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT username,google_sub,google_email FROM users")).one() == ("admin", None, None)
        assert {c["name"] for c in inspect(connection).get_columns("users")} >= {"google_sub", "google_email"}
    engine.dispose()


def google_sign_in(school, **changes):
    with patch.object(google_login.id_token, "verify_oauth2_token", return_value=claims(**changes)):
        return school.client.post("/api/auth/google", json={"credential": "signed-token", "nonce": "a" * 40})


def test_api_google_login_creates_session_and_denies_admin_routes(school):
    response = google_sign_in(school)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["role"] == "teacher"
    assert result["auth_provider"] == "google"
    assert result["must_change_password"] is False
    headers = {"Authorization": f"Bearer {result['access_token']}"}
    assert school.client.get("/api/auth/me", headers=headers).status_code == 200
    assert school.client.get("/api/admin/users", headers=headers).status_code == 403
    assert school.client.get("/api/persons?scope=assigned", headers=headers).json() == []
    assert school.client.get("/api/my/advisory-sections", headers=headers).json() == []
    assert school.client.get("/api/gradebooks", headers=headers).json() == []


def test_strict_mode_rejects_password_login_and_existing_password_sessions(school):
    response = school.client.post("/api/auth/login", json={"username": "admin", "password": "anything"})
    assert response.status_code == 403
    response = school.client.get("/api/auth/me", headers=school.admin_headers)
    assert response.status_code == 401


def test_google_account_cannot_use_local_password_change(school):
    result = google_sign_in(school).json()
    response = school.client.post("/api/auth/change-password",
        headers={"Authorization": f"Bearer {result['access_token']}"},
        json={"current_password": "anything", "new_password": "Strong-New-Password123!"})
    assert response.status_code == 403


def test_google_account_never_inherits_unlinked_name_based_schedule(school):
    school.db.add(ClassSchedule(grade="10", section="Rizal", subject="Mathematics",
        teacher_name="New Teacher", start_time=time(7), end_time=time(8), teacher_user_id=None))
    school.db.commit()
    result = google_sign_in(school).json()
    response = school.client.get("/api/schedules", headers={"Authorization": f"Bearer {result['access_token']}"})
    assert response.status_code == 200
    assert response.json() == []


def test_missing_configuration_fails_closed_and_exposes_setup_state(school, monkeypatch):
    configured = replace(main.settings, google_client_id="")
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(google_login, "settings", configured)
    response = school.client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json() == {"google_client_id": "", "deped_only": True, "allowed_domain": "deped.gov.ph",
                               "deped_password_recovery": False}
    assert google_sign_in(school).status_code == 503


def test_google_endpoint_requires_nonce_and_rejects_unverified_claims(school):
    assert school.client.post("/api/auth/google", json={"credential": "bad"}).status_code == 422
    assert google_sign_in(school, email_verified=False).status_code == 403


def test_legacy_rollout_mode_keeps_unlinked_password_login_only(school, monkeypatch):
    configured = replace(main.settings, deped_only=False)
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(auth, "settings", configured)
    school.admin.password_hash = auth.hash_password("Test-Local-Password123!")
    school.db.commit()
    response = school.client.post("/api/auth/login", json={"username": "admin", "password": "Test-Local-Password123!"})
    assert response.status_code == 200
    google_login.reserve_google_email(school.db, "admin", "head@deped.gov.ph")
    assert school.client.post("/api/auth/login", json={"username": "admin", "password": "Test-Local-Password123!"}).status_code == 403


def test_concurrent_identity_insert_recovers_by_reloading_existing_user(school):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    original_commit = school.db.commit
    attempts = 0

    def competing_commit():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            school.db.rollback()
            # Model the winning request's committed row, rather than merely retrying an insert.
            with Session(school.engine) as competing:
                competing.add(User(username="winner", full_name="Other Request", role="teacher",
                    google_sub="google-sub-123", google_email="new.teacher@deped.gov.ph",
                    password_hash="!google-only", active=True, must_change_password=False))
                competing.commit()
            raise IntegrityError("concurrent identity", {}, Exception("unique conflict"))
        original_commit()

    with patch.object(school.db, "commit", side_effect=competing_commit):
        result = google_login.google_user(school.db, claims())
    assert attempts == 2
    assert result.role == "teacher"
    assert result.username == "winner"
    assert school.db.query(User).filter(User.google_sub == "google-sub-123").count() == 1


def test_real_signature_audience_issuer_expiry_and_nonce_are_checked(school):
    """Only the certificate HTTP response is replaced; google-auth verifies real RSA JWTs."""
    import json
    import time as clock
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from google.auth import crypt, jwt

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = crypt.RSASigner.from_string(pem, key_id="test-key")
    now = int(clock.time())
    valid = {**claims(), "iat": now, "exp": now + 300, "aud": "school.apps.googleusercontent.com", "iss": "https://accounts.google.com"}
    certificate_response = SimpleNamespace(status=200, data=json.dumps({"test-key": public.decode()}).encode())
    with patch.object(google_login._GoogleRequest, "__call__", return_value=certificate_response):
        token = jwt.encode(signer, valid).decode()
        assert google_login.verify_google_credential(token, "a" * 40)["sub"] == "google-sub-123"
        for changed in ({"aud": "attacker-client"}, {"iss": "https://attacker.test"},
                        {"iat": now - 600, "exp": now - 300}, {"nonce": "different"}):
            with pytest.raises(HTTPException) as failure:
                google_login.verify_google_credential(jwt.encode(signer, {**valid, **changed}).decode(), "a" * 40)
            assert failure.value.status_code == 401
        pieces = token.split(".")
        pieces[2] = ("A" if pieces[2][0] != "A" else "B") + pieces[2][1:]
        with pytest.raises(HTTPException) as failure:
            google_login.verify_google_credential(".".join(pieces), "a" * 40)
        assert failure.value.status_code == 401


def test_google_endpoint_rejects_untrusted_browser_origin(school):
    response = school.client.post("/api/auth/google", headers={"Origin": "https://attacker.test"},
        json={"credential": "signed-token", "nonce": "a" * 40})
    assert response.status_code == 403


def test_explicit_subject_keeps_role_and_disabled_users_stay_blocked_at_api(school):
    google_login.reserve_google_email(school.db, "admin", "head@deped.gov.ph")
    response = google_sign_in(school, email="head@deped.gov.ph")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert school.client.get("/api/admin/users", headers=headers).status_code == 200
    school.db.refresh(school.admin)
    school.admin.active = False
    school.db.commit()
    assert google_sign_in(school, email="head@deped.gov.ph").status_code == 403
    assert school.client.get("/api/auth/me", headers=headers).status_code == 401


def test_strict_admin_cannot_create_unusable_local_password_account(school):
    google_login.reserve_google_email(school.db, "admin", "head@deped.gov.ph")
    result = google_sign_in(school, email="head@deped.gov.ph").json()
    response = school.client.post("/api/admin/users", headers={"Authorization": f"Bearer {result['access_token']}"},
        json={"username": "local-new", "password": "Strong-Password-123!", "role": "teacher", "full_name": "Local Teacher"})
    assert response.status_code == 403
    assert school.db.scalar(select(User).where(User.username == "local-new")) is None


def test_admin_password_reset_does_not_lock_google_teacher_out_of_workspace(school):
    google_login.reserve_google_email(school.db, "admin", "head@deped.gov.ph")
    admin_result = google_sign_in(school, email="head@deped.gov.ph", sub="admin-subject").json()
    teacher_result = google_sign_in(school).json()
    teacher = school.db.scalar(select(User).where(User.google_sub == "google-sub-123"))
    response = school.client.put(f"/api/admin/users/{teacher.id}",
        headers={"Authorization": f"Bearer {admin_result['access_token']}"},
        json={"role": "teacher", "full_name": "Teacher", "active": True, "new_password": "Strong-Password-123!"})
    assert response.status_code == 403
    response = school.client.get("/api/auth/me", headers={"Authorization": f"Bearer {teacher_result['access_token']}"})
    assert response.json()["must_change_password"] is False


def test_local_setup_command_reserves_existing_role_without_claiming_verification(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy.orm import Session
    backend = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "setup.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    run_migrations(engine)
    with Session(engine) as db:
        db.add(User(username="school-head", full_name="School Administrator", role="admin", password_hash="unused", active=True))
        db.commit()
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database_path.as_posix()}", "EDUSCAN_DATA_DIR": str(tmp_path / "data")}
    command = [sys.executable, str(backend / "tools/link_google_account.py"), "--username", "school-head", "--email", "head@deped.gov.ph"]
    response = subprocess.run(command, cwd=backend, env=environment, text=True, capture_output=True, timeout=30)
    assert response.returncode == 0, response.stderr
    assert "Ownership will be verified by Google at first sign-in" in response.stdout
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == "school-head"))
        assert user.role == "admin"
        assert user.google_email == "head@deped.gov.ph"
        assert user.google_sub is None
    engine.dispose()
