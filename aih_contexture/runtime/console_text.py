from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


_CONSOLE_REPLACEMENTS = (
    ("⚠️", "[WARN]"),
    ("⏱️", "[TIME]"),
    ("⏹️", "[STOP]"),
    ("▶️", "[START]"),
    ("✅", "[OK]"),
    ("❌", "[ERROR]"),
    ("⚠", "[WARN]"),
    ("🚀", "[START]"),
    ("📊", "[INFO]"),
    ("🧭", "[PLAN]"),
    ("🎉", "[DONE]"),
    ("🔄", "[RETRY]"),
    ("⏳", "[WAIT]"),
    ("💾", "[SAVE]"),
    ("📁", "[DIR]"),
    ("📄", "[FILE]"),
    ("📝", "[NOTE]"),
    ("🔍", "[DEBUG]"),
    ("🔧", "[CONFIG]"),
    ("🆕", "[NEW]"),
    ("✨", ""),
    ("⏹", "[STOP]"),
    ("▶", "[START]"),
    ("→", "->"),
)


def sanitize_console_text(text: str) -> str:
    """Normalize decorative runtime output for predictable terminals."""

    sanitized = str(text)
    for source, replacement in _CONSOLE_REPLACEMENTS:
        sanitized = sanitized.replace(source, replacement)
    return sanitized.replace("\ufe0f", "").replace("\u200d", "")


def safe_endpoint_for_log(value: object) -> str:
    """Return an endpoint without credentials, query parameters, or fragments."""

    text = str(value or "").strip()
    if not text:
        return "<default>"
    try:
        parts = urlsplit(text)
    except ValueError:
        return "<configured>"
    if not parts.scheme or not parts.hostname:
        return "<configured>"
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))
