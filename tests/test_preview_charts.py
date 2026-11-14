"""Smoke test for the chart preview script."""

import subprocess
import sys
from pathlib import Path

PREVIEW_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "preview_charts.py"
)


def test_preview_page_holds_every_chart(tmp_path: Path) -> None:
    out_file = tmp_path / "preview.html"

    subprocess.run(
        [sys.executable, str(PREVIEW_SCRIPT), "--out", str(out_file)],
        check=True,
        capture_output=True,
    )

    page = out_file.read_text(encoding="utf-8")
    for chart in ["centre-bars", "heatmap", "daily", "shortfall-bar"]:
        assert f'class="chart {chart}"' in page
    assert page.count('class="chart shortfall-bar"') == 10
    assert "http" not in page
