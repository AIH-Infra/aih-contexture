from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from urllib import error, request
from urllib.parse import urlparse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from aih_contexture.backends.external_config import default_mineru_command, default_mineru_python, default_paddle_python
from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry
from aih_contexture.backends.vlm import default_vlm_registry

BackendStatusLevel = Literal["ok", "missing_dependency", "requires_configuration", "planned", "unknown"]


@dataclass(frozen=True, slots=True)
class BackendStatus:
    name: str
    available: bool
    level: BackendStatusLevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def layout_backend_status(name: str, config: dict[str, Any] | None = None) -> BackendStatus:
    config = config or {}
    spec = default_layout_registry.get(name)
    capabilities = spec.capabilities
    if not capabilities.implemented:
        return BackendStatus(
            name=spec.name,
            available=False,
            level="planned",
            message=f"Layout backend '{spec.name}' is declared but not implemented yet.",
        )

    match spec.name:
        case "surya":
            return _module_status("surya", spec.name, "Surya Python package is required for the default layout backend.")
        case "external_layout_sidecar":
            return BackendStatus(
                name=spec.name,
                available=True,
                level="ok",
                message="No runtime dependency is required; this backend consumes an existing JSON sidecar.",
            )
        case "mineru_pp_doclayout_v2":
            command = str(config.get("mineru_command") or default_mineru_command())
            found = _command_exists(command)
            return BackendStatus(
                name=spec.name,
                available=found,
                level="ok" if found else "missing_dependency",
                message=(
                    f"MinerU command is available: {command}"
                    if found
                    else "MinerU CLI is not available. Install MinerU or set 'mineru_command' to the executable path."
                ),
                details={"command": command},
            )
        case "mineru_pp_doclayout_v2_direct":
            python = str(config.get("mineru_layout_python") or config.get("mineru_python") or default_mineru_python() or "")
            if not python:
                return BackendStatus(
                    name=spec.name,
                    available=False,
                    level="requires_configuration",
                    message="MinerU direct layout requires a MinerU Python interpreter. Set mineru_layout_python or CONTEXTURE_MINERU_PYTHON.",
                )
            return _mineru_python_status(python, spec.name)
        case "paddle_pp_doclayout_plus_l" | "paddle_pp_doclayout_v3":
            return _paddle_status(
                spec.name,
                config=config,
                python_key="paddle_layout_python",
                missing_message=f"PaddleOCR is required for {spec.name}.",
            )
        case "vlm_layout":
            if _probe_services(config):
                endpoint = config.get("vlm_layout_base_url") or config.get("openai_base_url")
                return _openai_compatible_service_status(
                    spec.name,
                    endpoint=endpoint,
                    missing_message="VLM layout requires vlm_layout_base_url or openai_base_url before it can be probed.",
                    timeout=_health_timeout(config),
                )
            return BackendStatus(
                name=spec.name,
                available=True,
                level="requires_configuration",
                message="VLM layout requires a reachable OpenAI-compatible endpoint configured at runtime.",
            )
        case _:
            return BackendStatus(
                name=spec.name,
                available=True,
                level="unknown",
                message="No dependency diagnostic is defined for this layout backend.",
            )


