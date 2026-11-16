from contextlib import closing
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi.testclient import TestClient

import test_attendance_sync as fixtures
from app import main
from app.auth import SESSION_CONTEXT_HEADER, SESSION_COOKIE, hash_password
from app.models import AuthSession


def test_sign_in_sets_httponly_cookie_and_sign_out_revokes_it():
    school = fixtures.AttendanceSyncTest()
    school.setUp()
    try:
        school.admin.password_hash = hash_password("Browser-Test-Password2026!")
        school.db.commit()
        origin = "http://127.0.0.1:5173"
        headers = {"Origin": origin, "X-EduScan-Request": "1"}
        with closing(TestClient(main.app, base_url="https://testserver", headers=headers)) as client:
            response = client.post("/api/auth/login", json={
                "username": "admin", "password": "Browser-Test-Password2026!",
            })
            assert response.status_code == 200
            assert "access_token" not in response.json()
            cookie = response.headers["set-cookie"].lower()
            assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
            assert client.get("/api/auth/me").json()["role"] == "admin"
            stored_cookie = client.cookies.get(SESSION_COOKIE)
            assert school.db.get(AuthSession, sha256(stored_cookie.encode()).hexdigest()) is not None
            assert school.db.get(AuthSession, stored_cookie) is None
            assert client.post("/api/auth/logout", headers={"X-EduScan-Request": ""}).status_code == 403
            assert client.get("/api/auth/me", headers={"Origin": "https://other.test"}).status_code == 403

            assert client.post("/api/auth/logout").status_code == 204
            assert client.get("/api/auth/me").status_code == 401
            assert client.get("/api/auth/me", headers={
                "Cookie": f"{SESSION_COOKIE}={stored_cookie}",
            }).status_code == 401
    finally:
        school.tearDown()


def test_password_change_rotates_the_current_session_and_revokes_other_devices():
    school = fixtures.AttendanceSyncTest()
    school.setUp()
    try:
        password = "Browser-Test-Password2026!"
        school.admin.password_hash = hash_password(password)
        school.db.commit()
        options = {"base_url": "https://testserver", "headers": {"X-EduScan-Request": "1"}}
        with closing(TestClient(main.app, **options)) as first, closing(TestClient(main.app, **options)) as second:
            credentials = {"username": "admin", "password": password}
            assert first.post("/api/auth/login", json=credentials).status_code == 200
            assert second.post("/api/auth/login", json=credentials).status_code == 200
            old_cookie = first.cookies.get(SESSION_COOKIE)
            response = first.post("/api/auth/change-password", json={
                "current_password": password, "new_password": "Updated-Browser-Password2026!",
            })
            assert response.status_code == 200, response.text
            assert first.cookies.get(SESSION_COOKIE) != old_cookie
            assert first.get("/api/auth/me").status_code == 200
            assert second.get("/api/auth/me").status_code == 401
            assert first.get("/api/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={old_cookie}"}).status_code == 401

            school.db.query(AuthSession).filter_by(user_id=school.admin.id).update({
                AuthSession.expires_at: datetime.utcnow() - timedelta(seconds=1),
            })
            school.db.commit()
            assert first.get("/api/auth/me").status_code == 401
    finally:
        school.tearDown()


def test_session_transport_accepts_http_on_loopback_only():
    school = fixtures.AttendanceSyncTest()
    school.setUp()
    try:
        password = "Browser-Test-Password2026!"
        school.admin.password_hash = hash_password(password)
        school.db.commit()
        credentials = {"username": "admin", "password": password}
        headers = {"X-EduScan-Request": "1"}
        with closing(TestClient(main.app, base_url="http://127.0.0.1:8000", headers=headers,
                                client=("127.0.0.1", 49152))) as local:
            response = local.post("/api/auth/login", json=credentials)
            assert response.status_code == 200
            assert "secure" not in response.headers["set-cookie"].lower()
            assert local.get("/api/auth/me").status_code == 200
        with closing(TestClient(main.app, base_url="http://school.test", headers=headers)) as remote:
            response = remote.post("/api/auth/login", json=credentials)
            assert response.status_code == 403
            assert "set-cookie" not in response.headers
    finally:
        school.tearDown()


def test_stale_browser_context_cannot_act_in_a_replaced_session():
    school = fixtures.AttendanceSyncTest()
    school.setUp()
    try:
        password = "Browser-Test-Password2026!"
        school.admin.password_hash = hash_password(password)
        school.teacher.password_hash = hash_password(password)
        school.db.commit()
        options = {"base_url": "https://testserver", "headers": {"X-EduScan-Request": "1"}}
        with closing(TestClient(main.app, **options)) as client:
            assert client.post("/api/auth/login", json={"username": "admin", "password": password}).status_code == 200
            first = client.get("/api/auth/me").json()["session_context"]
            assert client.post("/api/auth/login", json={"username": "teacher", "password": password}).status_code == 200

            response = client.get("/api/persons", headers={SESSION_CONTEXT_HEADER: first})
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "session_changed"
            assert client.post("/api/auth/logout", headers={SESSION_CONTEXT_HEADER: first}).status_code == 409
            current = client.get("/api/auth/me").json()
            assert current["role"] == "teacher"
            assert current["session_context"] != first
    finally:
        school.tearDown()
