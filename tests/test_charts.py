"""Tests for the SVG charts."""

import locale
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date

import pytest

from roster_check.charts import (
    BAR_AREA_WIDTH,
    NO_DATA_TEXT,
    SHORTFALL_BAR_WIDTH,
    centre_bar_chart,
    daily_chart,
    format_day,
    heatmap,
    shade_level,
    shortfall_bar,
)
from roster_check.models import CentreSummary, DailyTotal, HeatmapCell

CENTRES = [
    CentreSummary("HLS", "Hillside", 70, 7),
    CentreSummary("NTH", "Northgate", 70, 14),
    CentreSummary("RBC", "Riverbend Central", 40, 0),
]


def parse(svg: str) -> ET.Element:
    """Parse an SVG string, failing the test if it is not well-formed XML."""
    # Safe: the input is SVG produced by our own chart functions.
    return ET.fromstring(svg)  # noqa: S314


def with_class(root: ET.Element, tag: str, css_class: str) -> list[ET.Element]:
    """Return every ``tag`` element whose class list includes ``css_class``."""
    return [
        element
        for element in root.iter(tag)
        if css_class in element.get("class", "").split()
    ]


def texts(root: ET.Element) -> list[str]:
    """Return the content of every text element."""
    return [element.text or "" for element in root.iter("text")]


def chart_title(root: ET.Element) -> str:
    """Return the chart's text alternative."""
    return root.find("title").text


def all_charts() -> list[str]:
    """Return one example of every chart, for checks that apply to them all."""
    cells = [HeatmapCell(0, 16, 2, 1, 3)]
    daily = [DailyTotal(date(2026, 11, 2), 500, 150.5)]
    return [
        centre_bar_chart(CENTRES),
        heatmap(cells),
        daily_chart(daily),
        shortfall_bar(2, 3),
    ]


def test_day_label_uses_short_day_and_month_names() -> None:
    assert format_day(date(2026, 11, 3)) == "Tue 3 Nov"
    assert format_day(date(2027, 1, 10)) == "Sun 10 Jan"


def test_day_label_does_not_depend_on_the_locale() -> None:
    original = locale.setlocale(locale.LC_TIME)
    try:
        for name in ["de_DE.UTF-8", "German_Germany.1252", "fr_FR.UTF-8"]:
            try:
                locale.setlocale(locale.LC_TIME, name)
                break
            except locale.Error:
                continue
        assert format_day(date(2026, 11, 3)) == "Tue 3 Nov"
    finally:
        locale.setlocale(locale.LC_TIME, original)


def test_every_chart_is_an_svg_image_with_a_text_alternative() -> None:
    for svg in all_charts():
        root = parse(svg)
        assert root.tag == "svg"
        assert root.get("role") == "img"
        assert chart_title(root)
        assert root.get("viewBox")


def test_charts_make_no_external_references() -> None:
    for svg in all_charts():
        assert "http" not in svg
        assert "href" not in svg


def test_charts_set_no_colours_of_their_own() -> None:
    for svg in all_charts():
        assert "fill=" not in svg
        assert "stroke=" not in svg
        assert "#" not in svg


def test_centre_chart_draws_one_bar_per_centre() -> None:
    root = parse(centre_bar_chart(CENTRES))

    assert len(with_class(root, "rect", "bar")) == 3
    assert {"Hillside", "Northgate", "Riverbend Central"} <= set(texts(root))


def test_centre_bars_are_proportional_to_the_understaffed_percentage() -> None:
    root = parse(centre_bar_chart(CENTRES))

    widths = [float(bar.get("width")) for bar in with_class(root, "rect", "bar")]
    assert widths == [BAR_AREA_WIDTH / 2, BAR_AREA_WIDTH, 0]


def test_centre_bars_show_the_count_and_the_percentage() -> None:
    root = parse(centre_bar_chart(CENTRES))

    assert "14 of 70 (20%)" in texts(root)
    assert "0 of 40 (0%)" in texts(root)


def test_centre_bars_enter_one_after_another() -> None:
    root = parse(centre_bar_chart(CENTRES))

    delays = [bar.get("style") for bar in with_class(root, "rect", "bar")]
    assert delays == ["--delay: 0.00s", "--delay: 0.08s", "--delay: 0.16s"]


