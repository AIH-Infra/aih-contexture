from click.testing import CliRunner

from aih_contexture.scripts.backends import backends_cli
from aih_contexture.scripts.doctor import doctor_cli


def test_backends_cli_prints_compact_catalog():
    result = CliRunner().invoke(backends_cli, [])

    assert result.exit_code == 0
    assert "layout:" in result.output
    assert "surya" in result.output
    assert "ocr:" in result.output


def test_backends_cli_can_include_status_as_json(tmp_path):
    result = CliRunner().invoke(
        backends_cli,
        [
            "--status",
            "--json-output",
            "--mineru-command",
            str(tmp_path / "missing-mineru"),
        ],
    )

    assert result.exit_code == 0
    assert '"status"' in result.output
    assert '"mineru_pp_doclayout_v2"' in result.output
    assert '"missing_dependency"' in result.output


def test_backends_cli_accepts_service_probe_options(tmp_path):
    result = CliRunner().invoke(
        backends_cli,
        [
            "--status",
            "--json-output",
            "--mineru-command",
            str(tmp_path / "missing-mineru"),
            "--openai-base-url",
            "http://127.0.0.1:1234/v1",
            "--health-timeout",
            "1.0",
        ],
    )

    assert result.exit_code == 0
    assert '"status"' in result.output


def test_doctor_cli_prints_status_report(tmp_path):
    result = CliRunner().invoke(
        doctor_cli,
        [
            "--mineru-command",
            str(tmp_path / "missing-mineru"),
        ],
    )

    assert result.exit_code == 0
    assert "AIH-Contexture backend doctor" in result.output
    assert "summary:" in result.output
    assert "mineru_pp_doclayout_v2" in result.output
