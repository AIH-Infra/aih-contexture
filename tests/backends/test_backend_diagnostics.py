import subprocess
import builtins
from urllib.error import HTTPError

from aih_contexture.backends.diagnostics import layout_backend_status, ocr_backend_status, vlm_backend_status


def test_external_sidecar_status_is_available_without_runtime_dependency():
    status = layout_backend_status("external_layout_sidecar")

    assert status.available is True
    assert status.level == "ok"


def test_mineru_status_reports_missing_command(tmp_path):
    status = layout_backend_status(
        "mineru_pp_doclayout_v2",
        config={"mineru_command": str(tmp_path / "missing-mineru")},
    )

    assert status.available is False
    assert status.level == "missing_dependency"
    assert "MinerU CLI" in status.message


def test_planned_backend_status_is_not_available():
    status = layout_backend_status("humanities_layout_future")

    assert status.available is False
    assert status.level == "planned"

    ocr_status = ocr_backend_status("mineru_pytorch_paddle_ocr")
    assert ocr_status.available is False
    assert ocr_status.level == "planned"



def test_service_backends_report_configuration_requirement():
    layout_status = layout_backend_status("vlm_layout")
    ocr_status = ocr_backend_status("vlm_ocr")
    paddle_vl_ocr_status = ocr_backend_status("paddleocr_vl_ocr")
    vlm_status = vlm_backend_status("vlm_generalized")
    paddle_vl_status = vlm_backend_status("paddleocr_vl")
    mineru_vl_status = vlm_backend_status("mineru_vl")

    assert layout_status.level == "requires_configuration"
    assert ocr_status.level == "requires_configuration"
    assert paddle_vl_ocr_status.level == "requires_configuration"
    assert vlm_status.level == "requires_configuration"
    assert paddle_vl_status.level == "requires_configuration"
    assert mineru_vl_status.level == "requires_configuration"


def test_service_backends_do_not_probe_network_by_default(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network probe should not run by default")

    monkeypatch.setattr("aih_contexture.backends.diagnostics.request.urlopen", fail_urlopen)

    status = ocr_backend_status("calamari", config={"calamari_base_url": "http://127.0.0.1:9"})

    assert status.available is True
    assert status.level == "requires_configuration"


def test_calamari_status_can_probe_health_endpoint(monkeypatch):
    seen = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("aih_contexture.backends.diagnostics.request.urlopen", fake_urlopen)

    status = ocr_backend_status(
        "calamari",
        config={
            "probe_services": True,
            "calamari_base_url": "http://127.0.0.1:11800",
            "backend_health_timeout": 1.5,
        },
    )

    assert status.available is True
    assert status.level == "ok"
    assert seen == {"url": "http://127.0.0.1:11800/health", "timeout": 1.5}


def test_openai_compatible_probe_reports_auth_configuration(monkeypatch):
    def fake_urlopen(req, timeout):
        raise HTTPError(req.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("aih_contexture.backends.diagnostics.request.urlopen", fake_urlopen)

    status = ocr_backend_status(
        "vlm_ocr",
        config={"probe_services": True, "openai_base_url": "http://127.0.0.1:1234/v1"},
    )

    assert status.available is False
    assert status.level == "requires_configuration"
    assert status.details["url"] == "http://127.0.0.1:1234/v1/models"


def test_vlm_probe_without_endpoint_requires_configuration():
    status = vlm_backend_status("vlm_generalized", config={"probe_services": True})

    assert status.available is False
    assert status.level == "requires_configuration"


def test_paddle_status_can_check_external_sidecar_python(monkeypatch, tmp_path):
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")

    def fake_run(command, **kwargs):
        assert command[0] == str(python)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"paddle": "3.3.0", "cuda": true, "device": "gpu:0"}\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    status = layout_backend_status(
        "paddle_pp_doclayout_v3",
        config={"paddle_python": str(python)},
    )

    assert status.available is True
    assert status.level == "ok"
    assert status.details["cuda"] is True
    assert status.details["device"] == "gpu:0"


def test_paddle_status_reports_missing_external_sidecar_python(tmp_path):
    status = ocr_backend_status(
        "paddle_ocr_v5",
        config={"paddle_python": str(tmp_path / "missing-python.exe")},
    )

    assert status.available is False
    assert status.level == "missing_dependency"
    assert "does not exist" in status.message


def test_tesseract_status_reports_import_failure(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "aih_contexture.services.ocr_tesseract":
            raise ModuleNotFoundError("No module named 'pydantic_settings'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    status = ocr_backend_status("tesseract")

    assert status.available is False
    assert status.level == "missing_dependency"
    assert "Tesseract diagnostic import failed" in status.message
