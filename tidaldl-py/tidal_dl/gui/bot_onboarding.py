"""Backend configuration-state detection for the Discord bot onboarding
flow (onboarding-backend R1).

Two states only:

* ``configured``  — the shared-token file exists and is non-empty.
* ``needs-setup`` — otherwise.

The shared-token file is written by the GUI Bot Control panel
(``/bot-control/configure``). We only check existence+non-empty — no
parsing or validation.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, TextIO

from tidal_dl.helper.path import path_config_base

SHARED_TOKEN_FILENAME = "bot-shared-token"

GUI_SETUP_MESSAGE = (
    "\nDiscord bot setup is GUI-only. Open `music-dl gui`, go to the DJAI "
    "panel, and use Bot Control (/bot-control) to save config and deploy "
    "the bot.\n"
)


class OnboardingState(str, Enum):
    CONFIGURED = "configured"
    NEEDS_SETUP = "needs-setup"


def shared_token_path() -> Path:
    """Canonical shared-token file path (same one the GUI writes)."""
    override = os.environ.get("MUSIC_DL_BOT_TOKEN_PATH", "").strip()
    if override:
        return Path(override)
    return Path(path_config_base()) / SHARED_TOKEN_FILENAME


def detect_state(token_path: Path | None = None) -> OnboardingState:
    """Resolve the current onboarding state (R1)."""
    token = token_path if token_path is not None else shared_token_path()
    if _file_non_empty(token):
        return OnboardingState.CONFIGURED
    return OnboardingState.NEEDS_SETUP


class TokenSource(str, Enum):
    """Where the backend will resolve the bot shared secret from."""
    ENV = "env"
    FILE = "file"
    NONE = "none"


def bot_token_source(
    env_getter: Optional[Callable[[str, str], str]] = None,
    path_resolver: Optional[Callable[[], Path]] = None,
) -> TokenSource:
    """Report where :func:`tidal_dl.gui.security.resolve_bot_shared_token`
    will actually pull the bot shared secret from, without disclosing the
    secret itself. Used as the startup canary.

    Priority mirrors ``resolve_bot_shared_token``: env var first, then
    the GUI-written file. The optional ``env_getter`` and
    ``path_resolver`` parameters let unit tests exercise every source
    branch via dependency injection — no ``os.environ`` or disk
    manipulation required.
    """
    get_env = env_getter or (lambda key, default: os.environ.get(key, default))
    if (get_env("MUSIC_DL_BOT_TOKEN", "") or "").strip():
        return TokenSource.ENV
    resolve_path = path_resolver or shared_token_path
    if _file_non_empty(resolve_path()):
        return TokenSource.FILE
    return TokenSource.NONE


def _file_non_empty(path: Path) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    if not stat.st_size:
        return False
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return len(content) > 0


HINT_TEXT = (
    "Discord bot not configured — open the DJAI panel in `music-dl gui` "
    "and use Bot Control to set it up.\n"
)


def print_setup_hint(
    is_tty_fn: Callable[[], bool] | None = None,
    detect_fn: Callable[[], OnboardingState] | None = None,
    output: TextIO | None = None,
) -> None:
    import sys

    resolved_is_tty = is_tty_fn or sys.stdout.isatty
    resolved_detect = detect_fn or detect_state
    if not resolved_is_tty():
        return
    if resolved_detect() is OnboardingState.CONFIGURED:
        return
    out: TextIO = output if output is not None else sys.stdout
    out.write(HINT_TEXT)
    out.flush()


def dispatch_wizard(out: TextIO | None = None) -> int:
    import sys

    resolved_out: TextIO = out if out is not None else sys.stdout
    resolved_out.write(GUI_SETUP_MESSAGE)
    resolved_out.flush()
    return 0


def run_setup_force(
    output: TextIO | None = None,
) -> int:
    import sys

    out: TextIO = output if output is not None else sys.stdout
    out.write(GUI_SETUP_MESSAGE)
    out.flush()
    return 0