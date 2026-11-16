"""Security controls exercised with a temporary database and ordinary workbooks."""

import asyncio
import hashlib
import json
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_attendance_sync as fixtures
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from PIL import Image
from starlette import formparsers
from starlette.formparsers import MultiPartParser
from starlette.requests import Request

from app import main, request_limits
from app.rate_limits import RequestRateLimiter
from app.services import annex_g, backup, biometrics, reports, sf2


class RequestRateLimiterTest(unittest.TestCase):
    def test_budget_refills_for_each_address_without_extending_rejections(self):
        now = 100.0
        limiter = RequestRateLimiter({"camera": (30, 2)}, clock=lambda: now)

        self.assertIsNone(limiter.retry_after("camera", "192.0.2.1"))
        self.assertIsNone(limiter.retry_after("camera", "192.0.2.1"))
        self.assertEqual(limiter.retry_after("camera", "192.0.2.1"), 2)
        self.assertIsNone(limiter.retry_after("camera", "192.0.2.2"))
        now += 1
        self.assertEqual(limiter.retry_after("camera", "192.0.2.1"), 1)
        now += 1
        self.assertIsNone(limiter.retry_after("camera", "192.0.2.1"))

    def test_full_address_table_reclaims_an_idle_entry(self):
        now = 100.0
        limiter = RequestRateLimiter({"backup": (6, 1)}, clock=lambda: now, max_clients=1)

        self.assertIsNone(limiter.retry_after("backup", "192.0.2.1"))
        self.assertEqual(limiter.retry_after("backup", "192.0.2.2"), 60)
        now += 60
        self.assertIsNone(limiter.retry_after("backup", "192.0.2.2"))


class SecurityControlsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AttendanceSyncTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_api_responses_prevent_caching_and_mime_sniffing(self):
        response = self.fixture.client.get("/api/auth/me", headers=self.fixture.admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_camera_aliases_share_a_budget_before_multipart_parsing(self):
        headers = self.fixture.admin_headers
        payload = {"frame": ("fixture.png", self.camera_frame(20, 20), "image/png")}
        origin = next(iter(main.settings.allowed_origins), None)
        with self.request_budget({"camera": (60, 1)}):
            first = self.fixture.client.post("/api/biometrics/recognize", headers=headers)
            self.assertEqual(first.status_code, 422, first.text)
            second = self.fixture.client.post(
                "/api/biometrics/test",
                headers={**headers, "X-Forwarded-For": "192.0.2.2", **({"Origin": origin} if origin else {})},
                files=payload,
            )
            self.assertEqual(second.status_code, 429, second.text)
            self.assertEqual(second.headers["retry-after"], "1")
            self.assertIn("no-store", second.headers["cache-control"])
            if origin:
                self.assertEqual(second.headers["access-control-allow-origin"], origin)
                self.assertIn("retry-after", second.headers["access-control-expose-headers"].lower())
            with patch.object(MultiPartParser, "parse", side_effect=AssertionError("multipart parser called")) as parse:
                third = self.fixture.client.put(
                    f"/api/biometrics/enrollments/{self.fixture.student.id}", headers=headers, files=payload,
                )
            self.assertEqual(third.status_code, 429, third.text)
            parse.assert_not_called()

    def test_report_and_backup_budgets_are_independent_and_cover_alternate_routes(self):
        headers = self.fixture.admin_headers
        with self.request_budget({"report": (60, 1), "backup": (60, 1)}):
            self.assertEqual(self.fixture.client.get("/api/attendance/report.xlsx", headers=headers).status_code, 422)
            response = self.fixture.client.get("/api/dtr/1/export?format=xlsx", headers=headers)
            self.assertEqual(response.status_code, 429, response.text)
            self.assertEqual(self.fixture.client.post("/api/admin/backups", headers=headers).status_code, 422)
            with patch.object(MultiPartParser, "parse", side_effect=AssertionError("multipart parser called")) as parse:
                response = self.fixture.client.post(
                    "/api/admin/backups/restore", headers=headers, files={"file": ("fixture.edubak", b"fixture")},
                )
            self.assertEqual(response.status_code, 429, response.text)
            parse.assert_not_called()
            download = self.fixture.client.get("/api/admin/backups/fixture.edubak", headers=headers)
            self.assertEqual(download.status_code, 429, download.text)
            self.assertEqual(self.fixture.client.get("/api/admin/backups", headers=headers).status_code, 200)

    @staticmethod
    def request_budget(policies):
        return patch.object(main.app.state, "request_limiter",
                            RequestRateLimiter(policies, clock=lambda: 100.0))

    def test_sign_in_and_recovery_limits_stop_work_before_the_handlers(self):
        paths = {
            "password sign-in": "/api/auth/login",
            "Google sign-in": "/api/auth/google",
            "password recovery request": "/api/auth/password-reset/request",
            "password recovery confirmation": "/api/auth/password-reset/confirm",
        }
        with self.request_budget({category: (60, 1) for category in paths}):
            for category, path in paths.items():
                with self.subTest(category=category):
                    first = self.fixture.client.post(path, json={})
                    self.assertEqual(first.status_code, 422, first.text)
                    with patch.object(Request, "json", side_effect=AssertionError("JSON parsed")) as parse:
                        second = self.fixture.client.post(path, json={})
                    self.assertEqual(second.status_code, 429, second.text)
                    self.assertEqual(second.headers["retry-after"], "1")
                    parse.assert_not_called()

    def test_sms_limit_covers_test_dispatch_and_gateway_checks(self):
        headers = self.fixture.admin_headers
        with (self.request_budget({"SMS": (60, 1), "SMS cancellation": (60, 1)}),
              patch.object(main, "dispatch_queued", return_value=[]) as dispatch,
              patch.object(main, "gateway_diagnostics") as diagnostics):
            first = self.fixture.client.post("/api/sms/dispatch", headers=headers)
            self.assertEqual(first.status_code, 200, first.text)
            with patch.object(MultiPartParser, "parse", side_effect=AssertionError("multipart parser called")) as parse:
                second = self.fixture.client.post(
                    "/api/sms/test", headers=headers, files={"phone": (None, "09171234567")},
                )
            self.assertEqual(second.status_code, 429, second.text)
            parse.assert_not_called()
            third = self.fixture.client.get("/api/sms/gateway/check", headers=headers)
            self.assertEqual(third.status_code, 429, third.text)
            cancellation = self.fixture.client.post("/api/sms/outbox/unknown/cancel", headers=headers)
            self.assertEqual(cancellation.status_code, 404, cancellation.text)
            diagnostics.assert_not_called()
            dispatch.assert_called_once()

    def test_camera_body_over_limit_is_rejected_before_opening_the_parser(self):
        origin = next(iter(main.settings.allowed_origins), None)
        with patch.object(MultiPartParser, "parse", side_effect=AssertionError("multipart parser called")) as parse:
            response = self.fixture.client.post(
                "/api/biometrics/recognize",
                headers={**self.fixture.admin_headers, **({"Origin": origin} if origin else {})},
                files={"frame": ("fixture.jpg", bytes(9 * 1024 * 1024), "image/jpeg")},
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
        self.assertIn("no-store", response.headers["cache-control"])
        parse.assert_not_called()

    def test_streamed_workbook_stops_at_limit_and_closes_the_partial_upload(self):
        path = "/api/sf2/template"
        opened = []
        spooled_file = formparsers.SpooledTemporaryFile

        def record_spool(*args, **kwargs):
            file = spooled_file(*args, **kwargs)
            opened.append(file)
            return file

        async def upload():
            async with AsyncClient(transport=ASGITransport(app=main.app), base_url="https://testserver") as client:
                request = client.build_request("POST", path, files={"file": ("sf2.xlsx", self.workbook(sf2.SHEET_NAME))})
                body = await request.aread()

                async def chunks():
                    yield body[:512]
                    yield body[512:]

                return await client.post(
                    path, content=chunks(),
                    headers={**self.fixture.admin_headers, "Content-Type": request.headers["content-type"]},
                )

        with (patch.object(request_limits, "_form_body_limit", return_value=1024),
              patch.object(formparsers, "SpooledTemporaryFile", side_effect=record_spool),
              patch.object(main, "save_template") as save_template):
            response = asyncio.run(upload())
        self.assertNotIn("content-length", response.request.headers)
        self.assertEqual(response.status_code, 413, response.text)
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))
        save_template.assert_not_called()

    def test_camera_dimensions_are_checked_in_enrollment_and_recognition(self):
        image = self.camera_frame(3841, 12)
        for path, name, fields in (
            ("/api/biometrics/recognize", "frame", {}),
            (f"/api/biometrics/enroll/{self.fixture.student.id}", "frames", {"reason": "Synthetic test"}),
        ):
            with self.subTest(path=path):
                response = self.fixture.client.post(
                    path, headers=self.fixture.admin_headers, data=fields,
                    files={name: ("fixture.png", image, "image/png")},
                )
                self.assertEqual(response.status_code, 413, response.text)

    def test_camera_decoded_byte_budget_is_checked_before_loading_pixels(self):
        image = self.camera_frame(40, 40)
        with (patch.object(biometrics, "MAX_CAMERA_DECODED_BYTES", 4096),
              patch.object(Image.Image, "load", side_effect=AssertionError("pixels decoded"))):
            response = self.fixture.client.post(
                "/api/biometrics/recognize", headers=self.fixture.admin_headers,
                files={"frame": ("fixture.png", image, "image/png")},
            )
        self.assertEqual(response.status_code, 413, response.text)

    def test_tall_png_is_rejected_without_loading_pixels(self):
        image = self.camera_frame(20, 2161)
        with patch.object(Image.Image, "load", side_effect=AssertionError("pixels decoded")):
            response = self.fixture.client.post(
                "/api/biometrics/recognize", headers=self.fixture.admin_headers,
                files={"frame": ("fixture.png", image, "image/png")},
            )
        self.assertEqual(response.status_code, 413, response.text)

    def test_valid_camera_frames_keep_bgr_color_and_orientation(self):
        service = main.biometric_service
        image = service._decode(self.camera_frame(64, 48))
        self.assertEqual(image.shape, (48, 64, 3))
        self.assertEqual(image[0, 0].tolist(), [30, 20, 10])
        source = BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        with Image.new("RGB", (48, 64)) as portrait:
            portrait.save(source, "JPEG", exif=exif)
        self.assertEqual(service._decode(source.getvalue()).shape, (48, 64, 3))

    @staticmethod
    def camera_frame(width, height):
        destination = BytesIO()
        with Image.new("RGB", (width, height), (10, 20, 30)) as frame:
            frame.save(destination, "PNG")
        return destination.getvalue()

    def test_accepts_a_valid_sf2_workbook(self):
        template = self.workbook(sf2.SHEET_NAME)
        target = Path(fixtures.TEST_DIR.name) / "valid-sf2.xlsx"
        self.addCleanup(target.unlink, missing_ok=True)
        with patch.object(sf2, "DEFAULT_TEMPLATE", target):
            response = self.fixture.client.post(
                "/api/sf2/template", headers=self.fixture.admin_headers,
                files={"file": ("sf2.xlsx", template)},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(target.read_bytes(), template)

    def test_report_quota_preserves_existing_reports_and_discards_new_export(self):
        with tempfile.TemporaryDirectory(dir=fixtures.TEST_DIR.name) as directory:
            exports = Path(directory)
            registered = exports / "registered"
            registered.mkdir()
            (registered / "existing.xlsx").write_bytes(bytes(1024 * 1024))
            with (patch.object(reports, "EXPORT_DIR", exports),
                  patch.object(reports, "REPORT_DIR", registered),
                  patch.object(sf2, "EXPORT_DIR", exports),
                  patch.object(reports, "settings", SimpleNamespace(report_storage_mib=1))):
                response = self.fixture.client.get(
                    "/api/attendance/temporary-log?date=2026-10-13&format=xlsx",
                    headers=self.fixture.admin_headers,
                )
            self.assertEqual(response.status_code, 507, response.text)
            self.assertEqual([file.name for file in exports.rglob("*.xlsx")], ["existing.xlsx"])

    def test_backup_quota_preserves_existing_archive_at_either_destination(self):
        with tempfile.TemporaryDirectory(dir=fixtures.TEST_DIR.name) as directory:
            root = Path(directory) / "data"
            destination = root / "backups"
            destination.mkdir(parents=True)
            offsite = Path(directory) / "offsite"
            offsite.mkdir()
            (root / ".encryption_key").write_bytes(b"synthetic fixture key")
            with (patch.object(backup, "DATA_DIR", root),
                  patch.object(backup, "BACKUP_DIR", destination),
                  patch.object(backup, "BIOMETRIC_DIR", root / "biometrics"),
                  patch.object(backup, "MODEL_DIR", root / "models"),
                  patch.object(backup, "TEMPLATE_DIR", root / "templates"),
                  patch.object(backup, "_database_snapshot", return_value=("eduscan.db", b"synthetic snapshot", "sqlite")),
                  patch.object(backup, "settings", SimpleNamespace(backup_storage_mib=1))):
                for folder in (destination, offsite):
                    with self.subTest(full=folder.name):
                        existing = folder / "existing.edubak"
                        existing.write_bytes(bytes(1024 * 1024))
                        response = self.fixture.client.post(
                            "/api/admin/backups", headers=self.fixture.admin_headers,
                            data={"passphrase": "Synthetic backup passphrase", "destination": str(offsite)},
                        )
                        self.assertEqual(response.status_code, 507, response.text)
                        self.assertEqual(list(destination.glob("*.edubak")) + list(offsite.glob("*.edubak")), [existing])
                        existing.unlink()
                response = self.fixture.client.post(
                    "/api/admin/backups", headers=self.fixture.admin_headers,
                    data={"passphrase": "Synthetic backup passphrase", "destination": str(offsite)},
                )
                self.assertEqual(response.status_code, 200, response.text)
                filename = response.json()["filename"]
                self.assertEqual((destination / filename).read_bytes(), (offsite / filename).read_bytes())

    def test_workbook_expansion_limit_runs_before_the_excel_reader(self):
        for path, service, fields in (
            ("/api/sf2/template", sf2, {}),
            ("/api/admin/annex-g/enrollments/import", annex_g, {"approved_reference": "Synthetic approval"}),
            ("/api/admin/annex-g/dobs/import", annex_g, {"approved_reference": "Synthetic approval"}),
        ):
            with (self.subTest(path=path),
                  patch.object(service, "MAX_WORKBOOK_EXPANDED_BYTES", 512),
                  patch.object(service, "load_workbook", side_effect=AssertionError("Excel reader called")) as reader):
                response = self.fixture.client.post(
                    path, headers=self.fixture.admin_headers, data=fields,
                    files={"file": ("fixture.xlsx", self.workbook(sf2.SHEET_NAME))},
                )
                self.assertEqual(response.status_code, 413, response.text)
                reader.assert_not_called()

    def test_backup_over_expansion_limit_leaves_no_staged_restore(self):
        passphrase, data, expanded_size = self.encrypted_backup()
        with tempfile.TemporaryDirectory(dir=fixtures.TEST_DIR.name) as directory:
            pending = Path(directory) / "pending_restore"
            with (patch.object(backup, "PENDING_DIR", pending),
                  patch.object(backup, "database_backend", return_value="sqlite"),
                  patch.object(backup, "MAX_BACKUP_EXPANDED_BYTES", expanded_size - 1)):
                response = self.fixture.client.post(
                    "/api/admin/backups/restore", headers=self.fixture.admin_headers,
                    data={"passphrase": passphrase, "confirmation": "STAGE RESTORE"},
                    files={"file": ("fixture.edubak", data)},
                )
            self.assertEqual(response.status_code, 413, response.text)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_backup_with_a_checksum_mismatch_cleans_up_temporary_files(self):
        passphrase, data, _ = self.encrypted_backup(key_digest="0" * 64)
        with tempfile.TemporaryDirectory(dir=fixtures.TEST_DIR.name) as directory:
            with (patch.object(backup, "PENDING_DIR", Path(directory) / "pending_restore"),
                  patch.object(backup, "database_backend", return_value="sqlite")):
                response = self.fixture.client.post(
                    "/api/admin/backups/restore", headers=self.fixture.admin_headers,
                    data={"passphrase": passphrase, "confirmation": "STAGE RESTORE"},
                    files={"file": ("fixture.edubak", data)},
                )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("integrity check failed", response.json()["detail"])
            self.assertEqual(list(Path(directory).iterdir()), [])

    @staticmethod
    def encrypted_backup(key_digest=None):
        files = {"eduscan.db": b"synthetic database package", ".encryption_key": b"synthetic fixture key"}
        digests = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        if key_digest is not None:
            digests[".encryption_key"] = key_digest
        manifest = json.dumps({
            "format": 2, "database_backend": "sqlite",
            "files": digests,
        }).encode()
        source = BytesIO()
        with ZipFile(source, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", manifest)
            for name, content in files.items():
                archive.writestr(name, content)
        salt = bytes(16)
        passphrase = "Synthetic restore passphrase"
        data = backup.MAGIC + salt + backup._fernet(passphrase, salt).encrypt(source.getvalue())
        return passphrase, data, len(manifest) + sum(map(len, files.values()))

    def test_new_password_account_requires_explicit_temporary_password(self):
        response = self.fixture.client.post(
            "/api/admin/users",
            headers=self.fixture.admin_headers,
            json={"username": "new.teacher", "role": "teacher", "full_name": "New Teacher"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "password"])

    def test_camera_runtime_configuration_requires_an_administrator(self):
        path = "/api/biometrics/status"
        self.assertEqual(self.fixture.client.get(path, headers=self.fixture.teacher_headers).status_code, 403)
        self.assertEqual(self.fixture.client.get(path, headers=self.fixture.admin_headers).status_code, 200)

    def test_startup_can_keep_demo_accounts_disabled(self):
        settings = SimpleNamespace(seed_demo_accounts=False, attendance_scheduler_enabled=False)
        with (patch.object(main, "settings", settings),
              patch.object(main, "SessionLocal", return_value=self.fixture.db),
              patch.object(main, "initialize_database"),
              patch.object(main, "seed_reference_data"),
              patch.object(main, "configure_fast_gate"),
              patch.object(main, "seed_users") as seed_users):
            main.startup()
        seed_users.assert_not_called()

    def test_unrelated_workbook_preserves_the_installed_template(self):
        target = Path(fixtures.TEST_DIR.name) / "installed-sf2.xlsx"
        installed = self.workbook(sf2.SHEET_NAME)
        target.write_bytes(installed)
        self.addCleanup(target.unlink, missing_ok=True)
        with patch.object(sf2, "DEFAULT_TEMPLATE", target):
            response = self.fixture.client.post(
                "/api/sf2/template",
                headers=self.fixture.admin_headers,
                files={"file": ("unrelated.xlsx", self.workbook("Inventory"))},
            )
        self.assertEqual(response.status_code, 422)
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), installed)

    def test_sf2_worksheet_must_match_the_export_template_layout(self):
        target = Path(fixtures.TEST_DIR.name) / "layout-sf2.xlsx"
        backup = self.workbook(sf2.SHEET_NAME)
        target.write_bytes(backup)
        self.addCleanup(target.unlink, missing_ok=True)
        cover_workbook = self.workbook("Cover", sf2.SHEET_NAME)
        with patch.object(sf2, "DEFAULT_TEMPLATE", target):
            response = self.fixture.client.post(
                "/api/sf2/template",
                headers=self.fixture.admin_headers,
                files={"file": ("cover.xlsx", cover_workbook)},
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(target.read_bytes(), backup)

    @staticmethod
    def workbook(sheet_name, *additional_sheets):
        workbook = Workbook()
        workbook.active.title = sheet_name
        for title in additional_sheets:
            workbook.create_sheet(title)
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        return buffer.getvalue()
