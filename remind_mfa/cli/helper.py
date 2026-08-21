import typer

from remind_mfa.common.config_loader import get_config_paths


def prompt_for_config_names() -> list[str]:
    choices = ", ".join(path.stem for path in get_config_paths())
    entered_names = typer.prompt(
        f"Configs (comma-separated, available: {choices})", default="default"
    )
    return [name.strip() for name in entered_names.split(",") if name.strip()]
