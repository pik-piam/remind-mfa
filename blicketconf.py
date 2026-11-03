"""blicket's view of model runs, found by convention next to ``pyproject.toml``: the loader that
unpickles one or several run folders into one run, and the dataset that the Blick builder of
``blicket dev`` charts.

The Blicks, the figures of a run, are in ``blicks/``; see ``blicks/README.md``.
"""

import pickle
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import blicket as bk
import flodym as fd

from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.trade import TradeSet

PICKLE_NAME = "model.pickle"

MODEL_ORDER = [name.value for name in ModelNames]
"""The order a run holds its models in, that of ``ModelNames``."""

# The historical system counts the same calendar years as the future one, on a dimension of its
# own; under one name, a historical flow and its future counterpart share a chart.
DIMENSION_NAMES = {"Historical Time": "Time"}

# Units of parameters by name. A rate, share, yield or ratio is a fraction; the other parameters
# have units flodym does not record.
PARAMETER_UNITS = {
    "gdppc": "2005 USD PPP per person",
    "population": "people",
    "lifetime_mean": "years",
    "lifetime_std": "years",
}
FRACTION_SUFFIXES = ("_rate", "_share", "_shares", "_yield", "_ratio", "_split")


@dataclass(frozen=True)
class Run:
    """The models of a run, by name, in the order of ``ModelNames``: one for a run folder, up to
    one per model for a series folder or several run folders. The models are of one scenario and
    region mapping.

    Attributes:
        models: The unpickled models by name, such as ``"steel"``.
    """

    models: dict[str, CommonModel]

    def __iter__(self) -> Iterator[CommonModel]:
        return iter(self.models.values())

    def __len__(self) -> int:
        return len(self.models)

    @property
    def names(self) -> list[str]:
        """The names of the models, in the run's order."""
        return list(self.models)

    @property
    def scenario(self) -> str:
        """The scenario the models were run with, such as ``SSP2``."""
        return self._first.cfg.model_switches.scenario

    @property
    def region_mapping(self) -> str:
        """The region mapping of the models, such as ``h12``."""
        return self._first.cfg.input.region_mapping

    @property
    def _first(self) -> CommonModel:
        return next(iter(self.models.values()))


def load_run(selection: bk.RunSelection) -> tuple[Run, bk.RunInfo]:
    """Unpickle the models of one or several run folders into one run.

    A path is a run folder, ``<prefix>_<model>_<scenario>_<regions>/`` with a ``model.pickle``,
    that pickle, or a series folder of run folders, such as the ``data_out/ci_series/`` the ``ci``
    configuration layer writes for all models. The run holds every model found, at most one per
    model, in the order of ``ModelNames``. Its id is the folder's name, the names joined by ``+``
    for several paths; its profile is the models, scenario and region mapping, such as
    ``steel_SSP2_h12`` or ``plastics-steel-cement_SSP2_h12``, so that every combination of
    models has baselines of its own. The pickles do not record the commit of the model checkout,
    so the run info has none.

    Args:
        selection: The run paths given on the command line.

    Returns:
        The run and what blicket records about it.

    Raises:
        FileNotFoundError: If a path holds no ``model.pickle``, nor run folders with one.
        ValueError: If two pickles hold the same model, or the models are of different scenarios
            or region mappings.
        RuntimeError: If a pickle was written by another version of remind-mfa than the one
            installed.
    """
    pickles = [path for given in selection.paths for path in _pickles(given)]
    found: dict[str, tuple[Path, CommonModel]] = {}
    for path in pickles:
        model = read_model(path)
        if model.name in found:
            raise ValueError(f"{path} and {found[model.name][0]} both hold the {model.name} model")
        found[model.name] = (path, model)
    run = Run({name: found[name][1] for name in MODEL_ORDER if name in found})
    settings = {
        (model.cfg.model_switches.scenario, model.cfg.input.region_mapping) for model in run
    }
    if len(settings) > 1:
        shown = ", ".join(f"{name} in {path.parent.name}" for name, (path, _) in found.items())
        raise ValueError(f"the models are of different scenarios or region mappings: {shown}")
    profile = f"{'-'.join(run.names)}_{run.scenario}_{run.region_mapping}"
    info = bk.RunInfo(
        id=_run_id(selection.paths), profile=profile, fingerprint=bk.fingerprint(*pickles)
    )
    return run, info


def _pickles(path: Path) -> list[Path]:
    """The ``model.pickle`` files ``path`` names: the file itself, the one of a run folder, or
    those of the run folders in a series folder, in folder order."""
    if path.name == PICKLE_NAME and path.is_file():
        return [path]
    if (path / PICKLE_NAME).is_file():
        return [path / PICKLE_NAME]
    found = sorted(path.glob(f"*/{PICKLE_NAME}")) if path.is_dir() else []
    if not found:
        raise FileNotFoundError(
            f"{path} holds no {PICKLE_NAME}, nor run folders with one; is it a run or series "
            "folder?"
        )
    return found


def _run_id(paths: tuple[Path, ...]) -> str:
    """The folder names of the paths given, joined by ``+``; a pickle's is its folder's."""
    names = [path.parent.name if path.name == PICKLE_NAME else path.name for path in paths]
    return " + ".join(names)


