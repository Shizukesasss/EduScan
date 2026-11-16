"""Keep concurrent report requests separate without changing download names."""
import secrets
import tempfile
from pathlib import Path

from reportlab.lib.pdfencrypt import StandardEncryption

from ..storage_quota import REPORT_WORK_DIR


def new_report_path(directory: Path, filename: str) -> Path:
    work_directory = directory / REPORT_WORK_DIR
    work_directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="report-", dir=work_directory)) / filename


def report_encryption() -> StandardEncryption:
    return StandardEncryption('', ownerPassword=secrets.token_hex(24), canPrint=1,
                              canModify=0, canCopy=0, canAnnotate=0, strength=128)
