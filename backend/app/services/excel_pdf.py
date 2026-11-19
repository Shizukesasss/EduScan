"""Export the actual Excel print layout, then apply PDF editing restrictions."""
import io
import logging
import os
import secrets
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions

from .report_pdf import workbook_report_pdf


_excel_lock = Lock()
logger = logging.getLogger(__name__)


def excel_report_pdf(source: Path, *, terms: tuple[int, ...] = (), draft: bool = False,
                     landscape: bool = False) -> bytes:
    if os.name == 'nt':
        try:
            return _native_excel_pdf(source, terms=terms, draft=draft, landscape=landscape)
        except (OSError, subprocess.SubprocessError) as error:
            logger.warning('Using the built-in PDF renderer because Excel export failed (%s).', type(error).__name__)
    return workbook_report_pdf(source, terms=terms, draft=draft, landscape_pages=landscape)


def _native_excel_pdf(source: Path, *, terms: tuple[int, ...], draft: bool, landscape: bool) -> bytes:
    with TemporaryDirectory(dir=source.parent) as directory:
        command = [
            'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(Path(__file__).with_name('export-workbook-pdf.ps1')),
            '-Source', str(source.resolve()), '-OutputDirectory', str(Path(directory).resolve()),
        ]
        if terms:
            command.extend(('-Terms', ','.join(map(str, terms))))
        if draft:
            command.append('-Draft')
        if landscape:
            command.append('-Landscape')
        with _excel_lock:
            subprocess.run(command, check=True, capture_output=True, timeout=90,
                           creationflags=subprocess.CREATE_NO_WINDOW)

        parts = sorted(Path(directory).glob('sheet-*.pdf'))
        if not parts:
            raise HTTPException(409, 'The report template has no printable sheets for the selected terms.')
        with PdfWriter() as writer:
            for part in parts:
                writer.append(part, import_outline=False)
            # Enable standard and high-resolution printing, with editing disabled.
            permissions = UserAccessPermissions(0xFFFFF8C4)
            writer.encrypt('', owner_password=secrets.token_hex(24), algorithm='AES-256',
                           permissions_flag=permissions)
            buffer = io.BytesIO()
            writer.write(buffer)
        return buffer.getvalue()
