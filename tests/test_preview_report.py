"""Smoke test for the report preview script."""

import subprocess
import sys
from pathlib import Path

PREVIEW_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "preview_report.py"
)


def test_preview_script_writes_the_sample_report(tmp_path: Path) -> None:
    out_file = tmp_path / "preview.html"

    subprocess.run(
        [sys.executable, str(PREVIEW_SCRIPT), "--out", str(out_file)],
        check=True,
        capture_output=True,
    )

    page = out_file.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    for chart in ["centre-bars", "heatmap", "daily", "shortfall-bar"]:
        assert f'class="chart {chart}"' in page
    assert "All data in this report is fictional." in page
