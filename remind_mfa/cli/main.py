from remind_mfa.common.batch import run_batch
from remind_mfa.cli.helpers import configure_logger, prompt_for_config_names, prompt_for_model
from remind_mfa.common.helpers import ModelNames


import typer
from dotenv import load_dotenv


from typing import Annotated, Literal
app = typer.Typer()


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

    run_batch(config_names, models_to_run)