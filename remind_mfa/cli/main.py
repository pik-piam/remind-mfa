from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

from remind_mfa.cli.helpers import (
    ModelSelection,
    configure_logger,
    prompt_for_config_names,
    prompt_for_model,
)
from remind_mfa.common.batch import Batch
from remind_mfa.common.config_loader import ConfigStack
from remind_mfa.common.helpers import ModelNames

app = typer.Typer()


@app.command()
def main(
    config_names: Annotated[
        list[str] | None,
        typer.Option(
            "--config",
            help=(
                "Configuration name under config/. Repeat to stack configurations. "
                "At most one may contain [[batch_matrix]] tables, which define a batch of runs."
            ),
        ),
    ] = None,
    model: Annotated[
        Literal["all", "plastics", "steel", "cement"] | None,
        typer.Option(
            "--model",
            help=(
                "Model to run, or all. With [[batch_matrix]] tables, restricts the matrices "
                "to this model."
            ),
        ),
    ] = None,
) -> None:
    """Run REMIND-MFA with one or more layered configurations."""
    load_dotenv()

    if not config_names:
        config_names = prompt_for_config_names()
    configure_logger()
    stack = ConfigStack.load(config_names)

    model_selection: ModelSelection | None = None
    if model is not None:
        model_selection = ModelNames(model) if model != "all" else "all"
    elif Batch.requires_model_selection(stack):
        model_selection = prompt_for_model()
    models = None
    if model_selection is not None:
        models = list(ModelNames) if model_selection == "all" else [model_selection]

    batch = Batch.from_stack(stack, models)
    batch.run()