def ocr_backend_status(name: str, config: dict[str, Any] | None = None) -> BackendStatus:
    config = config or {}
    spec = default_ocr_registry.get(name)
    capabilities = spec.capabilities
    if not capabilities.implemented:
        return BackendStatus(
            name=spec.name,
            available=False,
            level="planned",
            message=f"OCR backend '{spec.name}' is declared but not implemented yet.",
        )

    match spec.name:
        case "surya":
            return _module_status("surya", spec.name, "Surya Python package is required for Surya OCR.")
        case "calamari":
            if _probe_services(config):
                base_url = config.get("calamari_base_url") or "http://localhost:11800"
                return _http_service_status(
                    spec.name,
                    urls=[f"{str(base_url).rstrip('/')}/health"],
                    timeout=_health_timeout(config),
                    missing_message=f"Calamari service is not reachable at {base_url}.",
                )
            return BackendStatus(
                name=spec.name,
                available=True,
                level="requires_configuration",
                message="Calamari OCR requires a reachable Calamari service configured at runtime.",
            )
        case "vlm_ocr":
            if _probe_services(config):
                endpoint = config.get("openai_base_url") or config.get("ocr_endpoint")
                return _openai_compatible_service_status(
                    spec.name,
                    endpoint=endpoint,
                    missing_message="VLM OCR requires openai_base_url or ocr_endpoint before it can be probed.",
                    timeout=_health_timeout(config),
                )
            return BackendStatus(
                name=spec.name,
                available=True,
                level="requires_configuration",
                message="VLM OCR requires a reachable OpenAI-compatible endpoint configured at runtime.",
            )
        case "paddleocr_vl_ocr":
            if _probe_services(config):
                endpoint = (
                    config.get("paddleocr_vl_layout_parsing_url")
                    or config.get("paddleocr_vl_endpoint")
                    or config.get("ocr_endpoint")
                    or config.get("openai_base_url")
                )
                return _vlm_or_service_endpoint_status(
                    spec.name,
                    endpoint=endpoint,
                    missing_message="PaddleOCR-VL OCR requires paddleocr_vl_endpoint, ocr_endpoint, or openai_base_url before it can be probed.",
                    timeout=_health_timeout(config),
                )
            return BackendStatus(
                name=spec.name,
                available=True,
                level="requires_configuration",
                message="PaddleOCR-VL OCR requires a reachable PaddleOCR-VL/OpenAI-compatible vision endpoint configured at runtime.",
            )
        case "paddle_ocr_v5":
            return _paddle_status(
                spec.name,
                config=config,
                python_key="paddle_ocr_python",
                missing_message="PaddleOCR is required for PaddleOCR PP-OCRv5.",
            )
        case "tesseract":
            return _tesseract_status(spec.name, config=config)
        case _:
            return BackendStatus(
                name=spec.name,
                available=True,
                level="unknown",
                message="No dependency diagnostic is defined for this OCR backend.",
            )


def vlm_backend_status(name: str, config: dict[str, Any] | None = None) -> BackendStatus:
    config = config or {}
    spec = default_vlm_registry.get(name)
    capabilities = spec.capabilities
    if not capabilities.implemented:
        return BackendStatus(
            name=spec.name,
            available=False,
            level="planned",
            message=f"VLM backend '{spec.name}' is declared but not implemented yet.",
        )

    if _probe_services(config):
        endpoint = (
            config.get(f"{spec.name}_endpoint")
            or config.get(f"{spec.name}_base_url")
            or config.get("ocr_endpoint")
            or config.get("openai_base_url")
            or config.get("vlm_direct_base_url")
        )
        return _vlm_or_service_endpoint_status(
            spec.name,
            endpoint=endpoint,
            missing_message=f"VLM backend '{spec.name}' requires a service endpoint before it can be probed.",
            timeout=_health_timeout(config),
        )

    return BackendStatus(
        name=spec.name,
        available=True,
        level="requires_configuration",
        message=f"VLM backend '{spec.name}' requires a configured service or local model runtime.",
    )


def _paddle_status(
    backend_name: str,
    *,
    config: dict[str, Any],
    python_key: str,
    missing_message: str,
) -> BackendStatus:
    sidecar_python = (
        config.get(python_key)
        or config.get("paddle_python")
        or default_paddle_python()
    )
    if sidecar_python:
        return _paddle_sidecar_status(str(sidecar_python), backend_name)

    return _module_status(
        "paddleocr",
        backend_name,
        missing_message,
    )


