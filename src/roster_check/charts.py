"""Charts: turn report figures into SVG strings for the HTML report.

Every function is pure and returns an SVG element as text. The SVG holds no
colours or animation: elements carry CSS classes and a ``--delay`` style, and
the report's stylesheet decides how they look and move. All text written into
the SVG is escaped.
"""

import math
from collections.abc import Sequence
from datetime import date
from html import escape

from roster_check.models import CentreSummary, DailyTotal, HeatmapCell

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

NO_DATA_TEXT = "No data to show"

# A shortfall at or above each threshold moves a heatmap cell up one shade, so
# the levels are 0, 1, 2 to 3, 4 to 6, and 7 or more. Fixed values mean the
# same shortfall has the same shade in every report.
SHADE_THRESHOLDS = (1, 2, 4, 7)

# Seconds between one element's entry animation and the next.
STAGGER_SECONDS = 0.08

BAR_CHART_WIDTH = 640
BAR_LABEL_WIDTH = 170
BAR_AREA_WIDTH = 300
BAR_ROW_HEIGHT = 36
BAR_HEIGHT = 22

HEATMAP_LABEL_WIDTH = 44
HEATMAP_HEADER_HEIGHT = 22
HEATMAP_CELL_WIDTH = 38
HEATMAP_CELL_HEIGHT = 30

DAILY_CHART_WIDTH = 640
DAILY_AXIS_WIDTH = 56
DAILY_RIGHT_MARGIN = 24
DAILY_PANEL_HEIGHT = 120
DAILY_PANEL_TITLE_HEIGHT = 24
DAILY_PANEL_GAP = 16
DAILY_DATE_LABEL_HEIGHT = 28
DAILY_MAX_DATE_LABELS = 7

# Multiples of a power of ten allowed as the top of an axis. Halving each
# gives the middle gridline, which stays a round number too.
AXIS_STEPS = (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)

SHORTFALL_BAR_WIDTH = 80
SHORTFALL_BAR_HEIGHT = 12


def format_day(day: date) -> str:
    """Return a date as a short label, for example ``Tue 4 Nov``.

    Day and month names are fixed English names, so the label does not depend
    on the computer's locale.
    """
    return f"{WEEKDAY_NAMES[day.weekday()]} {day.day} {MONTH_NAMES[day.month - 1]}"


def centre_bar_chart(centres: Sequence[CentreSummary]) -> str:
    """Draw one horizontal bar per centre showing its understaffed sessions.

    Bar length is the centre's understaffed percentage, scaled so the largest
    percentage fills the bar area. Each bar is labelled with the count and the
    percentage.

    Args:
        centres: Understaffing at each centre, in the order to draw them.

    Returns:
        An SVG element, or a "no data" SVG when there are no centres.
    """
    title = "Understaffed sessions by centre"
    if not centres:
        return _no_data(title)

    largest = max(centre.understaffed_percent for centre in centres)
    parts = []
    for index, centre in enumerate(centres):
        top = index * BAR_ROW_HEIGHT
        bar_top = top + (BAR_ROW_HEIGHT - BAR_HEIGHT) / 2
        middle = top + BAR_ROW_HEIGHT / 2
        width = _scale(centre.understaffed_percent, largest, BAR_AREA_WIDTH)
        label = (
            f"{centre.understaffed_sessions} of {centre.sessions} "
            f"({centre.understaffed_percent:.0f}%)"
        )
        parts.append(
            _text(
                BAR_LABEL_WIDTH - 10, middle, centre.centre_name, "label", anchor="end"
            )
        )
        parts.append(
            f'<rect class="bar" x="{BAR_LABEL_WIDTH}" y="{_number(bar_top)}" '
            f'width="{_number(width)}" height="{BAR_HEIGHT}" '
            f'style="{_delay(index)}">'
            f"<title>{escape(centre.centre_name)}: {escape(label)}</title></rect>"
        )
        parts.append(_text(BAR_LABEL_WIDTH + width + 8, middle, label, "value"))

    height = len(centres) * BAR_ROW_HEIGHT
    return _svg(BAR_CHART_WIDTH, height, title, parts, "centre-bars")