def read_model(path: Path) -> CommonModel:
    """Read a pickled model.

    Args:
        path: The ``model.pickle`` of a run.

    Returns:
        The model, with its historical and future MFA systems.

    Raises:
        RuntimeError: If the pickle was written by another version of remind-mfa than the one
            installed, or holds no model.
    """
    with warnings.catch_warnings():
        # unpickling older runs re-runs pydantic validation of the stored config
        warnings.simplefilter("ignore")
        try:
            with path.open("rb") as file:
                model = pickle.load(file)
        except (AttributeError, ImportError) as error:
            raise RuntimeError(
                f"{path} was written by another version of remind-mfa than the one installed "
                f"({type(error).__name__}: {error}); check out the commit that produced the run"
            ) from error
    if not isinstance(model, CommonModel):
        raise RuntimeError(f"{path} does not hold a REMIND-MFA model but a {type(model).__name__}")
    return model


def dataset(run: Run) -> bk.Frames:
    """The arrays of the run's models for the Blick builder of ``blicket dev``.

    Quantities per model, under its name: ``<model>/flows/<flow>`` in t per year;
    ``<model>/stocks/<stock>/stock`` in t and ``/inflow`` and ``/outflow`` in t per year;
    ``<model>/trade/<market>/imports``, ``/exports`` and ``/net_imports`` in t per year;
    ``<model>/parameters/<parameter>``, not additive, without the parameters that have no
    dimension; and the historical system's flows, stocks and trade under
    ``<model>/historical/``, its parameters left out, since most of them are the future system's.
    ``Historical Time`` is called ``Time``, and a dimension holds the values of every model. An
    array is read as a frame when it is first charted.

    Args:
        run: The run.

    Returns:
        The dataset.
    """
    frames = bk.Frames(dimensions=_dimensions(run))
    for name, model in run.models.items():
        future, historical = model.future_mfa, model.historical_mfa
        _add_system(frames, future, prefix=f"{name}/", group_prefix=f"{name} ", group_suffix="")
        for key, parameter in future.parameters.items():
            if parameter.dims.ndim:
                unit = _parameter_unit(key)
                _add(
                    frames,
                    f"{name}/parameters/{key}",
                    parameter,
                    f"{name} parameters",
                    unit,
                    additive=False,
                )
        _add_system(
            frames,
            historical,
            prefix=f"{name}/historical/",
            group_prefix=f"{name} ",
            group_suffix=" (historical)",
        )
    return frames


def _add_system(
    frames: bk.Frames, mfa: fd.MFASystem, prefix: str, group_prefix: str, group_suffix: str
) -> None:
    """The flows, stocks and trade of ``mfa`` as quantities under ``prefix``, in the groups
    ``<group_prefix>flows<group_suffix>`` and so on."""
    for key, flow in mfa.flows.items():
        group = f"{group_prefix}flows{group_suffix}"
        _add(frames, f"{prefix}flows/{key}", flow, group, "t per year")
    for key, stock in mfa.stocks.items():
        for part, unit in (("stock", "t"), ("inflow", "t per year"), ("outflow", "t per year")):
            array = getattr(stock, part)
            if array is not None:
                group = f"{group_prefix}stocks{group_suffix}"
                _add(frames, f"{prefix}stocks/{key}/{part}", array, group, unit)
    trade_set: TradeSet | None = getattr(mfa, "trade_set", None)
    for key, market in (trade_set.markets if trade_set is not None else {}).items():
        for part in ("imports", "exports", "net_imports"):
            array = getattr(market, part)
            group = f"{group_prefix}trade{group_suffix}"
            _add(frames, f"{prefix}trade/{key}/{part}", array, group, "t per year")


def _parameter_unit(name: str) -> str | None:
    if name.endswith(FRACTION_SUFFIXES):
        return "fraction"
    return PARAMETER_UNITS.get(name)


def _dimensions(run: Run) -> list[bk.Dimension]:
    """The dimensions of the run's models as the dataset names them, each with the values of
    every model, typed by their items, in the models' order; a dimension of years is sorted, so
    Historical Time's years fall into place among Time's."""
    values: dict[str, dict[Any, None]] = {}
    for model in run:
        for dimension in model.dims:
            name = DIMENSION_NAMES.get(dimension.name, dimension.name)
            values.setdefault(name, {}).update(dict.fromkeys(dimension.items))
    dimensions = []
    for name, items in values.items():
        integer = all(isinstance(item, int) for item in items)
        listed = sorted(items) if integer else list(items)
        dtype = "integer" if integer else "string"
        dimensions.append(bk.Dimension(name=name, dtype=dtype, values=listed))
    return dimensions


def _add(
    frames: bk.Frames,
    name: str,
    array: fd.FlodymArray,
    group: str,
    unit: str | None,
    *,
    additive: bool = True,
) -> None:
    """``array`` as the quantity ``name``, read as a frame when first charted; an array over both
    Time and Historical Time is left out, since the two would be one column."""
    names = [DIMENSION_NAMES.get(d, d) for d in array.dims.names]
    if len(set(names)) < len(names):
        return
    frames.add(
        name,
        lambda: array.to_df().rename_axis(index=names),
        unit=unit,
        dimensions=names,
        additive=additive,
        group=group,
    )
