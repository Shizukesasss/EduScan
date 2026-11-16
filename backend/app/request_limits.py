"""Bound form bodies before Starlette can consume their bytes."""

import re

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MIB = 1024 * 1024
MAX_CAMERA_UPLOAD_BYTES = 8 * MIB
MAX_ROSTER_WORKBOOK_BYTES = 15 * MIB
MAX_SF2_TEMPLATE_BYTES = 20 * MIB
MAX_BACKUP_ARCHIVE_BYTES = 250 * MIB
FORM_OVERHEAD_BYTES = MIB

_FILE_LIMITS = {
    "/api/admin/backups/restore": MAX_BACKUP_ARCHIVE_BYTES,
    "/api/admin/annex-g/enrollments/import": MAX_ROSTER_WORKBOOK_BYTES,
    "/api/admin/annex-g/dobs/import": MAX_ROSTER_WORKBOOK_BYTES,
    "/api/sf2/template": MAX_SF2_TEMPLATE_BYTES,
    "/api/biometrics/register": MAX_CAMERA_UPLOAD_BYTES,
    "/api/biometrics/recognize": MAX_CAMERA_UPLOAD_BYTES,
    "/api/biometrics/recognize-many": MAX_CAMERA_UPLOAD_BYTES,
    "/api/biometrics/recognize-preview": MAX_CAMERA_UPLOAD_BYTES,
    "/api/biometrics/test": MAX_CAMERA_UPLOAD_BYTES,
}
_ENROLLMENT_PATH = re.compile(r"/api/biometrics/(?:enroll|enrollments)/[^/]+")


def _form_body_limit(scope: Scope, media_type: str) -> int:
    if media_type == "application/x-www-form-urlencoded":
        return FORM_OVERHEAD_BYTES
    path = scope["path"]
    root_path = scope.get("root_path", "").rstrip("/")
    if root_path and path.startswith(root_path + "/"):
        path = path[len(root_path):]
    path = path.rstrip("/")
    if _ENROLLMENT_PATH.fullmatch(path):
        return MAX_CAMERA_UPLOAD_BYTES + FORM_OVERHEAD_BYTES
    return _FILE_LIMITS.get(path, 0) + FORM_OVERHEAD_BYTES


class FormBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        media_type = headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type not in {"multipart/form-data", "application/x-www-form-urlencoded"}:
            await self.app(scope, receive, send)
            return

        limit = _form_body_limit(scope, media_type)
        detail = f"Form request exceeds the {limit // MIB} MiB body limit"
        try:
            declared_length = int(headers.get("content-length", "0"))
        except ValueError:
            declared_length = 0
        if declared_length > limit:
            await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Starlette closes partially spooled uploads when its input stream raises.
                    raise HTTPException(413, detail)
            return message

        await self.app(scope, limited_receive, send)
