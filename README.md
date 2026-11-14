# Roster Check

Roster Check is a small command-line tool that compares staff rosters with session attendance for a fictional multi-site recreation organisation. It finds sessions that were understaffed against simple staffing ratios and writes a single, self-contained HTML report that a centre manager can open in any browser.

The project is a worked example of building a small, well-tested data tool with Python, SQL and AI coding agents. All data in it is fictional.

## Status

In development. The full plan is in the [project brief](documentation/Roster%20Check%20-%20Project%20Brief.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run roster-check --version
```

Run the tests and checks:

```bash
uv run pytest --cov
uv run ruff check
uv run ruff format --check
```

## Licence

MIT. See [LICENSE](LICENSE).
