import logging
import textwrap
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import blicket as bk
import typer
from blicket import dev, serve

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
    logging.getLogger("alembic").setLevel(logging.WARNING)


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


def open_viewer(run_paths: Sequence[Path]) -> None:
    """Build the Blicks of the run folders as one run, serve them with the Blick builder and open
    the viewer in the browser, as ``blicket dev --open`` does; returns when Ctrl-C stops the
    server.

    The build goes to ``.blicket/build/`` in the project, the one around this package, and is
    compared with the newest pushed baseline of its profile, if any. A run that exported no
    pickle leaves nothing to show, and a project blicket cannot work with leaves a message; both
    are logged instead of raised.

    Args:
        run_paths: The run folders of the models, which blicket loads as one run.
    """
    if not run_paths:
        logging.warning("No viewer: the run exported no pickle (export.pickle.do_export is off).")
        return
    try:
        root = bk.find_project_root(Path(__file__).parent)
        # Bound first on any free port, so that a viewer on the default port does not get in the
        # way and a port problem shows before the build
        server = serve.make_server(port=0)
    except bk.BlicketError as error:
        logging.error(f"No viewer: {error}")
        return
    try:
        session, report = dev.start(root, list(run_paths))
    except bk.BlicketError as error:
        server.server_close()
        logging.error(f"No viewer: {error}")
        return
    except BaseException:
        server.server_close()
        raise
    server.session = session
    logging.info(f"blicket: {report}")
    logging.info(f"The blicket viewer is at {server.url}#/ (Ctrl-C stops it).")
    webbrowser.open(server.url)
    serve.run(server)
