"""Tests for the optional Claude summary, using a fake client and no network."""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from builders import run_sample

from roster_check import summarise as summarise_module
from roster_check.models import Kpis, ReportData, Shift
from roster_check.summarise import (
    DEFAULT_MODEL,
    FALLBACK_BETA,
    NO_API_KEY,
    NO_PACKAGE,
    SYSTEM_PROMPT,
    build_prompt,
    skip_reason,
    summarise,
)

KEY = {"ANTHROPIC_API_KEY": "test-key-not-real"}


def text_block(text: str) -> SimpleNamespace:
    """Build a response content block holding text."""
    return SimpleNamespace(type="text", text=text)


def response(*blocks: SimpleNamespace, stop_reason: str = "end_turn") -> Any:
    """Build a response shaped like the SDK's message object."""
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


@dataclass
class FakeMessages:
    """Records each request and returns a fixed response or raises."""

    reply: Any = None
    error: Exception | None = None
    requests: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **request: Any) -> Any:
        """Record the request, then raise or return the fixed reply."""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


class FakeClient:
    """Stands in for ``anthropic.Anthropic``; only ``beta.messages`` is used."""

    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        """Set the reply to return or the error to raise."""
        self.messages = FakeMessages(reply, error)
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.fixture(scope="module")
def sample() -> tuple[ReportData, tuple[Shift, ...]]:
    """The sample report figures and the valid shifts they came from."""
    report, data_files = run_sample()
    return report, data_files[0].valid


def empty_report() -> ReportData:
    """Report figures for data with no sessions."""
    return ReportData(
        period_start=None,
        period_end=None,
        kpis=Kpis(0, 0, 0.0, 0, 3),
        centres=(),
        heatmap=(),
        daily=(),
        worst_sessions=(),
        staffing_rules=(),
    )


def test_no_api_key_skips_the_summary() -> None:
    assert skip_reason({}) == NO_API_KEY


def test_blank_api_key_skips_the_summary() -> None:
    assert skip_reason({"ANTHROPIC_API_KEY": ""}) == NO_API_KEY


def test_missing_package_skips_the_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summarise_module.importlib.util, "find_spec", lambda name: None)

    assert skip_reason(KEY) == NO_PACKAGE


def test_key_and_package_present_allow_the_summary() -> None:
    pytest.importorskip("anthropic")

    assert skip_reason(KEY) is None


