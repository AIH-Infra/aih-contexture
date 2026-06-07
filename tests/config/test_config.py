import sys
from contextlib import suppress
import click

from aih_contexture.config.printer import CustomClickPrinter
from aih_contexture.config.crawler import ConfigCrawler, crawler
from aih_contexture.config.parser import ConfigParser


def capture_kwargs(argv):
    command = click.command(cls=CustomClickPrinter)
    captured_kwargs = {}

    def parse_args(**kwargs):
        captured_kwargs.update(kwargs)
        return kwargs

    original_argv = sys.argv
    sys.argv = argv
    try:
        with suppress(SystemExit):
            command(ConfigParser.common_options(parse_args))()
    finally:
        sys.argv = original_argv

    return captured_kwargs


def test_config_parser():
    sys.argv = [
        "test",
        "--disable_multiprocessing",
        "--output_dir",
        "output_dir",
        "--height_tolerance",
        "0.5",
    ]
    kwargs = capture_kwargs(sys.argv)
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    # Validate kwarg capturing
    assert kwargs["disable_multiprocessing"]
    assert kwargs["output_dir"] == "output_dir"

    assert config_dict["pdftext_workers"] == 1  # disabling multiprocessing does this
    assert config_dict["height_tolerance"] == 0.5


def test_config_none():
    kwargs = capture_kwargs(["test"])
    def noop(**kwargs):
        return kwargs

    explicit_command = click.command()(ConfigParser.common_options(noop))
    explicit_options = {
        param.name
        for param in explicit_command.params
        if getattr(param, "name", None)
    }

    for key in crawler.attr_set:
        if key in explicit_options:
            continue
        # We force some options to become flags for ease of use on the CLI
        value = None
        assert kwargs.get(key) is value


def test_config_llm():
    kwargs = capture_kwargs(["test", "--use_llm"])
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    # Validate kwarg capturing
    assert config_dict["use_llm"]


def test_config_force_ocr():
    kwargs = capture_kwargs(["test", "--force_ocr"])
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    # Validate kwarg capturing
    assert config_dict["force_ocr"]


def test_config_selected_tesseract_backend_uses_shared_line_builder_by_default():
    kwargs = capture_kwargs(["test", "--ocr_backend", "tesseract"])
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    assert config_dict["ocr_backend"] == "tesseract"
    assert config_dict["force_ocr"] is True
    assert config_dict["disable_ocr"] is False
    assert "ocr_line_source" not in config_dict


def test_config_selected_calamari_backend_uses_tesseract_line_source():
    kwargs = capture_kwargs(["test", "--ocr_backend", "calamari"])
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    assert config_dict["ocr_backend"] == "calamari"
    assert config_dict["force_ocr"] is True
    assert config_dict["disable_ocr"] is False
    assert config_dict["ocr_line_source"] == "tesseract"


def test_config_all_selected_ocr_backends_force_ocr():
    for backend in ["surya", "calamari", "paddle_ocr_v5", "paddleocr_vl_ocr", "tesseract", "vlm_ocr"]:
        kwargs = capture_kwargs(["test", "--ocr_backend", backend])
        parser = ConfigParser(kwargs)
        config_dict = parser.generate_config_dict()

        assert config_dict["ocr_backend"] == backend
        assert config_dict["disable_ocr"] is False
        assert config_dict["force_ocr"] is True


def test_config_none_ocr_backend_uses_embedded_text_layer():
    kwargs = capture_kwargs(["test", "--ocr_backend", "none"])
    parser = ConfigParser(kwargs)
    config_dict = parser.generate_config_dict()

    assert config_dict["disable_ocr"] is True
    assert config_dict["force_ocr"] is False


def test_config_crawler_formats_deferred_annotations():
    assert ConfigCrawler._format_type("str | None") == "str | None"
