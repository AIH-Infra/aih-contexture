import json

from click.testing import CliRunner

from aih_contexture.scripts.evaluate_markdown import evaluate_markdown_cli


def test_evaluate_markdown_cli_writes_report(tmp_path):
    markdown_path = tmp_path / "sample.md"
    report_path = tmp_path / "markdown_eval.json"
    markdown_path.write_text("{0}\n\nhello\n\n{1}\n", encoding="utf-8")

    result = CliRunner().invoke(
        evaluate_markdown_cli,
        [str(markdown_path), "--output", str(report_path), "--strict"],
    )

    assert result.exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["results"][0]["metrics"]["anchor_count"] == 2


def test_evaluate_markdown_cli_strict_fails_for_invalid_markdown(tmp_path):
    markdown_path = tmp_path / "bad.md"
    markdown_path.write_text("{0}\n\n<!-- ImageDescription: id=\"x\" -->\n\n{2}\n", encoding="utf-8")

    result = CliRunner().invoke(
        evaluate_markdown_cli,
        [str(markdown_path), "--strict"],
    )

    assert result.exit_code != 0
    assert "Scholarly Markdown evaluation failed" in result.output
