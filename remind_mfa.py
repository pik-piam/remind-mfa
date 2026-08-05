import logging
from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

from remind_mfa.common.config_loader import get_config_paths, load_config
from remind_mfa.common.helpers import ModelNames, init_model

app = typer.Typer()


type ModelSelection = Literal["all"] | ModelNames


def configure_logger():
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def run_remind_mfa(config_names: list[str], models: list[ModelNames]) -> None:
    for model in models:
        model_config = load_config(config_names, model)
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


def prompt_for_config_names() -> list[str]:
    choices = ", ".join(path.stem for path in get_config_paths())
    entered_names = typer.prompt(
        f"Configs (comma-separated, available: {choices})", default="default"
    )
    return [name.strip() for name in entered_names.split(",") if name.strip()]


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
