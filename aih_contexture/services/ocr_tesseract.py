from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass(frozen=True, slots=True)
class TesseractCommandInfo:
    command: str
    version: str | None = None
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class TesseractLineResult:
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float | None = None


class TesseractNotFoundError(RuntimeError):
    pass


class TesseractOcrService:
    """Small subprocess wrapper around a system Tesseract executable."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.tesseract_cmd = str(self.config.get("tesseract_cmd") or "").strip() or None
        self.tesseract_lang = str(self.config.get("tesseract_lang") or "eng")
        self.tesseract_oem = int(self.config.get("tesseract_oem", 1))
        self.tesseract_psm = int(self.config.get("tesseract_psm", 7))
        self.tesseract_timeout = int(self.config.get("tesseract_timeout", 30))
        self.tesseract_omp_thread_limit = int(self.config.get("tesseract_omp_thread_limit", 1))
        self.tesseract_tessdata_prefix = str(self.config.get("tesseract_tessdata_prefix") or "").strip() or None
        self.tesseract_user_words = str(self.config.get("tesseract_user_words") or "").strip() or None
        self.tesseract_user_patterns = str(self.config.get("tesseract_user_patterns") or "").strip() or None
        self.tesseract_extra_config = str(self.config.get("tesseract_extra_config") or "").strip()
        self._command_info: TesseractCommandInfo | None = None

    def resolve_command(self) -> TesseractCommandInfo:
        if self._command_info is not None:
            return self._command_info

        for command, source in iter_tesseract_candidates(self.tesseract_cmd):
            version = _tesseract_version(command)
            if version is not None:
                self._command_info = TesseractCommandInfo(command=command, version=version, source=source)
                return self._command_info

        raise TesseractNotFoundError(
            "Tesseract executable was not found. Set tesseract_cmd, "
            "CONTEXTURE_TESSERACT_CMD, or add tesseract to PATH."
        )

    def get_version(self) -> str:
        return self.resolve_command().version or ""

    def list_languages(self) -> list[str]:
        command = self.resolve_command().command
        completed = subprocess.run(
            [command, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
            env=self._env(),
            check=False,
        )
        if completed.returncode != 0:
            return []
        languages: list[str] = []
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of available languages"):
                continue
            languages.append(line)
        return languages

    def validate_languages(self, lang_expr: str | None = None) -> tuple[bool, list[str], list[str]]:
        requested = parse_tesseract_languages(lang_expr or self.tesseract_lang)
        available = self.list_languages()
        if not available:
            return True, requested, []
        available_set = set(available)
        missing = [lang for lang in requested if lang not in available_set]
        return not missing, requested, missing

    def recognize_line(self, image: Image.Image, *, lang: str | None = None, psm: int | None = None) -> str:
        command = self.resolve_command().command
        lang = lang or self.tesseract_lang
        psm = int(psm if psm is not None else self.tesseract_psm)
        image_path = _make_service_temp_file("contexture-tesseract-line-", ".png")
        try:
            image.save(image_path)
            args = [
                command,
                str(image_path),
                "stdout",
                "-l",
                lang,
                "--oem",
                str(self.tesseract_oem),
                "--psm",
                str(psm),
            ]
            if self.tesseract_user_words:
                args.extend(["--user-words", self.tesseract_user_words])
            if self.tesseract_user_patterns:
                args.extend(["--user-patterns", self.tesseract_user_patterns])
            args.extend(_thresholding_args(self.config.get("tesseract_thresholding_method")))
            args.extend(_split_extra_config(self.tesseract_extra_config))

            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.tesseract_timeout,
                env=self._env(),
                check=False,
            )
        finally:
            _cleanup_service_temp_file(image_path)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Tesseract OCR failed").strip())
        return completed.stdout.strip()

    def recognize_lines(self, image: Image.Image, *, lang: str | None = None, psm: int | None = None) -> list[TesseractLineResult]:
        command = self.resolve_command().command
        lang = lang or self.tesseract_lang
        psm = int(psm if psm is not None else self.config.get("tesseract_line_psm", 6))
        image_path = _make_service_temp_file("contexture-tesseract-lines-", ".png")
        try:
            image.save(image_path)
            args = [
                command,
                str(image_path),
                "stdout",
                "-l",
                lang,
                "--oem",
                str(self.tesseract_oem),
                "--psm",
                str(psm),
                "tsv",
            ]
            if self.tesseract_user_words:
                args.extend(["--user-words", self.tesseract_user_words])
            if self.tesseract_user_patterns:
                args.extend(["--user-patterns", self.tesseract_user_patterns])
            args.extend(_thresholding_args(self.config.get("tesseract_thresholding_method")))
            args.extend(_split_extra_config(self.tesseract_extra_config))

            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.tesseract_timeout,
                env=self._env(),
                check=False,
            )
        finally:
            _cleanup_service_temp_file(image_path)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Tesseract line detection failed").strip())
        return parse_tesseract_tsv_lines(completed.stdout)

    def recognize_hocr_lines(
        self,
        image: Image.Image,
        *,
        lang: str | None = None,
        psm: int | None = None,
    ) -> list[TesseractLineResult]:
        command = self.resolve_command().command
        lang = lang or self.tesseract_lang
        psm = int(psm if psm is not None else self.config.get("tesseract_line_psm", 1))
        image_path = _make_service_temp_file("contexture-tesseract-hocr-lines-", ".png")
        try:
            image.save(image_path)
            args = [
                command,
                str(image_path),
                "stdout",
                "-l",
                lang,
                "--oem",
                str(self.tesseract_oem),
                "--psm",
                str(psm),
            ]
            if self.tesseract_user_words:
                args.extend(["--user-words", self.tesseract_user_words])
            if self.tesseract_user_patterns:
                args.extend(["--user-patterns", self.tesseract_user_patterns])
            args.extend(_thresholding_args(self.config.get("tesseract_thresholding_method")))
            args.extend(_split_extra_config(self.tesseract_extra_config))
            args.append("hocr")

            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.tesseract_timeout,
                env=self._env(),
                check=False,
            )
        finally:
            _cleanup_service_temp_file(image_path)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Tesseract hOCR line detection failed").strip())
        return parse_tesseract_hocr_lines(completed.stdout)

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.tesseract_omp_thread_limit > 0:
            env["OMP_THREAD_LIMIT"] = str(self.tesseract_omp_thread_limit)
        if self.tesseract_tessdata_prefix:
            env["TESSDATA_PREFIX"] = self.tesseract_tessdata_prefix
        return env


def parse_tesseract_languages(lang_expr: str) -> list[str]:
    return [part.strip() for part in str(lang_expr or "").split("+") if part.strip()]


def parse_tesseract_tsv_lines(tsv_text: str) -> list[TesseractLineResult]:
    rows = [line.split("\t") for line in (tsv_text or "").splitlines() if line.strip()]
    if not rows:
        return []
    header = rows[0]
    index = {name: idx for idx, name in enumerate(header)}
    required = {"level", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf", "text"}
    if not required.issubset(index):
        return []

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        if row[index["level"]] != "5":
            continue
        text = row[index["text"]].strip()
        if not text:
            continue
        try:
            left = int(float(row[index["left"]]))
            top = int(float(row[index["top"]]))
            width = int(float(row[index["width"]]))
            height = int(float(row[index["height"]]))
        except ValueError:
            continue
        if width <= 0 or height <= 0:
            continue

        key = (row[index["block_num"]], row[index["par_num"]], row[index["line_num"]])
        entry = grouped.setdefault(
            key,
            {
                "texts": [],
                "bbox": [left, top, left + width, top + height],
                "conf": [],
            },
        )
        entry["texts"].append(text)
        entry["bbox"][0] = min(entry["bbox"][0], left)
        entry["bbox"][1] = min(entry["bbox"][1], top)
        entry["bbox"][2] = max(entry["bbox"][2], left + width)
        entry["bbox"][3] = max(entry["bbox"][3], top + height)
        try:
            conf = float(row[index["conf"]])
            if conf >= 0:
                entry["conf"].append(conf)
        except ValueError:
            pass

    results: list[TesseractLineResult] = []
    for entry in grouped.values():
        text = " ".join(entry["texts"]).strip()
        if not text:
            continue
        conf_values = entry["conf"]
        confidence = sum(conf_values) / len(conf_values) if conf_values else None
        x0, y0, x1, y1 = entry["bbox"]
        results.append(TesseractLineResult(text=text, bbox=(x0, y0, x1, y1), confidence=confidence))
    results.sort(key=lambda item: (item.bbox[1], item.bbox[0], item.bbox[3], item.bbox[2]))
    return results


class _HocrLineParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[TesseractLineResult] = []
        self._active: dict[str, Any] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if self._active is None and tag.lower() == "span" and "ocr_line" in classes:
            bbox = _parse_hocr_bbox(attr_map.get("title", ""))
            if bbox is None:
                return
            self._active = {"bbox": bbox, "texts": [], "conf": _parse_hocr_confidence(attr_map.get("title", ""))}
            self._depth = 1
            return
        if self._active is not None:
            self._depth += 1

    def handle_data(self, data: str) -> None:
        if self._active is not None and data:
            self._active["texts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = re.sub(r"\s+", " ", unescape(" ".join(self._active["texts"]))).strip()
        if text:
            self.lines.append(
                TesseractLineResult(
                    text=text,
                    bbox=self._active["bbox"],
                    confidence=self._active["conf"],
                )
            )
        self._active = None
        self._depth = 0


def parse_tesseract_hocr_lines(hocr_text: str) -> list[TesseractLineResult]:
    parser = _HocrLineParser()
    parser.feed(hocr_text or "")
    parser.close()
    # hOCR already carries Tesseract's page/region reading order. Sorting by
    # y/x here can scramble multi-column pages, which is exactly the case where
    # Tesseract's full-page segmentation is more useful than per-block TSV.
    return parser.lines


def _parse_hocr_bbox(title: str) -> tuple[int, int, int, int] | None:
    match = re.search(r"\bbbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", title or "")
    if not match:
        return None
    return tuple(map(int, match.groups()))


def _parse_hocr_confidence(title: str) -> float | None:
    match = re.search(r"\bx_wconf\s+([0-9.]+)", title or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def iter_tesseract_candidates(explicit_command: str | None = None) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    if explicit_command:
        candidates.append((explicit_command, "config"))

    env_command = os.environ.get("CONTEXTURE_TESSERACT_CMD")
    if env_command:
        candidates.append((env_command, "CONTEXTURE_TESSERACT_CMD"))

    for command_name in ("tesseract", "tesseract.exe"):
        found = shutil.which(command_name)
        if found:
            candidates.append((found, "PATH"))

    candidates.extend(_platform_tesseract_candidates())

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for command, source in candidates:
        key = str(command).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append((str(command), source))
    return unique


def _platform_tesseract_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA")
        candidates.extend(
            [
                (r"C:\Program Files\Tesseract-OCR\tesseract.exe", "common_windows_path"),
                (r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe", "common_windows_path"),
                (r"D:\Soft\Tesseract-OCR\tesseract.exe", "common_windows_path"),
                (str(Path.cwd() / ".tesseract" / "tesseract.exe"), "local_portable_path"),
                (str(Path.cwd() / "tools" / "tesseract" / "tesseract.exe"), "local_portable_path"),
            ]
        )
        if localappdata:
            candidates.append((str(Path(localappdata) / "Programs" / "Tesseract-OCR" / "tesseract.exe"), "common_windows_path"))
    else:
        candidates.extend(
            [
                ("/usr/bin/tesseract", "common_unix_path"),
                ("/usr/local/bin/tesseract", "common_unix_path"),
                ("/opt/homebrew/bin/tesseract", "common_unix_path"),
            ]
        )
    return candidates


def _tesseract_version(command: str) -> str | None:
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    first_line = (completed.stdout or completed.stderr).splitlines()
    return first_line[0].strip() if first_line else ""


def _split_extra_config(value: str) -> list[str]:
    if not value:
        return []
    # Advanced escape hatch. Keep splitting simple and predictable for now.
    return [part for part in value.split() if part]


def _thresholding_args(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    mapping = {
        "auto": 0,
        "otsu": 0,
        "adaptive_otsu": 1,
        "adaptive-otsu": 1,
        "sauvola": 2,
    }
    if isinstance(value, str):
        key = value.strip().lower()
        if key in {"", "auto"}:
            return []
        method = mapping.get(key)
        if method is None:
            return []
    else:
        try:
            method = int(value)
        except (TypeError, ValueError):
            return []
        if method == 0:
            return []
    return ["-c", f"thresholding_method={method}"]


def _service_temp_root() -> str:
    root = Path(os.environ.get("CONTEXTURE_TEMP_DIR") or (Path.cwd() / ".contexture_tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _make_service_temp_file(prefix: str, suffix: str) -> Path:
    root = Path(_service_temp_root())
    for _ in range(100):
        path = root / f"{prefix}{uuid.uuid4().hex}{suffix}"
        if not path.exists():
            return path
    raise RuntimeError("Could not create a unique Tesseract temporary file")


def _cleanup_service_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