def test_centre_chart_with_no_understaffing_draws_empty_bars() -> None:
    root = parse(centre_bar_chart([CentreSummary("NTH", "Northgate", 0, 0)]))

    assert [bar.get("width") for bar in with_class(root, "rect", "bar")] == ["0"]


def test_centre_names_are_escaped() -> None:
    name = '<script>alert("x")</script> & Co'
    svg = centre_bar_chart([CentreSummary("NTH", name, 10, 1)])

    assert "<script>" not in svg
    assert name in texts(parse(svg))


@pytest.mark.parametrize(
    ("shortfall", "level"),
    [(0, 0), (1, 1), (2, 2), (3, 2), (4, 3), (6, 3), (7, 4), (25, 4)],
)
def test_shade_levels_are_fixed_by_shortfall(shortfall: int, level: int) -> None:
    assert shade_level(shortfall) == level


def test_heatmap_has_a_cell_for_every_day_and_hour_in_range() -> None:
    cells = [HeatmapCell(0, 6, 1, 0, 0), HeatmapCell(5, 9, 2, 1, 1)]

    root = parse(heatmap(cells))

    drawn = with_class(root, "rect", "cell") + with_class(root, "g", "cell")
    # Seven days by the four hours from 06 to 09.
    assert len(drawn) == 7 * 4
    assert texts(root)[:4] == ["06", "07", "08", "09"]


def test_heatmap_marks_hours_without_sessions_as_empty() -> None:
    cells = [HeatmapCell(0, 6, 1, 0, 0), HeatmapCell(0, 8, 1, 0, 0)]

    root = parse(heatmap(cells))

    assert len(with_class(root, "g", "cell")) == 2
    assert len(with_class(root, "rect", "empty")) == 7 * 3 - 2


def test_heatmap_cell_shade_and_number_show_the_shortfall() -> None:
    cells = [HeatmapCell(1, 16, 6, 4, 7), HeatmapCell(1, 17, 3, 0, 0)]

    root = parse(heatmap(cells))

    groups = with_class(root, "g", "cell")
    assert [group.get("class") for group in groups] == [
        "cell shade-4",
        "cell shade-0",
    ]
    assert [t.text for t in groups[0].iter("text")] == ["7"]
    assert list(groups[1].iter("text")) == []


def test_heatmap_cell_tooltip_gives_the_exact_numbers() -> None:
    cells = [HeatmapCell(1, 16, 6, 4, 7), HeatmapCell(2, 16, 1, 1, 1)]

    root = parse(heatmap(cells))

    tooltips = [group.find("title").text for group in with_class(root, "g", "cell")]
    assert tooltips == [
        "Tue 16:00: 6 sessions, 4 understaffed, shortfall 7",
        "Wed 16:00: 1 session, 1 understaffed, shortfall 1",
    ]


def test_heatmap_places_cells_by_day_and_hour() -> None:
    root = parse(heatmap([HeatmapCell(0, 5, 1, 0, 0), HeatmapCell(6, 7, 1, 0, 0)]))

    monday, sunday = (group.find("rect") for group in with_class(root, "g", "cell"))
    assert float(monday.get("x")) < float(sunday.get("x"))
    assert float(monday.get("y")) < float(sunday.get("y"))


def test_daily_chart_has_two_lines_with_a_point_per_day() -> None:
    daily = [
        DailyTotal(date(2026, 11, 2), 500, 150.0),
        DailyTotal(date(2026, 11, 3), 250, 75.5),
        DailyTotal(date(2026, 11, 4), 0, 0.0),
    ]

    root = parse(daily_chart(daily))

    lines = with_class(root, "path", "line")
    assert len(lines) == 2
    assert all(line.get("pathLength") == "1" for line in lines)
    assert len(with_class(root, "circle", "point")) == 6
    assert {"Attendance", "Staff hours"} <= set(texts(root))


