"""Offline reading export from the project's native Pipeline JSON tree."""
from pathlib import Path
import json

import click

from aih_contexture.middle.adapters.pipeline_json import pipeline_json_to_middle_document
from aih_contexture.runtime.artifacts import save_middle_json_artifacts
from aih_contexture.middle.reading_structure import copy_existing_reading_resources
from aih_contexture.scripts.reading_import_contract import GENERIC_LINE_HELP


@click.command(help='Import a recorded Contexture Pipeline render-tree JSON without OCR or model calls.')
@click.argument('json_path',type=click.Path(exists=True,dir_okay=False,path_type=Path))
@click.option('--output-dir',required=True,type=click.Path(file_okay=False,path_type=Path))
@click.option('--classical-marginalia-mode',type=click.Choice(['off','page_locators']),default=None)
@click.option('--classical-text-marginalia-mode',type=click.Choice(['separate','drop']),default=None)
@click.option('--generic-line-output-mode',type=click.Choice(['drop','page_comments']),default=None,help=GENERIC_LINE_HELP)
@click.option('--reading-diagnostics', 'emit_reading_diagnostics', is_flag=True, default=False)
def import_pipeline_json_cli(json_path,output_dir,classical_marginalia_mode,classical_text_marginalia_mode,generic_line_output_mode=None,emit_reading_diagnostics=False):
    try:
        data=json.loads(json_path.read_text(encoding='utf-8-sig'))
        middle=pipeline_json_to_middle_document(data,source_name=json_path.name,source_dir=json_path.parent)
        output_dir.mkdir(parents=True,exist_ok=True)
        copy_existing_reading_resources(middle,json_path.parent,output_dir)
        result=save_middle_json_artifacts(middle,str(output_dir),json_path.stem+'.pipeline_imported',
                emit_middle_scholarly=True,emit_reading_diagnostics=emit_reading_diagnostics,
                classical_marginalia_mode=classical_marginalia_mode,
                classical_text_marginalia_mode=classical_text_marginalia_mode,
                generic_line_output_mode=generic_line_output_mode)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    for name,path in result.items():
        click.echo(f'{name}: {path}')


if __name__=='__main__':
    import_pipeline_json_cli()
