"""Ingest: read a CSV file and apply the file-level checks.

Handles encoding, byte-order marks, line endings, blank lines and the header.
Fatal problems raise ``InputError``; individual rows are left to ``validate``.
"""

import csv
from collections.abc import Sequence
from pathlib import Path

from roster_check.models import CsvFile, InputError, RawRow

FALLBACK_ENCODING = "cp1252"


def read_csv(path: Path, required_columns: Sequence[str]) -> CsvFile:
    """Read a CSV file and check that it can be used.

    Each line is parsed on its own so that its raw text can be shown to the
    user. Column names are matched ignoring case and surrounding spaces, and
    may appear in any order. Extra columns are recorded and ignored.

    Args:
        path: The file to read.
        required_columns: Column names the file must contain.

    Returns:
        The file's header and its non-blank data lines.

    Raises:
        InputError: If the file is missing, unreadable or empty, or its
            header is missing a required column or repeats a column.
    """
    file_name = path.name
    text, used_fallback_encoding = _read_text(path)
    lines = _split_lines(text)
    if not lines:
        raise InputError(f"{file_name} has no rows")

    header = tuple(name.strip().lower() for name in _parse_line(lines[0]))
    _check_header(file_name, header, required_columns)

    rows = []
    blank_lines = 0
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            blank_lines += 1
            continue
        rows.append(RawRow(line_number, line, _parse_line(line)))
    if not rows:
        raise InputError(f"{file_name} has no rows")

    return CsvFile(
        file_name=file_name,
        header=header,
        rows=tuple(rows),
        blank_lines=blank_lines,
        ignored_columns=tuple(name for name in header if name not in required_columns),
        used_fallback_encoding=used_fallback_encoding,
    )


def _read_text(path: Path) -> tuple[str, bool]:
    """Read and decode a file, falling back to Windows-1252 if it is not UTF-8.

    Returns:
        The decoded text and whether the fallback encoding was used.
    """
    file_name = path.name
    if not path.is_file():
        raise InputError(f"{file_name} not found")
    try:
        data = path.read_bytes()
    except OSError:
        raise InputError(f"Could not read {file_name}") from None

    try:
        return data.decode("utf-8-sig"), False
    except UnicodeDecodeError:
        pass
    try:
        return data.decode(FALLBACK_ENCODING), True
    except UnicodeDecodeError:
        raise InputError(f"Could not read {file_name}") from None


def _split_lines(text: str) -> list[str]:
    """Split text into lines on any line ending, ignoring a final line ending.

    Returns an empty list for text with no content at all.
    """
    if not text.strip():
        return []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _parse_line(line: str) -> tuple[str, ...]:
    """Split one CSV line into fields, honouring quotes."""
    return tuple(next(csv.reader([line])))


def _check_header(
    file_name: str,
    header: tuple[str, ...],
    required_columns: Sequence[str],
) -> None:
    """Raise ``InputError`` if the header repeats a column or lacks one."""
    seen: set[str] = set()
    for name in header:
        if name in seen:
            raise InputError(f"{file_name} has duplicate column '{name}'")
        seen.add(name)
    for name in required_columns:
        if name not in seen:
            raise InputError(f"{file_name} is missing column '{name}'")
