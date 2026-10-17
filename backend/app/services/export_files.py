"""Keep concurrent report requests separate without changing download names."""
import tempfile
from pathlib import Path


def new_report_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="report-", dir=directory)) / filename