def test_summary_text_is_returned_from_a_finished_response(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(response(text_block("  Most sessions were staffed.  ")))

    assert summarise(sample[0], client=client, environ=KEY) == (
        "Most sessions were staffed."
    )


def test_request_uses_the_default_model_with_refusal_fallback(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(response(text_block("Summary.")))

    summarise(sample[0], client=client, environ=KEY)

    [request] = client.messages.requests
    assert request["model"] == DEFAULT_MODEL == "claude-opus-5-5"
    assert request["system"] == SYSTEM_PROMPT
    assert request["messages"] == [{"role": "user", "content": build_prompt(sample[0])}]
    assert request["output_config"] == {"effort": "low"}
    assert request["max_tokens"] == 16000
    assert request["betas"] == [FALLBACK_BETA]
    assert request["fallbacks"] == "default"


def test_custom_model_is_used_without_refusal_fallback(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(response(text_block("Summary.")))
    environ = {**KEY, "ROSTER_CHECK_MODEL": "claude-sonnet-5-5"}

    summarise(sample[0], client=client, environ=environ)

    [request] = client.messages.requests
    assert request["model"] == "claude-sonnet-5-5"
    assert "betas" not in request
    assert "fallbacks" not in request


def test_blank_model_setting_falls_back_to_the_default_model(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(response(text_block("Summary.")))

    summarise(sample[0], client=client, environ={**KEY, "ROSTER_CHECK_MODEL": ""})

    assert client.messages.requests[0]["model"] == DEFAULT_MODEL


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_response_that_did_not_finish_gives_no_summary(
    stop_reason: str, sample: tuple[ReportData, tuple[Shift, ...]]
) -> None:
    client = FakeClient(response(text_block("Partial"), stop_reason=stop_reason))

    assert summarise(sample[0], client=client, environ=KEY) is None


def test_only_text_blocks_are_used(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(
        response(
            SimpleNamespace(type="thinking", thinking=""),
            text_block("First sentence."),
            SimpleNamespace(type="fallback"),
            text_block("Second sentence."),
        )
    )

    assert summarise(sample[0], client=client, environ=KEY) == (
        "First sentence. Second sentence."
    )


def test_response_without_text_gives_no_summary(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(response(text_block("   ")))

    assert summarise(sample[0], client=client, environ=KEY) is None


def test_client_error_gives_no_summary(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    client = FakeClient(error=RuntimeError("unexpected"))

    assert summarise(sample[0], client=client, environ=KEY) is None


def test_sdk_connection_error_gives_no_summary(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    anthropic = pytest.importorskip("anthropic")
    client = FakeClient(error=anthropic.APIConnectionError(request=None))

    assert summarise(sample[0], client=client, environ=KEY) is None


def test_missing_key_without_a_client_gives_no_summary(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    assert summarise(sample[0], environ={}) is None


def test_client_is_created_from_the_environment_key_with_a_short_timeout(
    monkeypatch: pytest.MonkeyPatch, sample: tuple[ReportData, tuple[Shift, ...]]
) -> None:
    anthropic = pytest.importorskip("anthropic")
    created: list[dict[str, Any]] = []

    def fake_anthropic(**options: Any) -> FakeClient:
        created.append(options)
        return FakeClient(response(text_block("Summary.")))

    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic)

    assert summarise(sample[0], environ=KEY) == "Summary."
    assert created == [
        {"api_key": "test-key-not-real", "timeout": 30.0, "max_retries": 1}
    ]


def test_prompt_lists_the_sample_figures(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    lines = build_prompt(sample[0]).splitlines()

    assert lines[:6] == [
        "Staffing figures, Mon 2 Nov to Sun 15 Nov 2026:",
        "Sessions analysed: 281",
        "Understaffed sessions: 43 (15%)",
        "Staff hours rostered: 2,165.5",
        "Total attendance: 7,234",
        "Rows that could not be used: 17",
    ]
    assert "- Northgate: 17 of 70 sessions" in lines
    assert lines[
        lines.index("Largest gaps (day, starting hour, combined shortfall):") + 1
    ] == ("- Thursdays 16:00: 11 staff")
    worst_heading = lines.index("Worst sessions (centre, activity, date, time, need):")
    assert len(lines) - worst_heading - 1 == 5


def test_prompt_for_data_without_sessions_says_so() -> None:
    prompt = build_prompt(empty_report())

    assert prompt.splitlines()[0] == "Staffing figures, no sessions in the data:"
    assert "Rows that could not be used: 3" in prompt


def test_request_contains_no_staff_names_or_ids(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    report, shifts = sample
    client = FakeClient(response(text_block("Summary.")))

    summarise(report, client=client, environ=KEY)

    sent = json.dumps(client.messages.requests[0])
    identifiers = {shift.staff_id for shift in shifts}
    identifiers |= {shift.staff_name for shift in shifts if shift.staff_name}
    identifiers |= {session.session_id for session in report.worst_sessions}
    leaked = sorted(value for value in identifiers if value in sent)
    assert leaked == []


def test_prompt_does_not_depend_on_the_order_of_heatmap_cells(
    sample: tuple[ReportData, tuple[Shift, ...]],
) -> None:
    report = sample[0]
    reversed_report = ReportData(
        period_start=report.period_start,
        period_end=report.period_end,
        kpis=report.kpis,
        centres=report.centres,
        heatmap=tuple(reversed(report.heatmap)),
        daily=report.daily,
        worst_sessions=report.worst_sessions,
        staffing_rules=report.staffing_rules,
    )

    assert build_prompt(reversed_report) == build_prompt(report)
