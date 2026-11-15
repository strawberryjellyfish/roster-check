"""Shared test fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the directory holding the small CSV fixture files."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def no_anthropic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the API key and model setting so no test can reach the real API.

    Subprocesses started by tests inherit the cleaned environment too.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ROSTER_CHECK_MODEL", raising=False)
