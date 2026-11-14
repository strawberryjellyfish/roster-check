"""Shared test fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the directory holding the small CSV fixture files."""
    return Path(__file__).resolve().parent / "fixtures"
