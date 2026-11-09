"""Recovery through verified DepEd mailboxes using isolated accounts."""
import re
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import text

from test_google_login import claims, school
from app import auth, main
from app.services import google_login


def enable(monkeypatch):
    from app.services import password_recovery

    config = replace(main.settings, deped_password_recovery=True, smtp_host='smtp.example.test',
                     smtp_from='school@example.test')
    for module in (auth, main, password_recovery):
        monkeypatch.setattr(module, 'settings', config)
    messages = []
    monkeypatch.setattr(password_recovery, 'send_email', lambda *args: messages.append(args))
    return messages


def request_code(school, email):
    return school.client.post('/api/auth/password-reset/request', json={'email': email})


def reset(school, email, code, password='New-school-password-2026!'):
    return school.client.post('/api/auth/password-reset/confirm',
                              json={'email': email, 'code': code, 'new_password': password})


def code_from(messages):
    return re.search(r'\b\d{8}\b', messages[-1][2]).group()


def test_recovery_is_disabled_by_default(school):
    assert request_code(school, 'teacher@deped.gov.ph').status_code == 503


def test_verified_mailbox_can_reset_eduscan_password_and_sign_in(school, monkeypatch):
    messages = enable(monkeypatch)
    user = google_login.google_user(school.db, claims())
    email = user.google_email
    assert request_code(school, email.upper()).status_code == 202
    assert messages[0][0] == email
    assert request_code(school, email).status_code == 202
    assert len(messages) == 1
    code = code_from(messages)
    assert reset(school, email, code).status_code == 200
    assert reset(school, email, code).status_code == 400
    credentials = {'username': email, 'password': 'New-school-password-2026!'}
    result = school.client.post('/api/auth/login', json=credentials)
    assert result.status_code == 200
    token = result.json()['access_token']
    assert school.client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    school.db.execute(text('UPDATE deped_password_resets SET requested_at = :past'),
                      {'past': datetime.utcnow() - timedelta(minutes=2)})
    school.db.commit()
    assert request_code(school, email).status_code == 202
    assert reset(school, email, code_from(messages), 'Another-school-password-2026!').status_code == 200
    assert school.client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401
    assert school.client.post('/api/auth/login', json=credentials).status_code == 401


def test_recovery_does_not_disclose_or_enable_unverified_accounts(school, monkeypatch):
    messages = enable(monkeypatch)
    google_login.reserve_google_email(school.db, 'admin', 'reserved@deped.gov.ph')
    user = google_login.google_user(school.db, claims())
    good = request_code(school, user.google_email)
    for email in ('missing@deped.gov.ph', 'reserved@deped.gov.ph'):
        result = request_code(school, email)
        assert (result.status_code, result.json()) == (good.status_code, good.json())
    assert len(messages) == 1


def test_reset_code_expires_and_has_a_guess_limit(school, monkeypatch):
    messages = enable(monkeypatch)
    user = google_login.google_user(school.db, claims())
    assert request_code(school, user.google_email).status_code == 202
    code = code_from(messages)
    wrong = '00000000' if code != '00000000' else '11111111'
    for _ in range(5):
        assert reset(school, user.google_email, wrong).status_code == 400
    assert reset(school, user.google_email, code).status_code == 400
    school.db.execute(text('UPDATE deped_password_resets SET requested_at = :past'),
                      {'past': datetime.utcnow() - timedelta(minutes=11)})
    school.db.commit()
    assert request_code(school, user.google_email).status_code == 202
    school.db.execute(text('UPDATE deped_password_resets SET requested_at = :past'),
                      {'past': datetime.utcnow() - timedelta(minutes=11)})
    school.db.commit()
    assert reset(school, user.google_email, code_from(messages)).status_code == 400
