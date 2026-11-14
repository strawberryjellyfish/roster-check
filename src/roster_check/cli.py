"""Command-line interface: parses arguments and returns the process exit code."""

import argparse

from roster_check import __version__


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the ``roster-check`` command.

    Returns:
        A parser configured with every supported option.
    """
    parser = argparse.ArgumentParser(
        prog="roster-check",
        description=(
            "Check staff rosters against session attendance "
            "and report understaffed sessions."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line tool.

    Args:
        argv: Arguments excluding the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 on success.
    """
    parser = build_parser()
    parser.parse_args(argv)
    return 0
