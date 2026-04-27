import os
import sys
from unittest.mock import Mock

import pytest

from aih_contexture.scripts.run_streamlit_app import (
    DEFAULT_STREAMLIT_HOST,
    DEFAULT_STREAMLIT_PORT,
    _find_available_port,
    streamlit_app_cli,
)


def test_find_available_port_prefers_default_port(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._get_windows_excluded_ports",
        lambda: set(),
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._is_port_available",
        lambda host, port: port == DEFAULT_STREAMLIT_PORT,
    )

    assert _find_available_port() == DEFAULT_STREAMLIT_PORT


def test_find_available_port_increments_when_default_is_busy(monkeypatch):
    busy_ports = {8501, 8502}
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._get_windows_excluded_ports",
        lambda: set(),
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._is_port_available",
        lambda host, port: port not in busy_ports,
    )

    assert _find_available_port() == 8503


def test_find_available_port_skips_windows_excluded_ports(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._get_windows_excluded_ports",
        lambda: {8501, 8502, 8503},
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._is_port_available",
        lambda host, port: True,
    )

    assert _find_available_port() == 8504


def test_find_available_port_raises_when_no_port_is_available(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._get_windows_excluded_ports",
        lambda: set(),
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._is_port_available",
        lambda host, port: False,
    )

    with pytest.raises(RuntimeError, match="No available Streamlit port found"):
        _find_available_port(max_attempts=3)


def test_streamlit_app_cli_passes_selected_port(monkeypatch):
    run_calls = []

    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._find_available_port",
        lambda host=DEFAULT_STREAMLIT_HOST, start_port=8501, max_attempts=1000: 8504,
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app._get_local_ip",
        lambda: "192.168.31.99",
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.run_streamlit_app.subprocess.run",
        lambda cmd, env=None: run_calls.append((cmd, env)),
    )
    monkeypatch.setattr(sys, "argv", ["contexture_app.py"])

    streamlit_app_cli()

    cmd, env = run_calls[0]
    assert cmd[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert "--server.address" in cmd
    assert cmd[cmd.index("--server.address") + 1] == DEFAULT_STREAMLIT_HOST
    assert "--server.port" in cmd
    assert cmd[cmd.index("--server.port") + 1] == "8504"
    assert env["IN_STREAMLIT"] == "true"
    assert env["CUDA_VISIBLE_DEVICES"] == "0"