def _paddle_sidecar_status(python: str, backend_name: str) -> BackendStatus:
    python_path = Path(python).expanduser()
    if any(separator in python for separator in ("/", "\\")) and not python_path.exists():
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"Paddle sidecar Python does not exist: {python}",
            details={"python": python},
        )

    command = [
        python,
        "-c",
        (
            "import json; "
            "import paddle, paddleocr; "
            "print(json.dumps({"
            "'paddle': paddle.__version__, "
            "'cuda': paddle.is_compiled_with_cuda(), "
            "'device': paddle.device.get_device()"
            "}))"
        ),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except Exception as exc:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"Paddle sidecar check failed: {exc}",
            details={"python": python},
        )

    if completed.returncode != 0:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message="Paddle sidecar Python is configured but cannot import paddle and paddleocr.",
            details={
                "python": python,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-1000:],
                "stderr": completed.stderr[-1000:],
            },
        )

    details: dict[str, Any] = {"python": python}
    try:
        details.update(json.loads(completed.stdout.strip().splitlines()[-1]))
    except Exception:
        details["stdout"] = completed.stdout[-1000:]
    return BackendStatus(
        name=backend_name,
        available=True,
        level="ok",
        message=f"Paddle sidecar Python is available: {python}",
        details=details,
    )


def _tesseract_status(backend_name: str, *, config: dict[str, Any]) -> BackendStatus:
    try:
        from aih_contexture.services.ocr_tesseract import TesseractNotFoundError, TesseractOcrService
    except Exception as exc:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"Tesseract diagnostic import failed: {exc}",
        )

    try:
        service = TesseractOcrService(config)
        info = service.resolve_command()
        languages = service.list_languages()
        lang_expr = str(config.get("tesseract_lang") or "eng")
        ok, requested, missing = service.validate_languages(lang_expr)
    except TesseractNotFoundError:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message="Tesseract executable is not available. Install Tesseract or set CONTEXTURE_TESSERACT_CMD.",
        )
    except Exception as exc:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"Tesseract diagnostic failed: {exc}",
        )

    details = {
        "command": info.command,
        "version": info.version,
        "source": info.source,
        "languages": languages,
        "requested_languages": requested,
        "missing_languages": missing,
    }
    if not ok:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="requires_configuration",
            message="Tesseract is available, but requested language packs are missing: " + ", ".join(missing),
            details=details,
        )
    return BackendStatus(
        name=backend_name,
        available=True,
        level="ok",
        message=f"Tesseract is available: {info.command}",
        details=details,
    )


def _mineru_python_status(python: str, backend_name: str) -> BackendStatus:
    python_path = Path(python).expanduser()
    if any(separator in python for separator in ("/", "\\")) and not python_path.exists():
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"MinerU sidecar Python does not exist: {python}",
            details={"python": python},
        )

    command = [
        python,
        "-c",
        (
            "import json; "
            "from mineru.model.layout.pp_doclayoutv2 import PPDocLayoutV2LayoutModel; "
            "from mineru.utils.config_reader import get_device; "
            "print(json.dumps({'device': get_device(), 'model': PPDocLayoutV2LayoutModel.__name__}))"
        ),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except Exception as exc:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message=f"MinerU sidecar check failed: {exc}",
            details={"python": python},
        )

    if completed.returncode != 0:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="missing_dependency",
            message="MinerU sidecar Python is configured but cannot import PPDocLayoutV2LayoutModel.",
            details={
                "python": python,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-1000:],
                "stderr": completed.stderr[-1000:],
            },
        )

    details: dict[str, Any] = {"python": python}
    try:
        details.update(json.loads(completed.stdout.strip().splitlines()[-1]))
    except Exception:
        details["stdout"] = completed.stdout[-1000:]
    return BackendStatus(
        name=backend_name,
        available=True,
        level="ok",
        message=f"MinerU sidecar Python is available: {python}",
        details=details,
    )


def _module_status(module_name: str, backend_name: str, missing_message: str) -> BackendStatus:
    found = importlib.util.find_spec(module_name) is not None
    return BackendStatus(
        name=backend_name,
        available=found,
        level="ok" if found else "missing_dependency",
        message=f"Python module '{module_name}' is importable." if found else missing_message,
        details={"module": module_name},
    )


