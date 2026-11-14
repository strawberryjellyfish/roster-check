# Roster Check

A Python command-line tool that reads roster and session CSVs for a fictional recreation organisation, loads them into DuckDB, finds understaffed sessions with plain SQL, and writes one self-contained HTML report. The project also shows a disciplined workflow with coding agents, so how the work is done matters as much as the code.

The full specification is [documentation/Roster Check - Project Brief.md](documentation/Roster%20Check%20-%20Project%20Brief.md). It is the source of truth for data columns and validation rules (section 4), report content (section 5), module contracts (section 6.2), testing (section 7) and milestone scope (section 9). Read the sections that apply before starting a milestone.

## Commands

```bash
uv sync --all-extras          # install runtime, dev and optional dependencies
uv run pytest --cov           # full test suite with coverage (gate: 90 percent)
uv run ruff check             # lint
uv run ruff format            # format (CI runs ruff format --check)
uv run roster-check           # run on the bundled sample data
```

## Workflow

- **Branches.** Work on a branch named after the milestone, for example `feat/m2-validation`. Never commit to `main`; it must always be green and runnable.
- **Scope.** Stay inside the current milestone. Work that belongs to a later milestone waits for that milestone's branch.
- **Before every commit**, run `uv run pytest`, `uv run ruff check` and `uv run ruff format --check`, and make sure all pass.
- **Commit only with permission.** Show the user the files changed and the proposed message, then wait for explicit confirmation. The user may edit or extend the message before approving; commit with their final wording exactly. Each approval covers one commit. Pushing, opening a pull request and merging also need confirmation each time.
- **Commits** follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`). Each holds one coherent change together with its tests.
- **Pull requests.** One per milestone, using the PR template. A PR is merged into `main` only after it has been reviewed (CodeRabbit and the user) and CI is green. Answer every review comment with a fix commit or a stated reason. Squash merge, delete the branch, and only then start the next feature.

## Ask, do not assume

- Use only data structures, column names, types and formats defined in the brief or in existing code. If a structure is not specified, ask before writing code against it.
- When a task needs information you do not have, stop and ask for clarification.
- Confirm with the user before removing or weakening any existing functionality: deleting functions, tests, CLI flags or validation rules, or loosening a check.
- Runtime dependencies are `duckdb` and `jinja2` only. Propose any new dependency, with the reason, and wait for approval.

## Code standards

- Python 3.11+ with modern syntax: type hints on every signature, `X | None` unions, built-in generics (`list[str]`, `dict[str, int]`), `dataclasses`, `pathlib`, f-strings, `match` where it reads more clearly.
- Standards compliant: PEP 8 as enforced by ruff, PEP 257 docstrings.
- Code must be readable by someone seeing it for the first time: descriptive names, small functions with one job, straightforward control flow over clever one-liners.
- Documentation:
  - Every module starts with a short docstring stating its job in the pipeline.
  - Every function has a docstring stating what it does and how to use it; describe arguments, return value and raised exceptions when the signature alone does not make them clear.
  - Docstrings use Google style (`Args:`, `Returns:`, `Raises:`), enforced by ruff. Test functions rely on descriptive names instead of docstrings.
  - Inline comments explain why, only where the reason is not obvious from the code. Code that reads clearly needs no comment.
- Consistency: write the same kind of code the same way across the whole codebase. Before writing, look at how existing code handles the same thing and match it. Where the syntax allows a choice, pick one form and use it everywhere. For example:
  - Optional parentheses, trailing commas and quote style follow `ruff format` output.
  - String building uses f-strings only.
  - Imports, error handling, docstrings and comments follow one layout throughout.
  - Similar modules share the same internal order (docstring, imports, constants, public functions, private helpers).
  If no convention exists yet, choose one, apply it throughout, and keep to it from then on.
- DRY: put shared logic in one function and reuse it (one parser per field type in `validate.py`, shared SVG helpers in `charts.py`). Search for an existing helper before writing a new one.
- Design for expansion through simple seams (pure functions, data passed in as arguments, rules held as data) and build only what the current milestone needs. Skip abstract base classes, plugin systems and options that have no current caller.
- Architecture: data flows one way, `ingest -> validate -> db -> analysis -> charts -> report`, and no module reaches back into an earlier one. Keep to the contracts in brief section 6.2:
  - `cli.py` is the only module that prints or writes output files.
  - All SQL lives in `.sql` files under `src/roster_check/sql/`.
  - `validate.py` and `charts.py` are pure: no I/O.

## Security and data handling

- Treat every CSV value as untrusted input. Validate and normalise it in `validate.py` before it reaches DuckDB or the report, following the cases in brief section 4.4.
- SQL: pass values as bound parameters. Never build SQL by string formatting with data values.
- HTML: Jinja2 autoescaping stays on. Mark content safe only for SVG produced by `charts.py`, and `charts.py` escapes every piece of text it embeds.
- The report makes no external requests: no `http://` or `https://` in `src`, `href` or `@import`. A test enforces this.
- Load packaged files (SQL, templates) with `importlib.resources`. Handle user-supplied paths with `pathlib` and report missing or unreadable files as clear input errors.
- The Claude summary sends aggregated numbers only, never staff names or IDs, and never raises. Read the API key from `ANTHROPIC_API_KEY` only; never log, print or write it to the report.
- Users never see a Python traceback unless `--debug` is set. Error messages state the problem in one plain line.
- Avoid `eval`, `exec`, `pickle` and `shell=True`. Run subprocesses with argument lists.
- All data is fictional. No real names, emails, phone numbers or addresses anywhere, including fixtures.

## Testing

- Every new function or behaviour arrives with tests in the same commit. Write tests first or alongside the code.
- Each bad-data case in brief section 4.4 has its own test asserting both the outcome and the exact reason text.
- Tests run without network access. The Claude summary is tested with a fake client; CI never calls the real API.
- Tests do not depend on the current date, time zone or locale. Inject the clock where time is needed.
- Keep fixtures as tiny CSVs in `tests/fixtures/`. The full suite runs in under 30 seconds.

## Writing style

Comments, docstrings, commit messages, PR descriptions and README text are plain, informative English that says what changed and why. No emojis, decorative characters, ASCII banners or excessive punctuation.