def heatmap(cells: Sequence[HeatmapCell]) -> str:
    """Draw understaffing by day of the week and the hour sessions start.

    Rows are Monday to Sunday and columns run from the earliest to the latest
    hour with sessions. A cell's shade shows its shortfall (see
    ``shade_level``) and cells with a shortfall also show the number. An hour
    with no sessions is drawn as an empty cell.

    Args:
        cells: Heatmap cells, only for hours that have sessions.

    Returns:
        An SVG element, or a "no data" SVG when there are no cells.
    """
    title = "Staff shortfall by day of the week and starting hour"
    if not cells:
        return _no_data(title)

    first_hour = min(cell.hour for cell in cells)
    last_hour = max(cell.hour for cell in cells)
    hours = range(first_hour, last_hour + 1)
    by_position = {(cell.weekday, cell.hour): cell for cell in cells}

    parts = []
    for column, hour in enumerate(hours):
        centre = _heatmap_x(column) + HEATMAP_CELL_WIDTH / 2
        parts.append(
            _text(
                centre,
                HEATMAP_HEADER_HEIGHT / 2,
                f"{hour:02d}",
                "axis",
                anchor="middle",
            )
        )
    for weekday, day_name in enumerate(WEEKDAY_NAMES):
        middle = _heatmap_y(weekday) + HEATMAP_CELL_HEIGHT / 2
        parts.append(
            _text(HEATMAP_LABEL_WIDTH - 8, middle, day_name, "axis", anchor="end")
        )
        for column, hour in enumerate(hours):
            cell = by_position.get((weekday, hour))
            parts.append(_heatmap_cell(column, weekday, cell))

    width = HEATMAP_LABEL_WIDTH + len(hours) * HEATMAP_CELL_WIDTH
    height = HEATMAP_HEADER_HEIGHT + len(WEEKDAY_NAMES) * HEATMAP_CELL_HEIGHT
    return _svg(width, height, title, parts, "heatmap")


def shade_level(shortfall: int) -> int:
    """Return the heatmap shade, 0 to 4, for a total shortfall."""
    return sum(1 for threshold in SHADE_THRESHOLDS if shortfall >= threshold)


def daily_chart(daily: Sequence[DailyTotal]) -> str:
    """Draw attendance and staff hours per day as two aligned line panels.

    Attendance is the top panel and staff hours the bottom one. The panels
    share the date axis, and each has its own axis starting at zero. Days are
    placed by date, so a day missing from the data widens the space between
    its neighbours' points.

    Args:
        daily: Totals for each day, in date order.

    Returns:
        An SVG element, or a "no data" SVG when there are no days.
    """
    title = "Attendance and staff hours per day"
    if not daily:
        return _no_data(title)

    days = [total.day for total in daily]
    x_positions = [_daily_x(day, days[0], days[-1]) for day in days]
    panel_step = DAILY_PANEL_TITLE_HEIGHT + DAILY_PANEL_HEIGHT + DAILY_PANEL_GAP
    parts = [
        *_line_panel(
            "Attendance",
            x_positions,
            [float(total.attendance) for total in daily],
            days,
            top=0,
        ),
        *_line_panel(
            "Staff hours",
            x_positions,
            [total.staff_hours for total in daily],
            days,
            top=panel_step,
        ),
    ]
    date_label_top = 2 * panel_step - DAILY_PANEL_GAP
    step = math.ceil(len(days) / DAILY_MAX_DATE_LABELS)
    for x, day in list(zip(x_positions, days, strict=True))[::step]:
        parts.append(
            _text(
                x,
                date_label_top + DAILY_DATE_LABEL_HEIGHT / 2,
                format_day(day),
                "axis",
                anchor="middle",
            )
        )

    height = date_label_top + DAILY_DATE_LABEL_HEIGHT
    return _svg(DAILY_CHART_WIDTH, height, title, parts, "daily")


