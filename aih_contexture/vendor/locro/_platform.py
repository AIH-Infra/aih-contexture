"""Platform-specific constants and path helpers.

Shared by ``_dll`` and ``_download`` to avoid circular imports.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    LIB_NAME = "chrome_screen_ai.dll"
elif sys.platform in ("linux", "darwin"):
    LIB_NAME = "libchromescreenai.so"
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def chrome_component_bases() -> list[Path]:
    """Return candidate base directories for Chrome's screen_ai component."""
    if sys.platform == "win32":
        return [
            Path.home() / "AppData" / "Local" / "Google" / "Chrome"
            / "User Data" / "screen_ai",
        ]
    if sys.platform == "darwin":
        return [
            Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "screen_ai",
            Path.home() / "Library" / "Application Support" / "Chromium" / "screen_ai",
        ]
    # Linux: check Google Chrome, then Chromium
    return [
        Path.home() / ".config" / "google-chrome" / "screen_ai",
        Path.home() / ".config" / "chromium" / "screen_ai",
    ]


def default_model_dir() -> Path:
    """Base directory for downloaded / copied models."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "locro"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "locro"
    # XDG convention on Linux (and fallback for Windows without LOCALAPPDATA)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "locro"
    return Path.home() / ".local" / "share" / "locro"


def default_model_dir_display() -> str:
    """Human-readable string for --help text showing the default model dir."""
    if sys.platform == "win32":
        return "%LOCALAPPDATA%/locro"
    if sys.platform == "darwin":
        return "~/Library/Application Support/locro"
    return "~/.local/share/locro"


PLATFORM_TAG = "windows" if sys.platform == "win32" else ("mac" if sys.platform == "darwin" else "linux")


def _find_dropbox_dir() -> Path:
    """Locate the Dropbox directory, checking common locations."""
    home_dropbox = Path.home() / "Dropbox"
    if home_dropbox.is_dir():
        return home_dropbox
    if sys.platform == "win32":
        root_dropbox = Path("C:/Dropbox")
        if root_dropbox.is_dir():
            return root_dropbox
    return home_dropbox  # default even if it doesn't exist yet


def dropbox_zip_path() -> Path:
    """Path to the Dropbox zip for the current platform."""
    return _find_dropbox_dir() / "bin" / f"screen-ai-{PLATFORM_TAG}.zip"
