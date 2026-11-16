"""Cookie-session helpers for tests that switch between synthetic users."""

from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE, SESSION_REQUEST_HEADER, issue_session


class BrowserTestClient(TestClient):
    def __init__(self, app, **kwargs):
        # This suite explicitly selects a session on each authenticated request.
        super().__init__(app, base_url="https://testserver",
                         headers={SESSION_REQUEST_HEADER: "1", "Cookie": ""}, **kwargs)


def _session_headers(token):
    assert token is not None
    return {"Cookie": f"{SESSION_COOKIE}={token}", SESSION_REQUEST_HEADER: "1"}


def issued_session_headers(db, user):
    token = issue_session(db, user)
    db.commit()
    return _session_headers(token)


def response_session_headers(response):
    return _session_headers(response.cookies.get(SESSION_COOKIE))
