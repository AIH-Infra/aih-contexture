import subprocess

from PIL import Image

from aih_contexture.services.ocr_tesseract import (
    TesseractOcrService,
    iter_tesseract_candidates,
    parse_tesseract_hocr_lines,
    parse_tesseract_tsv_lines,
    parse_tesseract_languages,
)


def test_parse_tesseract_languages():
    assert parse_tesseract_languages("chi_sim+eng") == ["chi_sim", "eng"]
    assert parse_tesseract_languages(" eng + deu ") == ["eng", "deu"]


def test_iter_tesseract_candidates_prefers_explicit_and_env(monkeypatch):
    monkeypatch.setenv("CONTEXTURE_TESSERACT_CMD", r"C:\Tools\tesseract.exe")
    monkeypatch.setattr("shutil.which", lambda _name: None)

    candidates = iter_tesseract_candidates("custom-tesseract")

    assert candidates[0] == ("custom-tesseract", "config")
    assert candidates[1] == (r"C:\Tools\tesseract.exe", "CONTEXTURE_TESSERACT_CMD")


def test_service_resolves_version_and_languages(monkeypatch):
    def fake_run(command, **kwargs):
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.4.0\n", stderr="")
        if command[1] == "--list-langs":
            return subprocess.CompletedProcess(command, 0, stdout="List of available languages (2):\neng\ndeu\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = TesseractOcrService({"tesseract_cmd": "tesseract", "tesseract_lang": "eng+deu"})

    info = service.resolve_command()
    assert info.version == "tesseract 5.4.0"
    assert service.list_languages() == ["eng", "deu"]
    assert service.validate_languages() == (True, ["eng", "deu"], [])


def test_service_recognize_line_builds_expected_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.4.0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="Recognized text\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = TesseractOcrService(
        {
            "tesseract_cmd": "tesseract",
            "tesseract_lang": "eng",
            "tesseract_oem": 1,
            "tesseract_psm": 7,
            "tesseract_omp_thread_limit": 1,
        }
    )

    text = service.recognize_line(Image.new("RGB", (20, 10), "white"))

    assert text == "Recognized text"
    command = calls[-1][0]
    assert command[0] == "tesseract"
    assert command[2] == "stdout"
    assert command[3:] == ["-l", "eng", "--oem", "1", "--psm", "7"]
    assert calls[-1][1]["env"]["OMP_THREAD_LIMIT"] == "1"


def test_parse_tesseract_tsv_lines_groups_words_by_line():
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t8\t92\tHello",
            "5\t1\t1\t1\t1\t2\t45\t20\t35\t8\t88\tworld",
            "5\t1\t1\t1\t2\t1\t10\t40\t25\t8\t95\tNext",
        ]
    )

    lines = parse_tesseract_tsv_lines(tsv)

    assert [line.text for line in lines] == ["Hello world", "Next"]
    assert lines[0].bbox == (10, 20, 80, 28)
    assert round(lines[0].confidence, 1) == 90.0


def test_parse_tesseract_hocr_lines_preserves_hocr_reading_order():
    hocr = """
    <html><body>
      <div class="ocr_carea" title="bbox 300 10 500 80; x_reading_order 1">
        <span class="ocr_line" title="bbox 300 10 500 30; x_wconf 91">
          <span class="ocrx_word">Right</span> <span class="ocrx_word">column</span>
        </span>
      </div>
      <div class="ocr_carea" title="bbox 10 50 200 120; x_reading_order 2">
        <span class="ocr_line" title="bbox 10 50 200 70; x_wconf 88">Left lower</span>
      </div>
    </body></html>
    """

    lines = parse_tesseract_hocr_lines(hocr)

    assert [line.text for line in lines] == ["Right column", "Left lower"]
    assert lines[0].bbox == (300, 10, 500, 30)
    assert lines[0].confidence == 91


def test_service_recognize_lines_uses_tsv_and_line_psm(monkeypatch):
    calls = []
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t2\t3\t10\t5\t80\tLine",
        ]
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.4.0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=tsv, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = TesseractOcrService(
        {
            "tesseract_cmd": "tesseract",
            "tesseract_lang": "eng",
            "tesseract_line_psm": 6,
            "tesseract_thresholding_method": "sauvola",
        }
    )

    lines = service.recognize_lines(Image.new("RGB", (20, 10), "white"))

    assert [line.text for line in lines] == ["Line"]
    command = calls[-1][0]
    assert command[0] == "tesseract"
    assert command[-3:] == ["tsv", "-c", "thresholding_method=2"]
    assert command[command.index("--psm") + 1] == "6"


def test_service_recognize_hocr_lines_uses_hocr_and_page_psm(monkeypatch):
    calls = []
    hocr = """
    <html><body>
      <span class="ocr_line" title="bbox 2 3 12 8; x_wconf 80">Line</span>
    </body></html>
    """

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.4.0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=hocr, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = TesseractOcrService(
        {
            "tesseract_cmd": "tesseract",
            "tesseract_lang": "eng",
            "tesseract_line_psm": 1,
            "tesseract_thresholding_method": "sauvola",
        }
    )

    lines = service.recognize_hocr_lines(Image.new("RGB", (20, 10), "white"))

    assert [line.text for line in lines] == ["Line"]
    command = calls[-1][0]
    assert command[0] == "tesseract"
    assert command[-3:] == ["-c", "thresholding_method=2", "hocr"]
    assert command[command.index("--psm") + 1] == "1"