def shortfall_bar(shortfall: int, largest: int) -> str:
    """Draw the small inline bar showing one session's shortfall.

    Args:
        shortfall: The session's total shortfall.
        largest: The largest shortfall in the table, which fills the bar.

    Returns:
        An SVG element.
    """
    width = _scale(shortfall, largest, SHORTFALL_BAR_WIDTH)
    parts = [
        f'<rect class="bar" x="0" y="0" width="{_number(width)}" '
        f'height="{SHORTFALL_BAR_HEIGHT}" />'
    ]
    return _svg(
        SHORTFALL_BAR_WIDTH,
        SHORTFALL_BAR_HEIGHT,
        f"Short by {_plural(shortfall, 'staff member')}",
        parts,
        "shortfall-bar",
    )


def _heatmap_cell(column: int, weekday: int, cell: HeatmapCell | None) -> str:
    """Return the SVG for one heatmap cell, empty when it has no sessions."""
    x = _heatmap_x(column)
    y = _heatmap_y(weekday)
    position = (
        f'x="{x}" y="{y}" width="{HEATMAP_CELL_WIDTH}" height="{HEATMAP_CELL_HEIGHT}"'
    )
    if cell is None:
        return f'<rect class="cell empty" {position} />'

    tooltip = (
        f"{WEEKDAY_NAMES[weekday]} {cell.hour:02d}:00: "
        f"{_plural(cell.sessions, 'session')}, "
        f"{cell.understaffed_sessions} understaffed, shortfall {cell.shortfall}"
    )
    parts = [
        f'<g class="cell shade-{shade_level(cell.shortfall)}" '
        f'style="{_delay(column)}">',
        f"<title>{escape(tooltip)}</title>",
        f"<rect {position} />",
    ]
    if cell.shortfall > 0:
        parts.append(
            _text(
                x + HEATMAP_CELL_WIDTH / 2,
                y + HEATMAP_CELL_HEIGHT / 2,
                str(cell.shortfall),
                "cell-value",
                anchor="middle",
            )
        )
    parts.append("</g>")
    return "".join(parts)


def _heatmap_x(column: int) -> int:
    """Return the left edge of a heatmap column."""
    return HEATMAP_LABEL_WIDTH + column * HEATMAP_CELL_WIDTH


def _heatmap_y(row: int) -> int:
    """Return the top edge of a heatmap row."""
    return HEATMAP_HEADER_HEIGHT + row * HEATMAP_CELL_HEIGHT


def _daily_x(day: date, first: date, last: date) -> float:
    """Return the horizontal position of a day on the daily chart."""
    left = DAILY_AXIS_WIDTH
    width = DAILY_CHART_WIDTH - DAILY_AXIS_WIDTH - DAILY_RIGHT_MARGIN
    span = (last - first).days
    if span == 0:
        return left + width / 2
    return left + width * (day - first).days / span