def _command_exists(command: str) -> bool:
    if any(separator in command for separator in ("/", "\\")):
        return Path(command).expanduser().exists()
    return shutil.which(command) is not None


def _probe_services(config: dict[str, Any]) -> bool:
    return bool(config.get("probe_services") or config.get("backend_probe_services"))


def _health_timeout(config: dict[str, Any]) -> float:
    try:
        return float(config.get("backend_health_timeout") or config.get("health_timeout") or 3.0)
    except (TypeError, ValueError):
        return 3.0


def _openai_compatible_service_status(
    backend_name: str,
    *,
    endpoint: Any,
    missing_message: str,
    timeout: float,
) -> BackendStatus:
    if not endpoint:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="requires_configuration",
            message=missing_message,
        )
    return _http_service_status(
        backend_name,
        urls=[_openai_models_url(str(endpoint))],
        timeout=timeout,
        missing_message=f"OpenAI-compatible service is not reachable from endpoint: {endpoint}",
    )


def _vlm_or_service_endpoint_status(
    backend_name: str,
    *,
    endpoint: Any,
    missing_message: str,
    timeout: float,
) -> BackendStatus:
    if not endpoint:
        return BackendStatus(
            name=backend_name,
            available=False,
            level="requires_configuration",
            message=missing_message,
        )
    endpoint_text = str(endpoint).strip()
    if _looks_like_openai_endpoint(endpoint_text):
        return _openai_compatible_service_status(
            backend_name,
            endpoint=endpoint_text,
            missing_message=missing_message,
            timeout=timeout,
        )
    return _http_service_status(
        backend_name,
        urls=[endpoint_text, f"{endpoint_text.rstrip('/')}/health"],
        timeout=timeout,
        missing_message=f"Service endpoint is not reachable: {endpoint_text}",
        accept_reachable_status=True,
    )


def _http_service_status(
    backend_name: str,
    *,
    urls: list[str],
    timeout: float,
    missing_message: str,
    accept_reachable_status: bool = False,
) -> BackendStatus:
    attempts = []
    for url in urls:
        try:
            req = request.Request(url, method="GET", headers={"User-Agent": "AIH-Contexture/backend-diagnostics"})
            with request.urlopen(req, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                details = {"url": url, "status_code": status}
                if 200 <= status < 400:
                    return BackendStatus(
                        name=backend_name,
                        available=True,
                        level="ok",
                        message=f"Service endpoint is reachable: {url}",
                        details=details,
                    )
                attempts.append(details)
        except error.HTTPError as exc:
            details = {"url": url, "status_code": exc.code, "reason": str(exc.reason)}
            attempts.append(details)
            if exc.code in {401, 403}:
                return BackendStatus(
                    name=backend_name,
                    available=False,
                    level="requires_configuration",
                    message=f"Service endpoint is reachable but authentication/configuration is required: {url}",
                    details=details,
                )
            if accept_reachable_status and exc.code in {404, 405}:
                return BackendStatus(
                    name=backend_name,
                    available=True,
                    level="requires_configuration",
                    message=f"Service endpoint responded but may need method/path configuration: {url}",
                    details=details,
                )
        except Exception as exc:
            attempts.append({"url": url, "error": str(exc)})

    return BackendStatus(
        name=backend_name,
        available=False,
        level="missing_dependency",
        message=missing_message,
        details={"attempts": attempts},
    )


def _openai_models_url(endpoint: str) -> str:
    text = endpoint.strip().rstrip("/")
    if text.endswith("/chat/completions"):
        text = text[: -len("/chat/completions")]
    if not text.endswith("/v1"):
        text = f"{text}/v1"
    return f"{text}/models"


def _looks_like_openai_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    path = parsed.path.lower()
    return (
        path.endswith("/v1")
        or path.endswith("/v1/chat/completions")
        or "openai" in endpoint.lower()
        or "compatible" in endpoint.lower()
    )
