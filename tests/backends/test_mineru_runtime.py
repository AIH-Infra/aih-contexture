import subprocess

from aih_contexture.backends.external_config import default_mineru_command, venv_executable
from aih_contexture.backends.layout.mineru_runtime import MineruCliLayoutRuntime


def test_mineru_runtime_builds_conservative_pipeline_command(tmp_path):
    pdf = tmp_path / "sample.pdf"
    out = tmp_path / "out"
    pdf.write_bytes(b"%PDF-1.4\n")
    runtime = MineruCliLayoutRuntime(
        {
            "mineru_command": "mineru",
            "mineru_output_dir": str(out),
            "mineru_backend": "pipeline",
            "mineru_method": "ocr",
            "mineru_lang": "latin",
            "mineru_timeout": 120,
            "mineru_extra_args": "--foo bar",
        }
    )

    command = runtime.build_command(pdf, out)

    assert command[:10] == [
        "mineru",
        "-p",
        str(pdf),
        "-o",
        str(out),
        "-b",
        "pipeline",
        "-m",
        "ocr",
        "-l",
    ]
    assert "latin" in command
    assert "--foo" in command


def test_mineru_runtime_forwards_contiguous_contexture_page_range(tmp_path):
    pdf = tmp_path / "sample.pdf"
    out = tmp_path / "out"
    pdf.write_bytes(b"%PDF-1.4\n")
    runtime = MineruCliLayoutRuntime(
        {
            "mineru_output_dir": str(out),
            "page_range": [2, 3, 4],
        }
    )

    command = runtime.build_command(pdf, out)

    assert command[command.index("-s") + 1] == "2"
    assert command[command.index("-e") + 1] == "4"


def test_mineru_runtime_does_not_forward_noncontiguous_page_range(tmp_path):
    pdf = tmp_path / "sample.pdf"
    out = tmp_path / "out"
    pdf.write_bytes(b"%PDF-1.4\n")
    runtime = MineruCliLayoutRuntime(
        {
            "mineru_output_dir": str(out),
            "page_range": [2, 4],
        }
    )

    command = runtime.build_command(pdf, out)

    assert "-s" not in command
    assert "-e" not in command


def test_mineru_runtime_finds_expected_middle_json(tmp_path):
    pdf = tmp_path / "sample.pdf"
    out = tmp_path / "out"
    middle = out / "sample" / "txt" / "sample_middle.json"
    pdf.write_bytes(b"%PDF-1.4\n")
    middle.parent.mkdir(parents=True)
    middle.write_text('{"pdf_info": []}', encoding="utf-8")
    runtime = MineruCliLayoutRuntime(
        {"mineru_output_dir": str(out), "mineru_method": "txt"}
    )

    assert runtime.find_middle_json(out, pdf) == middle


def test_mineru_runtime_run_uses_runner_and_returns_middle_json(tmp_path):
    command_path = tmp_path / "mineru.exe"
    command_path.write_text("", encoding="utf-8")
    pdf = tmp_path / "sample.pdf"
    out = tmp_path / "out"
    middle = out / "sample" / "txt" / "sample_middle.json"
    pdf.write_bytes(b"%PDF-1.4\n")

    seen = {}

    def fake_runner(command, **kwargs):
        seen["env"] = kwargs.get("env")
        middle.parent.mkdir(parents=True)
        middle.write_text('{"pdf_info": []}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    runtime = MineruCliLayoutRuntime(
        {
            "mineru_command": str(command_path),
            "mineru_output_dir": str(out),
            "mineru_method": "txt",
        },
        runner=fake_runner,
    )

    result = runtime.run(pdf)

    assert result.middle_json_path == middle
    assert result.stdout == "ok"
    assert seen["env"]["MINERU_MODEL_SOURCE"] == "modelscope"
    assert seen["env"]["PYTHONUTF8"] == "1"
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"


def test_mineru_runtime_respects_explicit_env_overrides():
    runtime = MineruCliLayoutRuntime(
        {
            "mineru_env": {
                "MINERU_MODEL_SOURCE": "local",
                "PYTHONIOENCODING": "gbk",
            }
        }
    )

    env = runtime._subprocess_env()

    assert env["MINERU_MODEL_SOURCE"] == "local"
    assert env["PYTHONIOENCODING"] == "gbk"
    assert env["PYTHONUTF8"] == "1"


def test_mineru_command_defaults_to_contexture_env(monkeypatch):
    monkeypatch.setenv("CONTEXTURE_MINERU_COMMAND", r"C:\tools\mineru.exe")

    assert default_mineru_command() == r"C:\tools\mineru.exe"
    assert MineruCliLayoutRuntime({}).command_name == r"C:\tools\mineru.exe"


def test_venv_executable_uses_posix_bin(tmp_path):
    assert venv_executable(tmp_path / ".venv", "python", os_name="posix") == tmp_path / ".venv" / "bin" / "python"
    assert venv_executable(tmp_path / ".venv", "mineru", os_name="posix") == tmp_path / ".venv" / "bin" / "mineru"


def test_venv_executable_uses_windows_scripts(tmp_path):
    assert venv_executable(tmp_path / ".venv", "python", os_name="nt") == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert venv_executable(tmp_path / ".venv", "mineru.exe", os_name="nt") == tmp_path / ".venv" / "Scripts" / "mineru.exe"
