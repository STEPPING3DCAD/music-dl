"""R2 (non-blocking hint) + R3 (GUI-only setup) acceptance tests."""

from __future__ import annotations

import io

import pytest

from tidal_dl.gui import bot_onboarding as bot_onboarding_module
from tidal_dl.gui.bot_onboarding import (
    GUI_SETUP_MESSAGE,
    HINT_TEXT,
    OnboardingState,
    dispatch_wizard,
    print_setup_hint,
    run_setup_force,
)


# --------------------------------------------------------------------------
# R2: print_setup_hint — one line, non-blocking, no prompts
# --------------------------------------------------------------------------


def test_r2_ac1_needs_setup_on_tty_prints_hint() -> None:
    out = io.StringIO()
    print_setup_hint(
        is_tty_fn=lambda: True,
        detect_fn=lambda: OnboardingState.NEEDS_SETUP,
        output=out,
    )
    assert out.getvalue() == HINT_TEXT
    assert "DJAI" in out.getvalue()
    assert "Bot Control" in out.getvalue()


def test_r2_ac2_configured_prints_nothing() -> None:
    out = io.StringIO()
    print_setup_hint(
        is_tty_fn=lambda: True,
        detect_fn=lambda: OnboardingState.CONFIGURED,
        output=out,
    )
    assert out.getvalue() == ""


def test_r2_ac4_no_prompt_no_blocking() -> None:
    out = io.StringIO()
    print_setup_hint(
        is_tty_fn=lambda: True,
        detect_fn=lambda: OnboardingState.NEEDS_SETUP,
        output=out,
    )
    assert out.getvalue().count("\n") == 1


def test_r2_ac5_non_tty_suppresses_hint() -> None:
    out = io.StringIO()
    print_setup_hint(
        is_tty_fn=lambda: False,
        detect_fn=lambda: OnboardingState.NEEDS_SETUP,
        output=out,
    )
    assert out.getvalue() == ""


# --------------------------------------------------------------------------
# R3: run_setup_force — GUI-only setup message
# --------------------------------------------------------------------------


def test_r3_force_prints_gui_setup_message() -> None:
    out = io.StringIO()
    rc = run_setup_force(output=out)
    assert rc == 0
    assert out.getvalue() == GUI_SETUP_MESSAGE
    assert "DJAI" in out.getvalue()
    assert "/bot-control" in out.getvalue()


def test_r3_ac6_always_returns_zero() -> None:
    out = io.StringIO()
    rc = run_setup_force(output=out)
    assert rc == 0


def test_r3_force_without_tty_still_prints_gui_message() -> None:
    out = io.StringIO()
    rc = run_setup_force(output=out)
    assert rc == 0
    assert out.getvalue() == GUI_SETUP_MESSAGE


def test_dispatch_wizard_prints_gui_message() -> None:
    out = io.StringIO()
    rc = dispatch_wizard(out=out)
    assert rc == 0
    assert out.getvalue() == GUI_SETUP_MESSAGE


def test_dispatch_wizard_does_not_spawn_subprocess() -> None:
    out = io.StringIO()
    rc = dispatch_wizard(out=out)
    assert rc == 0
    assert "wizard" not in out.getvalue().lower()


# --------------------------------------------------------------------------
# Regression: the deleted interactive path stays deleted
# --------------------------------------------------------------------------


def test_regression_no_exported_interactive_prompt() -> None:
    """The prior-revision interactive TTY prompt is deleted. These symbols
    should no longer exist on the module — guard against a reintroduction
    that would re-hijack `music-dl gui`."""
    for name in (
        "ask_user",
        "classify_answer",
        "decide_startup_action",
        "should_prompt",
        "write_dismissal_flag",
        "run_first_run_flow",
        "PromptAnswer",
        "PromptDecision",
    ):
        assert not hasattr(bot_onboarding_module, name), (
            f"{name} was removed in the 2026-04-20 kit revision; normal "
            "`music-dl gui` must not hijack the terminal. Do not re-add "
            "without revising cavekit-onboarding-backend.md first."
        )


# --------------------------------------------------------------------------
# OnboardingState simplified to two values
# --------------------------------------------------------------------------


def test_onboarding_state_has_two_values_only() -> None:
    values = {s.value for s in OnboardingState}
    assert values == {"configured", "needs-setup"}


@pytest.mark.parametrize(
    "state,expected_hint",
    [
        (OnboardingState.CONFIGURED, False),
        (OnboardingState.NEEDS_SETUP, True),
    ],
)
def test_hint_visibility_matrix(
    state: OnboardingState, expected_hint: bool
) -> None:
    out = io.StringIO()
    print_setup_hint(
        is_tty_fn=lambda: True, detect_fn=lambda: state, output=out
    )
    assert bool(out.getvalue()) is expected_hint


def test_r3_ac5_force_does_not_consult_detect_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_setup_force must not branch on the current onboarding state."""

    def explode(*_args: object, **_kwargs: object) -> OnboardingState:
        raise AssertionError(
            "run_setup_force must not consult detect_state (R3 AC5)"
        )

    monkeypatch.setattr(bot_onboarding_module, "detect_state", explode)

    out = io.StringIO()
    rc = run_setup_force(output=out)
    assert rc == 0
    assert out.getvalue() == GUI_SETUP_MESSAGE