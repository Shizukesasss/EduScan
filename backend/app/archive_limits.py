"""Bound how much ZIP data callers can decompress."""

from collections.abc import Iterator
from contextlib import contextmanager
from tempfile import SpooledTemporaryFile
from typing import BinaryIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from fastapi import HTTPException

from .request_limits import MIB

MAX_WORKBOOK_EXPANDED_BYTES = 128 * MIB
_CHUNK_BYTES = 64 * 1024


def check_archive_size(archive: ZipFile, limit: int, label: str) -> list[ZipInfo]:
    members = archive.infolist()
    if sum(member.file_size for member in members) > limit:
        raise HTTPException(413, f"{label} exceeds the {limit // MIB} MiB decompressed size limit")
    if len({member.filename for member in members}) != len(members):
        raise BadZipFile("Archive contains duplicate entries")
    if any(member.compress_type not in (ZIP_STORED, ZIP_DEFLATED) for member in members):
        raise BadZipFile("Archive uses an unsupported compression method")
    return members


def expanded_chunks(archive: ZipFile, member: ZipInfo) -> Iterator[bytes]:
    # Read in bounded chunks. ZIP readers can expand data before checking its declared size.
    remaining = member.file_size
    with archive.open(member) as entry:
        while chunk := entry.read(min(_CHUNK_BYTES, remaining + 1)):
            remaining -= len(chunk)
            if remaining < 0:
                raise BadZipFile("Archive entry exceeds its declared size")
            yield chunk
    if remaining:
        raise BadZipFile("Archive entry ended before its declared size")


@contextmanager
def checked_workbook(source: BinaryIO, limit: int) -> Iterator[BinaryIO]:
    # Give OpenPyXL a ZIP with known member sizes so its whole-entry reads stay within the budget.
    with ZipFile(source) as uploaded, SpooledTemporaryFile(max_size=8 * MIB) as checked:
        members = check_archive_size(uploaded, limit, "Workbook")
        with ZipFile(checked, "w") as normalized:
            for member in members:
                with normalized.open(member.filename, "w") as destination:
                    for chunk in expanded_chunks(uploaded, member):
                        destination.write(chunk)
        checked.seek(0)
        yield checked
