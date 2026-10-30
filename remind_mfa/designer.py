"""Entry point for the flodym designer."""

from collections.abc import Sequence
from pathlib import Path

import flodym as fd

from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model

REPO_ROOT = Path(__file__).resolve().parents[1]


class DesignerModel:
    """A REMIND-MFA model, wrapped for the flodym designer.

    Args:
        cfg: The model configuration, as returned by `load_config`.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model: CommonModel = init_model(cfg)
        self._is_run_started = False
        self._is_computed = False

    @property
    def systems(self) -> dict[str, fd.MFASystem]:
        """The MFA systems by name: empty ones before `run`, the computed ones after it."""
        if self._is_computed:
            return self.model.computed_systems()
        return self.model.make_empty_systems()

    @property
    def input_parameter_names(self) -> list[str]:
        """The names of the parameters read from the input data."""
        return [parameter.name for parameter in self.model.definition_future.parameters]

    def run(self) -> dict[str, fd.MFASystem]:
        """Run the model, without export or visualization.

        A run replaces the parameters of the model, so the model is rebuilt from the
        configuration before running it again.

        Returns:
            The computed MFA systems by name.
        """
        if self._is_run_started:
            self.model = init_model(self.cfg)
            self._is_computed = False
        self._is_run_started = True
        self.model.run()
        self._is_computed = True
        return self.systems


def load(
    model: str,
    configs: Sequence[str | Path] = ("default", "pyodide"),
    root: str | Path | None = None,
) -> DesignerModel:
    """Load a model for the flodym designer.

      The returned object has the following attributes and methods:
      - `systems`: the MFA systems by name (`historical`, `future` and, for cement, `bottom_up`). Before `run()`, they have empty flows and stocks, to show the
    structure. After `run()`, they are the computed systems.
      - `run()`: runs the model and returns the computed systems.

      Args:
          model: Name of the model, e.g. "steel".
          configs: Configuration layers, as names of files in `<root>/config` or as paths.
          root: Root of the repository, against which configuration paths are resolved.
              Defaults to the repository containing this module.

      Returns:
          The model, with its systems available before running it.
    """
    root_dir = Path(root) if root is not None else REPO_ROOT
    if isinstance(configs, (str, Path)):
        configs = [configs]
    cfg = load_config(
        list(configs), ModelNames(model), config_dir=root_dir / "config", root_dir=root_dir
    )
    return DesignerModel(cfg)