def test_daily_chart_heights_are_proportional_within_each_panel() -> None:
    daily = [
        DailyTotal(date(2026, 11, 2), 500, 100.0),
        DailyTotal(date(2026, 11, 3), 250, 50.0),
        DailyTotal(date(2026, 11, 4), 0, 0.0),
    ]

    root = parse(daily_chart(daily))

    ys = [float(p.get("cy")) for p in with_class(root, "circle", "point")]
    attendance, hours = ys[:3], ys[3:]
    for panel in (attendance, hours):
        assert panel[2] - panel[1] == pytest.approx(panel[1] - panel[0])
    assert hours[2] > attendance[2]


def test_daily_chart_axes_start_at_zero_and_end_on_a_round_number() -> None:
    daily = [DailyTotal(date(2026, 11, 2), 734, 165.5)]

    labels = texts(parse(daily_chart(daily)))

    assert labels.count("0") == 2
    assert {"400", "800", "100", "200"} <= set(labels)


def test_daily_chart_places_days_by_date_so_gaps_show() -> None:
    daily = [
        DailyTotal(date(2026, 11, 2), 10, 1.0),
        DailyTotal(date(2026, 11, 3), 10, 1.0),
        DailyTotal(date(2026, 11, 6), 10, 1.0),
    ]

    root = parse(daily_chart(daily))

    xs = [float(p.get("cx")) for p in with_class(root, "circle", "point")][:3]
    assert xs[2] - xs[1] == pytest.approx(3 * (xs[1] - xs[0]))


def test_daily_chart_point_tooltips_name_the_day_and_value() -> None:
    root = parse(daily_chart([DailyTotal(date(2026, 11, 3), 1234, 165.5)]))

    tooltips = [p.find("title").text for p in with_class(root, "circle", "point")]
    assert tooltips == ["Tue 3 Nov: attendance 1,234", "Tue 3 Nov: staff hours 165.5"]


@pytest.mark.parametrize(
    ("attendance", "top_label"),
    [(1, "1"), (7, "8"), (95, "100"), (101, "150"), (205, "250"), (2900, "3,000")],
)
def test_daily_axis_top_is_the_next_round_number(
    attendance: int, top_label: str
) -> None:
    labels = texts(parse(daily_chart([DailyTotal(date(2026, 11, 2), attendance, 1.0)])))

    assert top_label in labels


def test_daily_chart_labels_at_most_seven_dates() -> None:
    daily = [DailyTotal(date(2026, 11, day), 10, 1.0) for day in range(2, 16)]

    labels = [t for t in texts(parse(daily_chart(daily))) if " Nov" in t]

    assert labels == [
        "Mon 2 Nov",
        "Wed 4 Nov",
        "Fri 6 Nov",
        "Sun 8 Nov",
        "Tue 10 Nov",
        "Thu 12 Nov",
        "Sat 14 Nov",
    ]


def test_shortfall_bar_is_proportional_to_the_largest_shortfall() -> None:
    full = parse(shortfall_bar(4, 4))
    half = parse(shortfall_bar(2, 4))

    assert float(full.find("rect").get("width")) == SHORTFALL_BAR_WIDTH
    assert float(half.find("rect").get("width")) == SHORTFALL_BAR_WIDTH / 2


def test_shortfall_bar_text_alternative_states_the_shortfall() -> None:
    assert chart_title(parse(shortfall_bar(1, 3))) == "Short by 1 staff member"
    assert chart_title(parse(shortfall_bar(3, 3))) == "Short by 3 staff members"


@pytest.mark.parametrize("draw", [centre_bar_chart, heatmap, daily_chart])
def test_empty_data_gives_a_no_data_chart(draw: Callable[[list], str]) -> None:
    root = parse(draw([]))

    assert texts(root) == [NO_DATA_TEXT]
    assert chart_title(root).endswith(NO_DATA_TEXT)


def test_daily_chart_with_all_zero_values_draws_points_on_the_baseline() -> None:
    root = parse(daily_chart([DailyTotal(date(2026, 11, 2), 0, 0.0)]))

    grid_bottoms = [float(line.get("y1")) for line in with_class(root, "line", "grid")]
    points = [float(p.get("cy")) for p in with_class(root, "circle", "point")]
    assert points == [grid_bottoms[0], grid_bottoms[3]]
