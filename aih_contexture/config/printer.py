import sys
from typing import Any, get_args

import click

from aih_contexture.config.crawler import crawler


def _stdout_encodable_text(text: str) -> str:
    """Escape only characters the active stdout encoding cannot represent."""
    # Click's deprecated get_text_stream() can wrap the console as UTF-8 even
    # when click.echo ultimately writes through sys.stdout's legacy code page.
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        return text
    try:
        return text.encode(encoding, errors="backslashreplace").decode(encoding)
    except LookupError:
        return text


def _echo_help(text: str) -> None:
    click.echo(_stdout_encodable_text(text))


class CustomClickPrinter(click.Command):
    def get_help(self, ctx):
        return _stdout_encodable_text(super().get_help(ctx))

    def parse_args(self, ctx, args):
        display_help = "config" in args and "--help" in args
        if display_help:
            _echo_help(
                "Here is a list of all the Builders, Processors, Converters, Providers and Renderers in Marker along with their attributes:"
            )

        # Keep track of shared attributes and their types
        shared_attrs = {}
        existing_param_names = {param.name for param in ctx.command.params if getattr(param, "name", None)}

        # First pass: identify shared attributes and verify compatibility
        for base_type, base_type_dict in crawler.class_config_map.items():
            for class_name, class_map in base_type_dict.items():
                for attr, (attr_type, formatted_type, default, metadata) in class_map[
                    "config"
                ].items():
                    if attr not in shared_attrs:
                        shared_attrs[attr] = {
                            "classes": [],
                            "type": attr_type,
                            "is_flag": _click_type(attr_type) is bool and not default,
                            "metadata": metadata,
                            "default": default,
                        }
                    shared_attrs[attr]["classes"].append(class_name)

        # Add shared attribute options first
        for attr, info in shared_attrs.items():
            if attr in existing_param_names:
                continue
            option_type = _click_type(info["type"])
            if option_type is not None:
                ctx.command.params.append(
                    click.Option(
                        ["--" + attr],
                        type=option_type,
                        help=" ".join(info["metadata"])
                        + f" (Applies to: {', '.join(info['classes'])})",
                        default=None,  # This is important, or it sets all the default keys again in config
                        is_flag=info["is_flag"],
                        flag_value=True if info["is_flag"] else None,
                    )
                )

        # Second pass: create class-specific options
        for base_type, base_type_dict in crawler.class_config_map.items():
            if display_help:
                _echo_help(f"{base_type}s:")
            for class_name, class_map in base_type_dict.items():
                if display_help and class_map["config"]:
                    _echo_help(
                        f"\n  {class_name}: {class_map['class_type'].__doc__ or ''}"
                    )
                    _echo_help(" " * 4 + "Attributes:")
                for attr, (attr_type, formatted_type, default, metadata) in class_map[
                    "config"
                ].items():
                    class_name_attr = class_name + "_" + attr

                    if display_help:
                        _echo_help(" " * 8 + f"{attr} ({formatted_type}):")
                        _echo_help(
                            "\n".join([f"{' ' * 12}" + desc for desc in metadata])
                        )

                    option_type = _click_type(attr_type)
                    if option_type is not None and class_name_attr not in existing_param_names:
                        is_flag = option_type is bool and not default

                        # Only add class-specific options
                        ctx.command.params.append(
                            click.Option(
                                ["--" + class_name_attr, class_name_attr],
                                type=option_type,
                                help=" ".join(metadata),
                                is_flag=is_flag,
                                default=None,  # This is important, or it sets all the default keys again in config
                            )
                        )

        if display_help:
            ctx.exit()

        super().parse_args(ctx, args)


def _click_type(annotation: Any) -> type | None:
    if annotation in (str, int, float, bool):
        return annotation
    args = get_args(annotation)
    if not args:
        return None
    non_none = [arg for arg in args if arg is not type(None)]
    if len(non_none) == 1 and non_none[0] in (str, int, float, bool):
        return non_none[0]
    return None