def _line_panel(
    name: str,
    x_positions: Sequence[float],
    values: Sequence[float],
    days: Sequence[date],
    *,
    top: float,
) -> list[str]:
    """Return the SVG parts for one panel of the daily chart.

    Args:
        name: Panel title, also used in each point's tooltip.
        x_positions: Horizontal position of each value.
        values: The values to plot, one per day.
        days: The day of each value, for the tooltips.
        top: Top edge of the panel.

    Returns:
        The panel title, axis lines and labels, the line and its points.
    """
    plot_top = top + DAILY_PANEL_TITLE_HEIGHT
    plot_bottom = plot_top + DAILY_PANEL_HEIGHT
    axis_max = _nice_ceiling(max(values))
    right = DAILY_CHART_WIDTH - DAILY_RIGHT_MARGIN

    parts = [_text(DAILY_AXIS_WIDTH, top + DAILY_PANEL_TITLE_HEIGHT / 2, name, "title")]
    for fraction in (0.0, 0.5, 1.0):
        y = plot_bottom - fraction * DAILY_PANEL_HEIGHT
        parts.append(
            f'<line class="grid" x1="{DAILY_AXIS_WIDTH}" y1="{_number(y)}" '
            f'x2="{right}" y2="{_number(y)}" />'
        )
        parts.append(
            _text(
                DAILY_AXIS_WIDTH - 8,
                y,
                _format_value(fraction * axis_max),
                "axis",
                anchor="end",
            )
        )

    points = [
        (x, plot_bottom - _scale(value, axis_max, DAILY_PANEL_HEIGHT))
        for x, value in zip(x_positions, values, strict=True)
    ]
    path = " ".join(
        f"{'M' if index == 0 else 'L'} {_number(x)} {_number(y)}"
        for index, (x, y) in enumerate(points)
    )
    parts.append(f'<path class="line" d="{path}" pathLength="1" />')
    for (x, y), value, day in zip(points, values, days, strict=True):
        tooltip = f"{format_day(day)}: {name.lower()} {_format_value(value)}"
        parts.append(
            f'<circle class="point" cx="{_number(x)}" cy="{_number(y)}" r="3">'
            f"<title>{escape(tooltip)}</title></circle>"
        )
    return parts


def _svg(width: float, height: float, title: str, parts: list[str], name: str) -> str:
    """Wrap chart parts in an SVG element with a text alternative.

    Args:
        width: Width of the drawing in SVG units.
        height: Height of the drawing in SVG units.
        title: Text alternative, read by screen readers and shown on hover.
        parts: SVG elements to place inside.
        name: Extra CSS class identifying the chart.

    Returns:
        The SVG element. It scales to its container through ``viewBox``.
    """
    return (
        f'<svg class="chart {name}" viewBox="0 0 {_number(width)} {_number(height)}" '
        f'role="img"><title>{escape(title)}</title>{"".join(parts)}</svg>'
    )


def _no_data(title: str) -> str:
    """Return a small SVG saying there is nothing to show."""
    message = _text(BAR_CHART_WIDTH / 2, 30, NO_DATA_TEXT, "no-data", anchor="middle")
    return _svg(BAR_CHART_WIDTH, 60, f"{title}: {NO_DATA_TEXT}", [message], "empty")


def _text(
    x: float, y: float, content: str, css_class: str, *, anchor: str = "start"
) -> str:
    """Return an escaped SVG text element centred vertically on ``y``.

    Args:
        x: Horizontal position of the anchor point.
        y: Vertical centre of the text.
        content: The text, which is escaped.
        css_class: CSS class for styling.
        anchor: Which part of the text sits at ``x``: "start", "middle" or
            "end".

    Returns:
        The SVG text element.
    """
    return (
        f'<text class="{css_class}" x="{_number(x)}" y="{_number(y)}" '
        f'text-anchor="{anchor}" dominant-baseline="central">'
        f"{escape(content)}</text>"
    )


def _scale(value: float, largest: float, length: float) -> float:
    """Return ``value`` as a share of ``length``, where ``largest`` fills it."""
    return 0.0 if largest <= 0 else length * value / largest


def _nice_ceiling(value: float) -> float:
    """Return the smallest round number at or above ``value``.

    A round number is one of ``AXIS_STEPS`` times a power of ten. Used as the
    top of an axis so the gridline labels are round and little space is lost.
    """
    if value <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(value))
    return float(next(step * power for step in AXIS_STEPS if value <= step * power))


def _format_value(value: float) -> str:
    """Return a value with thousands separators and at most one decimal place."""
    return f"{value:,.1f}".removesuffix(".0")


def _number(value: float) -> str:
    """Return a coordinate rounded to one decimal place, without a trailing .0."""
    return f"{value:.1f}".removesuffix(".0")


def _delay(index: int) -> str:
    """Return the inline style that staggers an element's entry animation."""
    return f"--delay: {index * STAGGER_SECONDS:.2f}s"


def _plural(count: int, word: str) -> str:
    """Return ``count`` with ``word``, adding an "s" unless the count is 1."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"
