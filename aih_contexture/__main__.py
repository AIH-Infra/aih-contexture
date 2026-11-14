from __future__ import annotations

import importlib
import sys

from aih_contexture import __version__

COMMANDS: dict[str, tuple[str, str]] = {
    "convert": ("aih_contexture.scripts.convert", "convert_cli"),
    "convert-single": ("aih_contexture.scripts.convert_single", "convert_single_cli"),
    "chunk": ("aih_contexture.scripts.chunk_convert", "chunk_convert_cli"),
    "doctor": ("aih_contexture.scripts.doctor", "doctor_cli"),
    "backends": ("aih_contexture.scripts.backends", "backends_cli"),
    "middle": ("aih_contexture.scripts.middle", "middle_cli"),
    "gui": ("aih_contexture.scripts.run_streamlit_app", "streamlit_app_cli"),
    "extract": ("aih_contexture.scripts.run_streamlit_app", "extraction_app_cli"),
    "server": ("aih_contexture.scripts.server", "server_cli"),
    "structured-source": ("aih_contexture.scripts.structured_source", "structured_source_cli"),
    "validate-source": ("aih_contexture.scripts.structured_source", "validate_source_package_cli"),
    "text-layer-batch": ("aih_contexture.scripts.text_layer_batch", "text_layer_batch_cli"),
    "text-layer-audit": ("aih_contexture.scripts.text_layer_audit", "text_layer_audit_cli"),
}


HELP = """AIH-Contexture agent CLI

Use the instance conda interpreter, not Scripts\\contexture*.exe:

  python -m aih_contexture doctor
  python -m aih_contexture convert <input_dir> --output_dir <out>
  python -m aih_contexture convert-single <file.pdf> --output_dir <out>
  python -m aih_contexture convert-single <file.pdf> --layout_backend none --ocr_backend none

Python API:

  from aih_contexture.api import convert_file, doctor
  convert_file(r'C:\\doc.pdf', output_dir=r'D:\\out')

Commands:
  convert            Folder of PDFs
  convert-single     One PDF/image
  doctor             Backend readiness
  backends           Backend catalog
  gui                Streamlit UI
  server             FastAPI server
  structured-source  TEI/EPUB import
  validate-source    Source package check
  middle             Middle JSON tools
  chunk              Chunked folder convert
  extract            Extraction UI
  text-layer-batch   Text-layer batch
  text-layer-audit   Text-layer audit
"""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        sys.stdout.write(HELP)
        return 0
    if args[0] in {"-V", "--version"}:
        sys.stdout.write(f"aih-contexture {__version__}\n")
        return 0

    name = args[0]
    spec = COMMANDS.get(name)
    if spec is None:
        sys.stderr.write(f"unknown command: {name}\n\n")
        sys.stdout.write(HELP)
        return 2

    module_name, attr = spec
    cli = getattr(importlib.import_module(module_name), attr)
    sys.argv = [f"aih-contexture {name}", *args[1:]]
    try:
        import click
    except Exception:
        click = None
    if click is not None and isinstance(cli, click.Command):
        cli.main(args=args[1:], prog_name=f"aih-contexture {name}")
    else:
        cli()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
