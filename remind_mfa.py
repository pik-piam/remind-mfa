import logging
import textwrap
from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

from remind_mfa.cli.helper import prompt_for_config_names
from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model

app = typer.Typer()


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


def run_remind_mfa(config_names: list[str], models: list[ModelNames]) -> None:
    for model_name in models:
        logging.info("=" * 103)
        logging.info(f"Starting {model_name.value} run...")
        model_config = load_config(config_names, model_name)
        model = init_model(cfg=model_config)
        logging.info(f"{type(model).__name__} instance created.")
        model.run()
        logging.info("Model computations completed.")
        model.export()
        logging.info("Export completed.")
        model.visualize()
        logging.info("Visualization completed.")


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


@app.command()
def main(
    config_names: Annotated[
        list[str] | None,
        typer.Option(
            "--config",
            help="Configuration name under config/. Repeat to stack configurations.",
        ),
    ] = None,
    model: Annotated[
        Literal["all", "plastics", "steel", "cement"] | None,
        typer.Option("--model", help="Model to run, or all."),
    ] = None,
) -> None:
    """Run REMIND-MFA with one or more layered configurations."""
    load_dotenv()

    if not config_names:
        config_names = prompt_for_config_names()
    if model is None:
        model_selection = prompt_for_model()
    else:
        model_selection = ModelNames(model) if model != "all" else "all"
    models_to_run = list(ModelNames) if model_selection == "all" else [model_selection]

    configure_logger()

    run_remind_mfa(config_names, models_to_run)


if __name__ == "__main__":
    app()
