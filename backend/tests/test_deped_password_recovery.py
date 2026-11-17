"""Recovery through verified DepEd mailboxes using isolated accounts."""
import re
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from test_google_login import claims, school
from browser_test_client import response_session_headers
from app import auth, main
from app.rate_limits import RequestRateLimiter
from app.services import google_login


@pytest.fixture(autouse=True)
def isolated_request_limits(monkeypatch):
    limiter = main.app.state.request_limiter
    monkeypatch.setattr(limiter, 'buckets', RequestRateLimiter(limiter.policies).buckets)


def enable(monkeypatch, **overrides):
    from app.services import password_recovery

    values = dict(deped_password_recovery=True, smtp_host='smtp.example.test', smtp_from='school@example.test')
    config = replace(main.settings, **(values | overrides))
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


def test_local_admin_can_reset_password_through_configured_mailbox(school, monkeypatch):
    messages = enable(monkeypatch, deped_only=False, deped_password_recovery=False,
                      admin_recovery_username='admin', admin_recovery_email='recovery@example.test')
    assert school.client.get('/api/auth/config').json()['admin_password_recovery']
    path = '/api/auth/password-reset'
    missing = school.client.post(f'{path}/request', json={'username': 'teacher'})
    requested = school.client.post(f'{path}/request', json={'username': ' ADMIN '})
    assert requested.status_code == missing.status_code == 202
    assert requested.json() == missing.json()
    assert [message[0] for message in messages] == ['recovery@example.test']
    payload = {'username': 'admin', 'code': code_from(messages), 'new_password': 'Admin-new-password-2026!'}
    assert school.client.post(f'{path}/confirm', json=payload).status_code == 200
    assert school.client.post(f'{path}/confirm', json=payload).status_code == 400
    assert school.client.get('/api/auth/me', headers=school.admin_headers).status_code == 401
    login = school.client.post('/api/auth/login', json={'username': 'admin', 'password': payload['new_password']})
    assert login.status_code == 200
    assert login.json()['role'] == 'admin'


def test_local_admin_recovery_respects_account_role_and_deped_only_mode(school, monkeypatch):
    messages = enable(monkeypatch, deped_only=True,
                      admin_recovery_username='admin', admin_recovery_email='recovery@example.test')
    path = '/api/auth/password-reset/request'
    assert not school.client.get('/api/auth/config').json()['admin_password_recovery']
    assert school.client.post(path, json={'username': 'admin'}).status_code == 503
    assert not messages

    messages = enable(monkeypatch, deped_only=False,
                      admin_recovery_username='teacher', admin_recovery_email='recovery@example.test')
    assert school.client.post(path, json={'username': 'teacher'}).status_code == 202
    assert not messages


def test_admin_enrolls_own_mailbox_and_recovers_without_per_user_environment(school, monkeypatch):
    messages = enable(monkeypatch, deped_only=False, deped_password_recovery=False,
                      admin_recovery_username='', admin_recovery_email='')
    school.admin.password_hash = auth.hash_password('Current-admin-password-2026!')
    school.db.commit()
    school.admin_headers = response_session_headers(school.client.post('/api/auth/login', json={
        'username': 'admin', 'password': 'Current-admin-password-2026!',
    }))
    reset_request = '/api/auth/password-reset/request'
    path = '/api/auth/recovery-email'
    assert school.client.get('/api/auth/config').json()['admin_password_recovery']
    assert school.client.post(reset_request, json={'username': 'admin'}).status_code == 202
    assert not messages
    payload = {'email': 'recovery@example.test', 'current_password': 'Current-admin-password-2026!'}
    assert school.client.post(f'{path}/request', json=payload, headers=school.teacher_headers).status_code == 403
    assert school.client.post(f'{path}/request', json={**payload, 'current_password': 'wrong'},
                              headers=school.admin_headers).status_code == 422
    assert school.client.post(f'{path}/request', json=payload, headers=school.admin_headers).status_code == 202
    assert messages[-1][0] == payload['email']
    assert school.client.get(path, headers=school.admin_headers).json()['email'] is None
    assert school.client.post(reset_request, json={'username': 'admin'}).status_code == 202
    assert len(messages) == 1
    confirm = {'code': code_from(messages)}
    assert school.client.post(f'{path}/confirm', json=confirm, headers=school.admin_headers).status_code == 200
    assert school.client.post(f'{path}/confirm', json=confirm, headers=school.admin_headers).status_code == 400
    assert school.client.get(path, headers=school.admin_headers).json()['email'] == payload['email']
    assert school.client.post(reset_request, json={'username': 'admin'}).status_code == 202
    assert messages[-1][0] == payload['email'] and len(messages) == 2
    assert school.client.post('/api/auth/password-reset/confirm', json={
        'username': 'admin', 'code': code_from(messages), 'new_password': 'Admin-recovered-password-2026!',
    }).status_code == 200

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
    headers = response_session_headers(result)
    assert school.client.get('/api/auth/me', headers=headers).json()['auth_provider'] == 'deped_password'
    school.db.execute(text('UPDATE deped_password_resets SET requested_at = :past'),
                      {'past': datetime.utcnow() - timedelta(minutes=2)})
    school.db.commit()
    assert request_code(school, email).status_code == 202
    assert reset(school, email, code_from(messages), 'Another-school-password-2026!').status_code == 200
    assert school.client.get('/api/auth/me', headers=headers).status_code == 401
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
