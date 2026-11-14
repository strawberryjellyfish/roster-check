"""Tests for the command-line interface."""

import runpy
import sys
from importlib.metadata import version

import pytest

from roster_check import __version__
from roster_check.cli import main


def test_package_version_matches_installed_metadata() -> None:
    assert __version__ == version("roster-check")


def test_version_flag_prints_version_and_exits_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"roster-check {__version__}"


def test_no_arguments_returns_success() -> None:
    assert main([]) == 0


def test_unknown_argument_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--not-a-real-option"])

    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_module_entry_point_runs_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["roster_check", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("roster_check", run_name="__main__")

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
