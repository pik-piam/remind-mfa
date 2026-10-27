import logging
import textwrap
from typing import Literal

import typer

from remind_mfa.common.config_loader import get_config_paths
from remind_mfa.common.helpers import ModelNames

type ModelSelection = Literal["all"] | ModelNames


def configure_logger():
    _FMT = "%(asctime)s %(levelname)-8s %(message)s"
    _DATEFMT = "%Y-%m-%d %H:%M:%S"
    _WIDTH = 132
    _INDENT = " " * 29  # len("2026-08-21 12:00:00 INFO     ")

    class _IndentFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            text = super().format(record)
            parts = []
            for i, line in enumerate(text.splitlines()):
                if i == 0:
                    parts.append(textwrap.fill(line, width=_WIDTH, subsequent_indent=_INDENT))
                else:
                    parts.append(
                        textwrap.fill(_INDENT + line, width=_WIDTH, subsequent_indent=_INDENT)
                    )
            return "\n".join(parts)

    handler = logging.StreamHandler()
    handler.setFormatter(_IndentFormatter(fmt=_FMT, datefmt=_DATEFMT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(handler)

    # mute info for packages spamming the log
    muted_packages = ["alembic", "plotly", "kaleido", "choreographer"]
    for package in muted_packages:
        logging.getLogger(package).setLevel(logging.WARNING)


def prompt_for_config_names() -> list[str]:
    choices = ", ".join(path.stem for path in get_config_paths())
    entered_names = typer.prompt(
        f"Configs (comma-separated, available: {choices})", default="default"
    )
    return [name.strip() for name in entered_names.split(",") if name.strip()]


def prompt_for_model() -> ModelSelection:
    choices = ", ".join(model.value for model in ModelNames) + ", all"
    while True:
        value = typer.prompt(f"Model ({choices})").strip().lower()
        if value == "all":
            return "all"
        try:
            return ModelNames(value)
        except ValueError:
            typer.echo(f"Invalid model {value!r}. Choose one of: {choices}.", err=True)
