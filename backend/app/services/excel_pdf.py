"""Export the actual Excel print layout, then apply PDF editing restrictions."""
import io
import os
import secrets
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions


_excel_lock = Lock()


def excel_report_pdf(source: Path, *, terms: tuple[int, ...] = (), draft: bool = False) -> bytes:
    if os.name != 'nt':
        raise HTTPException(503, 'Template PDF export requires Microsoft Excel on the Windows EduScan host.')

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
        try:
            with _excel_lock:
                subprocess.run(command, check=True, capture_output=True, timeout=90,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as error:
            raise HTTPException(503, 'Excel took too long to export the report. Try generating it again.') from error
        except (OSError, subprocess.CalledProcessError) as error:
            raise HTTPException(503, 'Excel could not export the report template. Check that Microsoft Excel can open and print the template on the EduScan host.') from error

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
