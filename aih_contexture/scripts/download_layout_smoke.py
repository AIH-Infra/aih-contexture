from __future__ import annotations

import json
from pathlib import Path

import click
import requests


DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "evaluation" / "layout_smoke_sources.json"
DEFAULT_OUTPUT_DIR = Path("data") / "layout_smoke" / "downloads"


@click.command(help="Download the small online PDF set used for Contexture layout smoke evaluation.")
@click.option("--sources", type=click.Path(exists=True, dir_okay=False), default=str(DEFAULT_SOURCES), show_default=True)
@click.option("--output-dir", type=click.Path(file_okay=False), default=str(DEFAULT_OUTPUT_DIR), show_default=True)
@click.option("--manifest-output", type=click.Path(dir_okay=False), default=None, help="Write a contexture_eval_layout manifest template next to downloads.")
@click.option("--timeout", type=int, default=60, show_default=True)
@click.option("--force", is_flag=True, help="Redownload files that already exist.")
def download_layout_smoke_cli(
    sources: str,
    output_dir: str,
    manifest_output: str | None,
    timeout: int,
    force: bool,
):
    source_path = Path(sources)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    downloaded = []
    manifest_cases = []
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        file_path = output_path / str(source["filename"])
        if file_path.exists() and not force:
            click.echo(f"[skip] {file_path}")
        else:
            _download(source["url"], file_path, timeout=timeout)
            click.echo(f"[ok] {file_path} ({file_path.stat().st_size} bytes)")
        downloaded.append(str(file_path))
        manifest_cases.append(
            {
                "id": source.get("id"),
                "path": str(file_path),
                "backend": ",".join(source.get("backend_targets", [])),
                "document_type": source.get("document_type"),
                "required_block_types": source.get("required_block_types", []),
                "notes": source.get("notes"),
            }
        )

    manifest = {
        "name": "contexture-layout-smoke-downloaded",
        "version": 1,
        "min_blocks": 1,
        "cases": manifest_cases,
    }
    if manifest_output:
        manifest_path = Path(manifest_output)
    else:
        manifest_path = output_path.parent / "downloaded_layout_manifest.template.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"[manifest] {manifest_path}")
    click.echo(json.dumps({"downloaded": downloaded, "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


def _download(url: str, file_path: Path, *, timeout: int) -> None:
    headers = {"User-Agent": "aih-contexture-layout-smoke/0.3"}
    with requests.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            raise click.ClickException(f"Downloaded content does not look like a PDF: {url} ({content_type})")
        tmp_path = file_path.with_suffix(file_path.suffix + ".part")
        with tmp_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    output.write(chunk)
        tmp_path.replace(file_path)


if __name__ == "__main__":
    download_layout_smoke_cli()
