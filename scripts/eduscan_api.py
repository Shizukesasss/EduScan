"""In-memory cookie authentication for EduScan command-line tools."""

import getpass
import json
from contextlib import contextmanager
from http.cookiejar import CookieJar
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
import warnings


@contextmanager
def school_api(base_url, username):
    address = urlsplit(base_url)
    if address.scheme != "https" and not (
        address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Use HTTPS or a loopback URL for EduScan")

    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(path, payload=None, *, method=None, timeout=30):
        headers = {"X-EduScan-Request": "1"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        return opener.open(Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method),
                           timeout=timeout)

    with request("/api/auth/login", {"username": username, "password": getpass.getpass("Password: ")}):
        pass
    try:
        yield request
    finally:
        try:
            with request("/api/auth/logout", method="POST"):
                pass
        except URLError:
            warnings.warn("EduScan could not revoke this command-line session. It will expire automatically.", stacklevel=2)
