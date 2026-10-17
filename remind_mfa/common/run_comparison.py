"""Building blocks for comparing several REMIND-MFA runs.

Runs are read into :class:`LoadedRun` objects (see :func:`load_run`). Both comparison notebooks
draw one figure per run and merge the figures into an overlay and a difference figure
(:func:`overlay_figures`, :func:`difference_figure`); they differ in where the figures come from:

* :mod:`notebooks.compare_runs_report` re-runs the model's own visualizer on each run
  (:func:`standard_figures`). Whatever the visualizer is configured to plot is compared, so a
  plot only has to be added once, in the visualizer.
* :mod:`notebooks.compare_runs` explores any flow, stock, parameter or trade variable. The
  variables are stacked into one long ``DataFrame`` (:func:`build_frame`) with one column per
  dimension (``Time``, ``Region``, ``Good``, ...), the bookkeeping columns ``Run`` and
  ``Variable``, and a ``value`` column, which :func:`frame_figures` draws in the layout of the
  merged figures.

*Change detection* boils the comparison down to numbers: which variables changed in which region
(:func:`regional_changes`, :func:`change_heatmap`), whether the runs are numerically identical
(:func:`verdict`, :func:`verdict_markdown` for the PR comment) and how much a figure changed
(:func:`figure_change`).

The functions here are deliberately free of any notebook or UI code so they can be unit tested
and reused.
"""

import dataclasses
import math
import pickle
import re
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import flodym as fd
import numpy as np
import pandas as pd
import plotly.colors as plc
import plotly.graph_objects as go
import plotly.io as pio
import pyam
from matplotlib import colors as mcolors
from plotly.subplots import make_subplots
from pydantic import BaseModel

from remind_mfa.common.common_config import BaseVisualizationCfg, VisualizationCfg
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.helpers import ModelNames

WORLD = "World"
"""Item name used for the sum over all regions."""

REGION_COLUMN = "Region"
RUN_COLUMN = "Run"
VARIABLE_COLUMN = "Variable"
UNIT_COLUMN = "Unit"
VALUE_COLUMN = "value"

COLORS = plc.qualitative.Dark24
"""Palette used by the model visualizers, so comparison figures match the standard plots."""

MAX_FACET_COLUMNS = 4
HEATMAP_MAX_ROWS = 30

INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
GRID_COLOR = "#e1e0d9"
AXIS_COLOR = "#c3c2b7"
SURFACE = "#ffffff"

TEMPLATE = go.layout.Template(
    layout=dict(
        font=dict(
            family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
            size=12,
            color=SECONDARY_INK,
        ),
        title=dict(x=0, xref="paper", xanchor="left", font=dict(size=16, color=INK)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=list(COLORS),
        xaxis=dict(
            gridcolor=GRID_COLOR,
            linecolor=AXIS_COLOR,
            showline=True,
            ticks="outside",
            tickcolor=AXIS_COLOR,
            ticklen=4,
            zeroline=False,
            automargin=True,
        ),
        yaxis=dict(
            gridcolor=GRID_COLOR,
            zerolinecolor=AXIS_COLOR,
            zerolinewidth=1,
            automargin=True,
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)", tracegroupgap=0, title=dict(font=dict(color=INK))),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=AXIS_COLOR, font=dict(color=INK)),
        bargap=0.25,
        margin=dict(l=60, r=24, t=80, b=48),
    )
)
"""Quiet look shared by all comparison figures: white surface, hairline grid, recessive axes."""

PANEL_HEIGHT = 250
"""Height in pixels of one row of subplots."""

SINGLE_PANEL_HEIGHT = 460
"""Height in pixels of a figure without subplots."""


# ── run discovery and loading ──────────────────────────────────────────────────


@dataclass
class LoadedRun:
    """A run together with its loaded data.

    ``data`` is the whole pickled model for model pickles and the ``pyam.IamDataFrame`` for IAMC
    workbooks. Only model pickles support the standard-figure comparison.
    """

    path: Path
    label: str
    data: CommonModel | pyam.IamDataFrame = field(repr=False)

    @property
    def is_model(self) -> bool:
        """Whether the run was read from a model pickle."""
        return isinstance(self.data, CommonModel)

    @property
    def model_name(self) -> str | None:
        """The name of the model a run belongs to, e.g. ``steel``."""
        return self.model.name if self.is_model else None

    @property
    def model(self) -> CommonModel:
        """The pickled model; raises for runs read from other sources."""
        if not isinstance(self.data, CommonModel):
            raise TypeError(f"Run {self.label!r} was not read from a model pickle.")
        return self.data

    @property
    def mfa(self) -> CommonMFASystem:
        """The future MFA system of the pickled model, holding the results."""
        return self.model.future_mfa

    def with_label(self, label: str) -> LoadedRun:
        """The same run under another label."""
        return dataclasses.replace(self, label=label)


@dataclass(frozen=True)
class RunInfo:
    """A run on disk, described by what its path tells without reading the (large) file.

    Model, scenario and region mapping are taken from the name of the run directory,
    ``<prefix>_<model>_<scenario>_<region mapping>``, and are ``None`` if it is named otherwise.
    """

    path: Path
    """``model.pickle`` of the run, or an IAMC ``.xlsx`` workbook."""
    modified: datetime
    """When the file was last written, i.e. when the run finished."""
    _label: str | None = None
    """Name to show the run under in figures, see :func:`default_label`."""
    model: str | None = None
    scenario: str | None = None
    region_mapping: str | None = None

    def display_path(self, data_root: Path | None = None) -> str:
        """The run, relative to the data root if it lies below it, to tell runs apart in a picker."""
        # all pickles are called model.pickle, so their run directory tells them apart
        shown = self.path.parent if self.path.name == "model.pickle" else self.path
        if data_root is not None and shown.is_relative_to(data_root):
            shown = shown.relative_to(data_root)
        return str(shown)

    @property
    def label(self) -> str:
        """Human-readable label for a run path.

        The label is derived from the name of the run directory if no custom label is set.
        """
        if self._label is not None:
            return self._label
        run_dir = self.path if self.path.is_dir() else self.path.parent
        return run_dir.name or self.path.stem

    @classmethod
    def from_path(cls, path: Path, label: str | None = None) -> RunInfo:
        """Describe the run at ``path``.

        Args:
            path: ``model.pickle`` of a run or the run directory holding it, or an IAMC
                ``.xlsx`` workbook.
            data_root: Directory the display path is relative to, if the run lies below it.
            label: Name to show the run under; defaults to :func:`default_label`.

        Raises:
            FileNotFoundError: If there is no file at ``path``.
        """
        path = Path(path)
        if (path / "model.pickle").is_file():
            path = path / "model.pickle"

        run_dir = path if path.is_dir() else path.parent
        parts = run_dir.name.split("_")
        # the prefix and the scenario may contain underscores, the model name does not
        model_index = next(
            (
                index
                for index, part in enumerate(parts)
                if part in {model.value for model in ModelNames} and 0 < index < len(parts) - 2
            ),
            None,
        )
        return cls(
            path=path,
            _label=label,
            modified=datetime.fromtimestamp(path.stat().st_mtime),
            model=None if model_index is None else parts[model_index],
            scenario=None if model_index is None else "_".join(parts[model_index + 1 : -1]),
            region_mapping=None if model_index is None else parts[-1],
        )


def discover_runs(data_root: Path) -> list[RunInfo]:
    """Find all model pickles below ``data_root``, newest first."""
    runs = [RunInfo.from_path(path) for path in data_root.glob("**/model.pickle")]
    return sorted(runs, key=lambda run: (run.modified, run.display_path), reverse=True)


def unique_labels(labels: Sequence[str]) -> list[str]:
    """Disambiguate repeated labels by appending a counter, keeping the given order."""
    seen: dict[str, int] = {}
    result = []
    for label in labels:
        seen[label] = seen.get(label, 0) + 1
        result.append(label if seen[label] == 1 else f"{label} ({seen[label]})")
    return result


def load_runs(
    run_info: dict[str, RunInfo],
) -> tuple[dict[str, LoadedRun], dict[str, str]]:
    """Load multiple runs given their RunInfo objects."""
    loaded_runs = {}
    load_failures = {}
    for key, info in run_info.items():
        try:
            loaded_runs[key] = load_run(info.path, info.label)
        except Exception as load_error:  # noqa: BLE001
            load_failures[key] = load_error
    return loaded_runs, load_failures


def load_run(path: Path, label: str) -> LoadedRun:
    """Read a single run: the whole model for pickles, the workbook for IAMC exports.

    Args:
        path: ``model.pickle`` of a run, or an IAMC ``.xlsx`` workbook.
        label: Label to show the run under; defaults to :func:`default_label`.

    Raises:
        RuntimeError: If a pickle was written by an incompatible version of the model code.
    """
    path = Path(path)
    data = _load_model(path) if path.suffix == ".pickle" else pyam.IamDataFrame(str(path))
    return LoadedRun(path=path, label=label, data=data)


def _load_model(path: Path) -> CommonModel:
    with warnings.catch_warnings():
        # unpickling older runs re-runs pydantic validation of the stored config
        warnings.simplefilter("ignore")
        try:
            with path.open("rb") as file_handle:
                model = pickle.load(file_handle)
        except (AttributeError, ImportError, ModuleNotFoundError) as error:
            raise RuntimeError(
                f"{path} was written by a different version of the model code and cannot be "
                f"read here ({error})."
            ) from error
    if not isinstance(model, CommonModel):
        raise RuntimeError(f"{path} does not contain a REMIND-MFA model.")
    return model


# ── variables and tidy frames ──────────────────────────────────────────────────


def list_variables(run: LoadedRun) -> list[str]:
    """Qualified names of the variables a run offers.

    Qualified names are ``"<group>: <name>"``, e.g. ``"flow: bof_production => forming"``. The
    group prefix keeps names unique across flows, stocks, parameters and trade.
    """
    if isinstance(run.data, pyam.IamDataFrame):
        return [f"{variable.split('|')[0]}: {variable}" for variable in run.data.variable]
    return list(_pickle_getters(run.mfa))


def common_variables(runs: Sequence[LoadedRun]) -> list[str]:
    """Variables offered by *all* runs, in the order of the first one, so only comparable data
    can be selected."""
    per_run = [list_variables(run) for run in runs]
    shared = set.intersection(*(set(names) for names in per_run))
    return [name for name in per_run[0] if name in shared]


def _pickle_getters(mfa: CommonMFASystem) -> dict[str, Callable[[], fd.FlodymArray]]:
    """Lazy accessors for every array of an MFA system, keyed by qualified variable name.

    The arrays are wrapped in callables so that listing the variables of a run stays cheap:
    derived arrays such as net trade are only computed once actually selected.
    """
    getters: dict[str, Callable[[], fd.FlodymArray]] = {}
    for name, flow in (mfa.flows or {}).items():
        getters[f"flow: {name}"] = lambda flow=flow: flow
    for name, stock in (mfa.stocks or {}).items():
        for group, attribute in (
            ("stock", "stock"),
            ("stock inflow", "inflow"),
            ("stock outflow", "outflow"),
        ):
            if getattr(stock, attribute, None) is not None:
                getters[f"{group}: {name}"] = lambda stock=stock, attribute=attribute: (
                    getattr(stock, attribute)
                )
    for name, parameter in mfa.parameters.items():
        getters[f"parameter: {name}"] = lambda parameter=parameter: parameter
    for name, market in (mfa.trade_set.markets if mfa.trade_set else {}).items():
        getters[f"trade: {name} imports"] = lambda market=market: market.imports
        getters[f"trade: {name} exports"] = lambda market=market: market.exports
        getters[f"trade: {name} net imports"] = lambda market=market: market.net_imports
    return getters


def get_array(run: LoadedRun, variable: str) -> fd.FlodymArray:
    """The flodym array behind a qualified variable name of a model run."""
    getters = _pickle_getters(run.mfa)
    if variable not in getters:
        raise KeyError(f"{variable!r} not found in run {run.label!r}.")
    return getters[variable]()


def get_variable(run: LoadedRun, variable: str) -> pd.DataFrame:
    """Tidy long frame of a single variable of a single run.

    Columns are one per dimension of the variable, plus ``value`` and, where the source knows
    it, ``Unit``.
    """
    if isinstance(run.data, pyam.IamDataFrame):
        return _iamc_variable(run.data, variable.split(": ", 1)[1])
    return get_array(run, variable).to_df(index=False)


def _iamc_variable(iam_df: pyam.IamDataFrame, variable: str) -> pd.DataFrame:
    df = iam_df.filter(variable=variable).data
    if df.empty:
        raise KeyError(f"{variable!r} not found in the IAMC workbook.")
    return df.rename(columns={"year": "Time", "region": REGION_COLUMN, "unit": UNIT_COLUMN})[
        ["Time", REGION_COLUMN, UNIT_COLUMN, VALUE_COLUMN]
    ]


def build_frame(runs: Sequence[LoadedRun], variables: Sequence[str]) -> pd.DataFrame:
    """Stack the given variables of the given runs into one frame.

    Adds the ``Run`` and ``Variable`` columns. Variables do not all have the same dimensions, so
    a dimension that one of the parts lacks is ``NaN`` in its rows; :func:`frame_figures` then
    either keeps that as its own item or sums it away with the rest.
    """
    frames = []
    for run in runs:
        for variable in variables:
            df = get_variable(run, variable)
            df.insert(0, RUN_COLUMN, run.label)
            df.insert(1, VARIABLE_COLUMN, variable)
            frames.append(df)
    if not frames:
        return pd.DataFrame({RUN_COLUMN: [], VARIABLE_COLUMN: [], VALUE_COLUMN: []})
    tidy = pd.concat(frames, ignore_index=True)
    tidy[RUN_COLUMN] = pd.Categorical(tidy[RUN_COLUMN], categories=[run.label for run in runs])
    return tidy


def dimension_columns(df: pd.DataFrame) -> list[str]:
    """Columns of a tidy frame that can be mapped to a plot channel."""
    return [column for column in df.columns if column not in (VALUE_COLUMN, UNIT_COLUMN)]


def with_world(df: pd.DataFrame) -> pd.DataFrame:
    """Add the sum over all regions as region ``World``, unless the data already reports it.

    ``World`` comes first in the item order of the region column, followed by the other regions
    in alphabetical order. Frames without a region column are returned as they are.
    """
    if REGION_COLUMN not in df.columns:
        return df
    is_world = df[REGION_COLUMN] == WORLD
    regional, world = df[~is_world], df[is_world]
    if world.empty:
        others = [column for column in df.columns if column not in (REGION_COLUMN, VALUE_COLUMN)]
        world = (
            regional.groupby(others, as_index=False, observed=True, dropna=False)[VALUE_COLUMN]
            .sum()
            .assign(**{REGION_COLUMN: WORLD})[df.columns]
        )
    combined = pd.concat([world, regional], ignore_index=True)
    combined[REGION_COLUMN] = pd.Categorical(
        combined[REGION_COLUMN],
        categories=[WORLD, *sorted(regional[REGION_COLUMN].dropna().unique())],
        ordered=True,
    )
    return combined


def apply_filters(df: pd.DataFrame, filters: Mapping[str, Sequence[Any]]) -> pd.DataFrame:
    """Restrict columns to the given items. Empty or missing selections are ignored."""
    for column, items in filters.items():
        if column in df.columns and len(items):
            df = df[df[column].isin(items)]
    return df


def ordered_items(series: pd.Series) -> list:
    """Items of a column in plotting order, respecting an explicit categorical order.

    Returns builtin types rather than numpy scalars, so the items can be compared with and
    displayed as literals (a ``numpy.int64`` year renders as ``np.int64(2020)`` in UI controls).
    """
    if isinstance(series.dtype, pd.CategoricalDtype):
        present = set(series)
        return [item for item in series.cat.categories.tolist() if item in present]
    return pd.unique(series).tolist()


class ChartType(StrEnum):
    """How :func:`frame_figures` draws the items of the colour dimension."""

    LINE = "line"
    SCATTER = "scatter"
    AREA = "stacked area"
    BAR_STACKED = "stacked bar"
    BAR_GROUPED = "grouped bar"


def frame_figures(
    df: pd.DataFrame,
    x: str,
    color: str | None = None,
    facet: str | None = None,
    chart_type: ChartType = ChartType.LINE,
    shares: bool = False,
    title: str = "",
    ylabel: str = "",
) -> dict[str, go.Figure]:
    """One figure per run of a tidy frame, ready to be merged like the standard figures.

    Values are summed over every dimension that is not mapped to the x axis, the lines or the
    subplots. A summed region dimension takes the ``World`` rows if there are any (see
    :func:`with_world`), as they already hold the sum. All figures have the same traces in the
    same order, missing values being ``NaN``, so :func:`overlay_figures` and
    :func:`difference_figure` can compare them point by point.

    Args:
        df: Tidy frame as returned by :func:`build_frame`.
        x: Column on the x axis.
        color: Column with one line per item, each in its own colour.
        facet: Column with one subplot per item.
        chart_type: How to draw the items of ``color``.
        shares: Whether to show the lines in percent of their sum.
        title: Title of the figures.
        ylabel: Title of the y axes.

    Returns:
        The figures by run label, in the order of the runs.

    Raises:
        ValueError: If a column is mapped to several channels, or there is nothing to plot.
    """
    channels = [column for column in (facet, color) if column is not None]
    if len({x, *channels}) <= len(channels):
        raise ValueError("Each dimension can only go to one of the x axis, lines and subplots.")
    if REGION_COLUMN in df.columns and REGION_COLUMN not in (x, *channels):
        world = df[df[REGION_COLUMN] == WORLD]
        df = df if world.empty else world
    if df.empty:
        raise ValueError("Nothing to plot: the selection is empty.")
    items = {column: [str(item) for item in ordered_items(df[column])] for column in channels}
    x_items = [item for item in ordered_items(df[x]) if not pd.isna(item)]
    # as text, items a variable lacks the dimension of (NaN) stay in the groups as "nan"
    df = df.assign(**{column: df[column].astype(str) for column in channels})
    totals = df.groupby([RUN_COLUMN, *channels, x], observed=True)[VALUE_COLUMN].sum()
    if shares:
        within = [RUN_COLUMN, *([facet] if facet else []), x]
        sums = totals.groupby(level=within, observed=True).transform("sum")
        totals = 100 * totals / sums.replace(0, np.nan)
    table = totals.unstack(x).reindex(columns=x_items)
    lines = {
        key if isinstance(key, tuple) else (key,): row.to_numpy(dtype=float)
        for key, row in table.iterrows()
    }
    missing = np.full(len(x_items), np.nan)

    figures = {}
    for run in ordered_items(df[RUN_COLUMN]):
        panels = []
        for facet_item in items[facet] if facet else [None]:
            panel = _Panel(
                title=facet_item or "",
                xaxis=dict(title_text=x),
                yaxis=dict(title_text=ylabel),
            )
            stack = np.zeros(len(x_items))
            for index, color_item in enumerate(items[color] if color else [None]):
                key = tuple(item for item in (run, facet_item, color_item) if item is not None)
                values = lines.get(key, missing)
                item_color = COLORS[index % len(COLORS)]
                if chart_type in (ChartType.BAR_STACKED, ChartType.BAR_GROUPED):
                    trace = go.Bar(
                        x=[str(item) for item in x_items],
                        y=values,
                        name=color_item,
                        # a hairline of the surface colour separates touching bars and segments
                        marker=dict(color=item_color, line=dict(color=SURFACE, width=1)),
                        # the runs' bars of an item share their place next to the other items
                        offsetgroup=color_item if chart_type is ChartType.BAR_GROUPED else None,
                    )
                else:
                    trace = go.Scatter(
                        x=x_items,
                        y=values,
                        name=color_item,
                        mode="markers" if chart_type is ChartType.SCATTER else "lines",
                        line_color=item_color,
                        marker_color=item_color,
                    )
                if chart_type is ChartType.AREA:
                    stack = stack + np.nan_to_num(values)
                    fill = "tozeroy" if index == 0 else "tonexty"
                    trace.update(y=stack, fill=fill, fillcolor=item_color)
                panel.traces.append(trace)
            panels.append(panel)
        fig = _grid_figure(_wrap(panels), title)
        figures[str(run)] = fig.update_layout(
            barmode="stack" if chart_type is ChartType.BAR_STACKED else "group"
        )
    return figures


# ── subplots ───────────────────────────────────────────────────────────────────

_CARRIED_AXIS_SETTINGS = ("type", "tickformat", "ticksuffix", "exponentformat")
"""Axis settings of a standard figure that merged figures keep, e.g. logarithmic axes."""


@dataclass
class _Panel:
    """One subplot of a figure: its title, its traces and the settings of its axes."""

    title: str
    traces: list = field(default_factory=list)
    xaxis: dict[str, Any] = field(default_factory=dict)
    yaxis: dict[str, Any] = field(default_factory=dict)

    @property
    def is_stacked(self) -> bool:
        """Whether the subplot holds stacked areas, whose layers only make sense together."""
        return any(getattr(trace, "fill", None) for trace in self.traces)

    def series(self) -> dict[str, list]:
        """The traces grouped into series by name, e.g. the historic, projected and last-year
        traces of one region."""
        grouped: dict[str, list] = {}
        for trace in self.traces:
            grouped.setdefault(_series_name(trace), []).append(trace)
        return grouped


def _series_name(trace) -> str:
    return "" if trace.name is None else str(trace.name)


def _panels(fig: go.Figure) -> list[_Panel]:
    """The subplots of a figure in reading order, holding copies of its traces.

    Colours plotly would pick from the colour cycle are made explicit, as they depend on the
    position of a trace in the figure, which merging changes.
    """
    panels: dict[tuple[str, str], _Panel] = {}
    positions: dict[tuple[str, str], tuple[float, float]] = {}
    colorway = fig.layout.template.layout.colorway or plc.qualitative.Plotly
    for index, trace in enumerate(go.Figure(fig).data):
        if trace.type == "scatter" and trace.line.color is None and trace.marker.color is None:
            color = colorway[index % len(colorway)]
            (
                trace.update(marker_color=color)
                if _is_markers(trace)
                else trace.update(line_color=color)
            )
        key = (trace.xaxis or "x", trace.yaxis or "y")
        if key not in panels:
            xaxis, yaxis = fig.layout[_axis_key(key[0])], fig.layout[_axis_key(key[1])]
            x_domain, y_domain = xaxis.domain or (0.0, 1.0), yaxis.domain or (0.0, 1.0)
            positions[key] = (-round(y_domain[1], 6), round(x_domain[0], 6))
            panels[key] = _Panel(
                title=_subplot_title(fig, (x_domain[0] + x_domain[1]) / 2, y_domain[1]),
                xaxis=_axis_settings(xaxis),
                yaxis=_axis_settings(yaxis),
            )
        panels[key].traces.append(trace)
    return [panels[key] for key in sorted(panels, key=positions.__getitem__)]


def _axis_key(anchor: str) -> str:
    """Layout key of the axis a trace refers to, e.g. ``"x2"`` -> ``"xaxis2"``."""
    return f"{anchor[0]}axis{anchor[1:]}"


def _axis_settings(axis) -> dict[str, Any]:
    settings = {name: axis[name] for name in _CARRIED_AXIS_SETTINGS if axis[name] is not None}
    if axis.title.text:
        settings["title_text"] = axis.title.text
    return settings


def clean_title(text: str | None) -> str:
    """Tidy a title: collapse repeated spaces and drop a ``Dimension=`` prefix of subplot titles."""
    text = " ".join((text or "").split())
    # "=>" separates the processes of a flow name, it is no prefix
    prefixed = re.fullmatch(r"[^=]+=(?!>)(.+)", text)
    return prefixed.group(1).strip() if prefixed else text


def _subplot_title(fig: go.Figure, x_center: float, y_top: float) -> str:
    """Title of the subplot at the given position; ``make_subplots`` centres it on top."""
    for annotation in fig.layout.annotations:
        if annotation.x is None or annotation.y is None:
            continue
        if abs(annotation.x - x_center) < 1e-3 and abs(annotation.y - y_top) < 1e-3:
            return clean_title(annotation.text)
    return ""


def _match_panels(panel_sets: Sequence[list[_Panel]]) -> list[list[_Panel]]:
    """Match the subplots of several figures by title, or by position if titles are missing or
    repeated. A subplot that some figures lack is matched with empty ones in their place."""

    def keyed(panels: list[_Panel]) -> dict[str, _Panel]:
        titles = [panel.title for panel in panels]
        if all(titles) and len(set(titles)) == len(titles):
            return dict(zip(titles, panels))
        return {f"#{index}": panel for index, panel in enumerate(panels)}

    keyed_sets = [keyed(panels) for panels in panel_sets]
    matched = []
    for key in dict.fromkeys(key for panels in keyed_sets for key in panels):
        present = next(panels[key] for panels in keyed_sets if key in panels)
        matched.append(
            [panels.get(key) or dataclasses.replace(present, traces=[]) for panels in keyed_sets]
        )
    return matched


def _wrap(panels: Sequence[_Panel]) -> list[list[_Panel | None]]:
    n_columns = max(1, min(MAX_FACET_COLUMNS, len(panels)))
    return [list(panels[start : start + n_columns]) for start in range(0, len(panels), n_columns)]


def _grid_figure(cells: Sequence[Sequence[_Panel | None]], title: str) -> go.Figure:
    """Lay out panels on a fresh grid of subplots, row by row, in the comparison style.

    Every subplot keeps its own y range, as regions differ by orders of magnitude. Axis titles
    are only shown along the left and bottom edges, where they do not run into the neighbours.
    """
    if not cells:
        return go.Figure(
            layout=dict(
                template=TEMPLATE,
                title_text=clean_title(title),
                height=SINGLE_PANEL_HEIGHT,
            )
        )
    n_rows = len(cells)
    n_columns = max(len(row) for row in cells)
    grid = [list(row) + [None] * (n_columns - len(row)) for row in cells]
    height = SINGLE_PANEL_HEIGHT if n_rows == 1 else 130 + PANEL_HEIGHT * n_rows
    fig = make_subplots(
        rows=n_rows,
        cols=n_columns,
        specs=[[{} if cell is not None else None for cell in row] for row in grid],
        subplot_titles=[cell.title for row in grid for cell in row if cell is not None],
        horizontal_spacing=0.07 if n_columns > 1 else 0.0,
        # room between the rows for the tick labels and subplot titles
        vertical_spacing=min(90 / height, 0.9 / (n_rows - 1)) if n_rows > 1 else 0.0,
    )
    bottom_rows = {
        column: max(row for row in range(n_rows) if grid[row][column] is not None)
        for column in range(n_columns)
        if any(grid[row][column] is not None for row in range(n_rows))
    }
    traces, trace_rows, trace_columns = [], [], []
    for row, cells_of_row in enumerate(grid):
        first_column = next(column for column, cell in enumerate(cells_of_row) if cell is not None)
        for column, panel in enumerate(cells_of_row):
            if panel is None:
                continue
            traces.extend(panel.traces)
            trace_rows.extend([row + 1] * len(panel.traces))
            trace_columns.extend([column + 1] * len(panel.traces))
            xaxis = dict(panel.xaxis)
            if row != bottom_rows[column]:
                xaxis.pop("title_text", None)
            yaxis = dict(panel.yaxis)
            if column != first_column:
                yaxis.pop("title_text", None)
            fig.update_xaxes(xaxis, row=row + 1, col=column + 1)
            fig.update_yaxes(yaxis, row=row + 1, col=column + 1)
    if traces:
        fig.add_traces(traces, rows=trace_rows, cols=trace_columns)
    fig.update_annotations(font=dict(size=13, color=INK))
    # ticks at 1, 2 and 5 of each decade, rather than a label on every digit
    fig.update_xaxes(dtick="D2", selector=dict(type="log"))
    fig.update_yaxes(dtick="D2", selector=dict(type="log"))
    has_log_x = any(
        panel.xaxis.get("type") == "log" for row in grid for panel in row if panel is not None
    )
    fig.update_layout(
        template=TEMPLATE,
        title=dict(text=clean_title(title), **_top_band(height)),
        height=height,
        # comparing values of the same year is the point; along GDP the runs' x values differ
        hovermode="closest" if has_log_x else "x unified",
    )
    return fig


def _top_band(height: int) -> dict[str, Any]:
    """Position in the band above the subplots, where the title and the run legend go."""
    return dict(y=1 - 16 / height, yref="container", yanchor="top")


# ── standard figures of the model visualizers ──────────────────────────────────

HEADLESS_OVERRIDES: dict[str, Any] = {
    "do_visualize": True,
    "do_show_figs": False,
    "do_save_figs": False,
    "do_save_figs_html": False,
    "plotting_engine": "plotly",
}
"""Visualization settings that make a visualizer produce its figures without showing or saving."""


def stored_fields(cfg: BaseModel) -> dict[str, Any]:
    """Field values a pydantic instance actually carries, recursively, as plain dicts.

    Configs unpickled from older runs lack the fields added to the schema since then (accessing
    them raises ``AttributeError``). Validating this dict again lets the current defaults fill
    the gaps.
    """
    fields: dict[str, Any] = {}
    for name in type(cfg).model_fields:
        if name not in cfg.__dict__:
            continue
        value = cfg.__dict__[name]
        fields[name] = stored_fields(value) if isinstance(value, BaseModel) else value
    return fields


def visualization_cfg(
    base: VisualizationCfg, plots: Mapping[str, bool] | None = None
) -> VisualizationCfg:
    """A copy of a run's visualization config that plots headlessly.

    Args:
        base: Visualization config of a run, usually ``run.model.visualizer.cfg``. Its class
            (e.g. ``SteelVisualizationCfg``) and plot settings are kept.
        plots: Plot groups to switch on or off, by field name (see :func:`plot_toggles`).
    """
    fields = stored_fields(base) | HEADLESS_OVERRIDES
    for name, info in type(base).model_fields.items():
        # plot groups added to the schema after the run was written get their default settings
        if name not in fields and _is_plot_group(info.annotation):
            fields[name] = {}
    for name, enabled in (plots or {}).items():
        if name not in type(base).model_fields:
            raise KeyError(f"Unknown plot group {name!r} for {type(base).__name__}.")
        fields[name] = {**fields.get(name, {}), "do_visualize": enabled}
    return type(base).model_validate(fields)


def _is_plot_group(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseVisualizationCfg)


def plot_toggles(cfg: VisualizationCfg) -> dict[str, bool]:
    """Which plot groups of a visualization config are switched on, by field name."""
    return {
        name: value.do_visualize
        for name in type(cfg).model_fields
        if isinstance(value := getattr(cfg, name, None), BaseVisualizationCfg)
    }


def standard_figures(run: LoadedRun, cfg: VisualizationCfg) -> dict[str, go.Figure]:
    """Re-plot the standard figures of a run, keyed by their file base name.

    Uses the model's own visualizer class with the given configuration, so exactly the figures a
    model run would show or save are produced -- including any added to the visualizer later --
    but nothing is shown or written. Use :func:`visualization_cfg` to derive ``cfg``.
    """
    model = run.model
    visualizer = type(model).VisualizerCls(cfg=cfg, display_names=type(model).DisplayNamesCls())
    renderer = pio.renderers.default  # constructing a visualizer changes the global renderer
    try:
        visualizer.visualize(model)
    finally:
        pio.renderers.default = renderer
    return dict(visualizer.figures)


def is_sankey(fig: go.Figure) -> bool:
    """Whether a figure is a Sankey diagram, which cannot be overlaid or differenced."""
    return any(trace.type == "sankey" for trace in fig.data)


# ── overlay and difference of runs ─────────────────────────────────────────────

REFERENCE_OPACITY = 0.3
"""Opacity of the reference run in an overlay, which is drawn as a faded ghost of the other run."""

REFERENCE_LINE_WIDTH = 6
"""Width of the reference run's lines in an overlay: wide enough to show the other run inside."""

LINE_WIDTH = 2

RUN_DASHES = ("dash", "dot", "dashdot", "longdash")
RUN_SYMBOLS = ("diamond", "square", "triangle-up", "cross")
"""Line styles and marker symbols of the third and further runs, in turn. The reference is told
apart as a ghost and the second run keeps the figure's own styles. Bars need neither: each run's
bars stand side by side, labelled with the run on a second level of the x axis."""

MAX_OVERLAID_SERIES = 4
"""Overlay subplots with more line series than this are split into one subplot per series.

Twelve regions of two runs in one subplot are a tangle; one subplot per region compares the two
runs of that region at a glance. See also :data:`MAX_OVERLAY_PANELS`.
"""

MAX_OVERLAY_PANELS = 48
"""Largest number of subplots an overlay is split into; figures that would need more keep their
layout (e.g. 13 materials in each of 12 regions)."""

SIGNIFICANT_DIGITS = 6
"""Merged figures carry values rounded to this many significant digits per trace.

The figures are for looking at, and full double precision would triple the size of an exported
report page (dozens of figures with hundreds of traces each).
"""


def _is_markers(trace) -> bool:
    return trace.type == "scatter" and trace.mode == "markers"


def _kind(traces: Iterable) -> str:
    """How traces are drawn, so the runs can be keyed alike: as "bar", "markers", "area" or, if
    mixed, "line"; a stack keeps its areas whatever else is drawn."""
    kinds = {
        (
            "bar"
            if trace.type == "bar"
            else (
                "area"
                if getattr(trace, "fill", None)
                else "markers" if _is_markers(trace) else "line"
            )
        )
        for trace in traces
    }
    if "area" in kinds:
        return "area"
    return kinds.pop() if len(kinds) == 1 else "line"


def _run_variant(index: int, variants: Sequence[str]) -> str | None:
    """Style forced onto the traces of the run at ``index`` (the reference being 0), taken in
    turn from ``variants`` such as :data:`RUN_DASHES`."""
    return variants[(index - 2) % len(variants)] if index > 1 else None


def _hover_name(trace, run: str) -> str:
    series = _series_name(trace)
    return f"{series} · {run}" if series else run


def _as_reference(trace, run: str) -> None:
    """Draw a trace of the reference run as a faded, wide ghost behind the other runs.

    Ghosts are solid whatever the line style, which the other runs' lines on top still show.
    """
    trace.update(name=_hover_name(trace, run))
    if trace.type != "scatter":
        trace.update(opacity=REFERENCE_OPACITY)
    elif trace.fill:
        # plotly does not apply the trace opacity to fills between traces
        color = trace.fillcolor or trace.line.color
        trace.update(fillcolor=_faded(color, REFERENCE_OPACITY), line_width=0)
    elif _is_markers(trace):
        trace.update(opacity=REFERENCE_OPACITY)
    else:
        trace.update(
            opacity=REFERENCE_OPACITY,
            line=dict(width=REFERENCE_LINE_WIDTH, dash="solid"),
        )


def _as_compared(trace, run: str, index: int) -> None:
    """Draw a trace of the run at ``index`` in its own style, on top of the reference.

    Lines are thin and markers have a ring in the surface colour, so they stay legible where they
    cross. Stacked areas become the outlines of their layers, as the reference shows the stack.
    """
    trace.update(name=_hover_name(trace, run))
    if trace.type != "scatter":
        return
    if _is_markers(trace):
        trace.update(marker=dict(size=8, line=dict(width=1.5, color=SURFACE)))
        if (symbol := _run_variant(index, RUN_SYMBOLS)) is not None:
            trace.update(marker_symbol=symbol)
        return
    trace.update(fill=None, line_width=LINE_WIDTH)
    if (dash := _run_variant(index, RUN_DASHES)) is not None:
        trace.update(line_dash=dash)


def _beside(trace, run: str) -> None:
    """Move bars to the place of their run, labelled on a second level of the x axis, so the
    bars of all runs stand side by side within each x item."""
    if trace.type == "bar":
        trace.update(x=[[str(item) for item in trace.x], [run] * len(trace.x)])


def _faded(color: str, alpha: float) -> str:
    """A CSS colour (hex, name or ``rgb(...)``) as ``rgba(...)`` with the given opacity."""
    if color.startswith("rgb"):
        red, green, blue = plc.unlabel_rgb(color)[:3]
    else:
        red, green, blue = (255 * channel for channel in mcolors.to_rgb(color))
    return f"rgba({red:.0f}, {green:.0f}, {blue:.0f}, {alpha})"


def _run_swatch(index: int, kind: str = "line") -> dict[str, Any]:
    """Legend style of the run at ``index`` in traces of the given kind (see :func:`_kind`): the
    reference as its ghost, the others as they are drawn."""
    if kind in ("bar", "markers"):
        symbol = "square" if kind == "bar" else _run_variant(index, RUN_SYMBOLS) or "circle"
        opacity = REFERENCE_OPACITY if index == 0 else 1.0
        marker = dict(color=SECONDARY_INK, size=10, symbol=symbol, opacity=opacity)
        return dict(mode="markers", marker=marker)
    if index > 0:
        dash = _run_variant(index, RUN_DASHES)
        return dict(mode="lines", line=dict(color=SECONDARY_INK, width=LINE_WIDTH, dash=dash))
    if kind == "area":
        faded = _faded(SECONDARY_INK, REFERENCE_OPACITY)
        return dict(mode="lines", fill="toself", fillcolor=faded, line=dict(width=0))
    return dict(
        mode="lines",
        opacity=REFERENCE_OPACITY,
        line=dict(color=SECONDARY_INK, width=REFERENCE_LINE_WIDTH),
    )


def _series_swatches(panels: Iterable[_Panel]) -> dict[str, dict[str, Any]]:
    """Legend style of each named series of the given subplots, by series name.

    A series is represented by a solid line if it has one, rather than its projection (dotted)
    or the marker of the last historic year. Taken as a snapshot, so restyling the traces
    afterwards leaves the legend alone.
    """
    grouped: dict[str, list] = {}
    for panel in panels:
        for name, traces in panel.series().items():
            grouped.setdefault(name, []).extend(traces)
    swatches = {}
    for name, traces in grouped.items():
        if not name:
            continue
        trace = min(
            traces,
            key=lambda trace: (
                _is_markers(trace),
                trace.type == "scatter" and (trace.line.dash or "solid") != "solid",
            ),
        )
        if trace.type == "bar":
            marker = dict(color=trace.marker.color, size=10, symbol="square")
            swatches[name] = dict(mode="markers", marker=marker)
        elif getattr(trace, "fill", None):
            color = trace.fillcolor or trace.line.color
            swatches[name] = dict(
                mode="lines",
                fill="toself",
                fillcolor=color,
                line=dict(color=color, width=0),
            )
        elif _is_markers(trace):
            swatches[name] = dict(mode="markers", marker=dict(color=trace.marker.color, size=8))
        else:
            swatches[name] = dict(mode="lines", line=dict(color=trace.line.color, width=LINE_WIDTH))
    return swatches


def _add_legends(
    fig: go.Figure,
    cells: Sequence[Sequence[_Panel | None]],
    runs: Mapping[str, dict[str, Any]],
    series: Mapping[str, dict[str, Any]],
) -> None:
    """Key the runs in the band above the subplots, and the series, if any, in the legend.

    Every entry toggles the traces in the legend group of its name. With series, the traces
    belong to the groups of their series, so the run key moves to a second legend whose entries
    cannot toggle anything.
    """
    if not cells:
        return
    run_legend = "legend2" if series else "legend"
    entries = [
        go.Scatter(
            x=[None],
            y=[None],
            name=name,
            legendgroup=name,
            legend=legend,
            showlegend=True,
            hoverinfo="skip",
            **style,
        )
        for legend, styles in ((run_legend, runs), ("legend", series))
        for name, style in styles.items()
    ]
    if runs:
        run_key = dict(orientation="h", x=1, xanchor="right", **_top_band(fig.layout.height))
        if series:
            run_key |= dict(itemclick=False, itemdoubleclick=False)
        fig.update_layout({run_legend: run_key})
    row, column = next(
        (row + 1, column + 1)
        for row, cells_of_row in enumerate(cells)
        for column, cell in enumerate(cells_of_row)
        if cell is not None
    )
    fig.add_traces(entries, rows=row, cols=column)


def overlay_figures(figures: Sequence[go.Figure], labels: Sequence[str]) -> go.Figure:
    """One figure showing the traces of all runs, the first one being the reference.

    The other runs are drawn in the figure's own style on top of the reference, which is drawn
    as a faded and wider ghost of the same colour: where the runs agree, the line runs through
    the middle of its ghost. Stacked areas of the reference stay filled, faded, and the other
    runs' layers are drawn as lines on top. From the third run on, each run gets a line style and
    marker symbol of its own (:data:`RUN_DASHES`, :data:`RUN_SYMBOLS`). Bars of the runs stand
    side by side, the reference's faded. A single run is drawn in its own style only.

    Subplots with more than :data:`MAX_OVERLAID_SERIES` line series (e.g. one line per region)
    are split into one subplot per series, as long as that takes at most
    :data:`MAX_OVERLAY_PANELS` subplots. A small grid of subplots then gets one column per
    original subplot and one row per series.
    """
    ghost = len(figures) > 1
    matched = _match_panels([_panels(fig) for fig in figures])
    series_per_group = [
        list(dict.fromkeys(name for panel in group for name in panel.series())) for group in matched
    ]
    kind = _kind(trace for group in matched for panel in group for trace in panel.traces)
    barmode = figures[0].layout.barmode
    is_stacked = barmode == "stack" or any(panel.is_stacked for group in matched for panel in group)
    split = (
        not is_stacked
        and max((len(names) for names in series_per_group), default=0) > MAX_OVERLAID_SERIES
        and sum(len(names) for names in series_per_group) <= MAX_OVERLAY_PANELS
    )
    # the legend shows each series in the compared runs' style
    swatches = _series_swatches([panel for group in matched for panel in group[::-1]])
    # with one series per subplot, the subplot titles tell the series apart and the legend is
    # free to toggle the runs; otherwise it identifies (and toggles) the series
    by_series = not split and len(swatches) > 1

    def merged(group: list[_Panel], title: str, series: str | None = None) -> _Panel:
        traces = []
        # the reference goes first: behind the other runs, and a stack stays one block of traces
        for index, (panel, run) in enumerate(zip(group, labels)):
            for trace in panel.traces:
                name = _series_name(trace)
                if series is not None and name != series:
                    continue
                if index == 0 and ghost:
                    _as_reference(trace, run)
                else:
                    _as_compared(trace, run, index)
                if ghost:
                    _beside(trace, run)
                trace.update(showlegend=False, legendgroup=name if by_series else run)
                traces.append(trace)
        return dataclasses.replace(group[0], title=title, traces=traces)

    def split_title(panel_title: str, series: str) -> str:
        return " · ".join(part for part in (panel_title, series) if part)

    cells: list[list[_Panel | None]]
    if split and 1 < len(matched) <= MAX_FACET_COLUMNS:
        all_series = list(dict.fromkeys(name for names in series_per_group for name in names))
        cells = [
            [
                (
                    merged(group, split_title(group[0].title, series), series)
                    if series in names
                    else None
                )
                for group, names in zip(matched, series_per_group)
            ]
            for series in all_series
        ]
    elif split:
        cells = _wrap(
            [
                merged(group, split_title(group[0].title, series), series)
                for group, names in zip(matched, series_per_group)
                for series in names
            ]
        )
    else:
        cells = _wrap([merged(group, group[0].title) for group in matched])

    fig = _grid_figure(cells, figures[0].layout.title.text or "").update_layout(barmode=barmode)
    runs = {label: _run_swatch(index, kind) for index, label in enumerate(labels)}
    _add_legends(fig, cells, runs if ghost else {}, swatches if by_series else {})
    return _compact(fig)


def aligned(reference: go.Figure, other: go.Figure) -> bool:
    """Whether two figures have the same traces (names, subplots, lengths), so they can be
    compared point by point."""
    if len(reference.data) != len(other.data):
        return False
    for first, second in zip(reference.data, other.data):
        first_y, second_y = getattr(first, "y", None), getattr(second, "y", None)
        if first_y is None or second_y is None or len(first_y) != len(second_y):
            return False
        if (first.type, first.name, first.xaxis, first.yaxis) != (
            second.type,
            second.name,
            second.xaxis,
            second.yaxis,
        ):
            return False
    return True


def difference_figure(
    figures: Sequence[go.Figure], labels: Sequence[str], relative: bool = True
) -> go.Figure | None:
    """Every run minus the first one, the reference, trace by trace in the reference's layout.

    Values are compared point by point, i.e. for the same year; where the x axis is not time
    (stock over GDP) the difference is drawn at the reference's x values. Stacked areas are
    un-stacked first, so each layer shows its own change, and drawn as lines; stacked bars
    are drawn side by side. With ``relative=True`` the difference is in percent of the reference
    and undefined (``NaN``) where the reference is zero. Runs are told apart as in
    :func:`overlay_figures`.

    Returns:
        The difference figure, or ``None`` if there is no run to compare with the reference or
        the figures do not all have the same traces.
    """
    reference, others = figures[0], figures[1:]
    if not others or not all(aligned(reference, other) for other in others):
        return None
    panels_per_run = []
    for other in others:
        fig = go.Figure(reference)
        for trace, (reference_layer, other_layer) in zip(fig.data, _trace_layers(reference, other)):
            difference = other_layer - reference_layer
            if relative:
                scale = np.where(reference_layer == 0, np.nan, reference_layer)
                with np.errstate(divide="ignore", invalid="ignore"):
                    difference = 100 * difference / scale
            trace.update(y=difference)
            if trace.type == "scatter":
                trace.update(fill=None)
        panels_per_run.append(_panels(fig))
    swatches = _series_swatches(panels_per_run[0])
    series = swatches if len(swatches) > 1 else {}

    panels = []
    for group in zip(*panels_per_run):
        traces = []
        for index, panel in enumerate(group, start=1):
            for trace in panel.traces:
                name = _series_name(trace)
                _as_compared(trace, labels[index], index)
                if trace.type == "bar":
                    # each item's bars of all runs share a place, as in a grouped bar chart
                    trace.update(offsetgroup=name or None)
                if len(others) > 1:
                    _beside(trace, labels[index])
                trace.update(showlegend=False, legendgroup=name if series else labels[index])
                traces.append(trace)
        unit = group[0].yaxis.get("title_text", "")
        ylabel = "difference [%]" if relative else f"Δ {unit}".strip()
        yaxis = group[0].yaxis | {"title_text": ylabel}
        panels.append(dataclasses.replace(group[0], traces=traces, yaxis=yaxis))
    cells = _wrap(panels)
    fig = _grid_figure(cells, reference.layout.title.text + " - Difference" or "").update_layout(
        barmode="group"
    )
    subtitle = f"{', '.join(labels[1:])} minus {labels[0]}"
    if relative:
        subtitle += f", in % of {labels[0]}"
    # a taller top band makes room for the subtitle
    fig.update_layout(title_subtitle_text=subtitle, margin_t=100)
    # zero is "no change", the line every trace is read against
    fig.update_yaxes(zeroline=True, zerolinecolor=SECONDARY_INK)
    kind = _kind(trace for panel in panels for trace in panel.traces)
    runs = {label: _run_swatch(index, kind) for index, label in enumerate(labels) if index > 0}
    _add_legends(fig, cells, runs if len(others) > 1 else {}, series)
    return _compact(fig)


def _trace_layers(reference: go.Figure, other: go.Figure) -> list[tuple[np.ndarray, np.ndarray]]:
    """The y values of every pair of traces of two aligned figures, as floats.

    Stacked areas hold cumulative values, so their traces are un-stacked into the layer each
    one adds, which is what a comparison of the traces is about.
    """
    layers = []
    previous: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
    for reference_trace, other_trace in zip(reference.data, other.data):
        reference_y = np.asarray(reference_trace.y, dtype=float)
        other_y = np.asarray(other_trace.y, dtype=float)
        reference_layer, other_layer = reference_y, other_y
        fill = getattr(reference_trace, "fill", None)
        subplot = (reference_trace.xaxis, reference_trace.yaxis)
        if fill == "tonexty" and subplot in previous:
            reference_layer = reference_y - previous[subplot][0]
            other_layer = other_y - previous[subplot][1]
        if fill:
            previous[subplot] = (reference_y, other_y)
        layers.append((reference_layer, other_layer))
    return layers


def _compact(fig: go.Figure) -> go.Figure:
    """Round the floating point data of every trace to :data:`SIGNIFICANT_DIGITS`, in place."""
    for trace in fig.data:
        if trace.type != "scatter":
            continue
        for axis in ("x", "y"):
            values = getattr(trace, axis)
            if values is None:
                continue
            array = np.asarray(values)
            if array.dtype.kind != "f":  # years and category labels are left alone
                continue
            trace.update({axis: _round_significant(array, SIGNIFICANT_DIGITS)})
    return fig


def _round_significant(values: np.ndarray, digits: int) -> np.ndarray:
    """Round to ``digits`` significant digits relative to the largest absolute value."""
    finite = values[np.isfinite(values) & (values != 0)]
    if finite.size == 0:
        return values
    magnitude = int(np.floor(np.log10(np.abs(finite).max())))
    return np.round(values, digits - 1 - magnitude)


# ── change detection ───────────────────────────────────────────────────────────

RELATIVE_TOLERANCE = 1e-9
"""Largest change of a series, relative to its largest reference value, that still counts as
unchanged: floating point noise of a refactor rather than a change of results."""

COMPARED_GROUPS = ("flow", "stock", "stock inflow")
"""Variable groups the change detection looks at by default."""

CHANGE_COLUMN = "change [%]"
YEAR_COLUMN = "year"

HEATMAP_CLIP_PERCENT = 50.0
"""Changes beyond this many percent share the colour of the extreme, keeping the scale readable."""

HEATMAP_ROW_HEIGHT = 22


def peak_change(reference: np.ndarray, other: np.ndarray) -> tuple[float, int]:
    """Largest change of a series, signed and in percent of the largest reference value.

    Scaling by the largest reference value rather than point by point keeps years with
    near-zero reference values from dominating.

    Returns:
        The change at the point of the largest absolute difference, and the index of that point.
        ``(nan, 0)`` if both series are zero throughout, ``(±inf, index)`` if only the reference
        is.
    """
    reference = np.asarray(reference, dtype=float)
    other = np.asarray(other, dtype=float)
    difference = other - reference
    if not np.isfinite(difference).any():
        return np.nan, 0
    index = int(np.nanargmax(np.abs(difference)))
    scale = np.nanmax(np.abs(reference))
    if scale > 0:
        return 100 * float(difference[index]) / float(scale), index
    if difference[index] == 0:
        return np.nan, index
    return math.copysign(math.inf, difference[index]), index


def is_changed(change: float) -> bool:
    """Whether a change in percent (see :func:`peak_change`) exceeds :data:`RELATIVE_TOLERANCE`."""
    return not np.isnan(change) and abs(change) > 100 * RELATIVE_TOLERANCE


def format_change(change: float, signed: bool = True) -> str:
    """A change in percent as text, e.g. ``"−32.1 %"``; ``signed=False`` drops the sign."""
    if np.isnan(change):
        return "unchanged"
    if np.isinf(change):
        return "new (reference is zero)"
    magnitude = abs(change)
    text = f"{magnitude:,.0f} %" if magnitude >= 1000 else f"{magnitude:.3g} %"
    if not signed:
        return text
    return ("−" if change < 0 else "+") + text


def regional_changes(
    reference: LoadedRun,
    other: LoadedRun,
    groups: Sequence[str] = COMPARED_GROUPS,
) -> pd.DataFrame:
    """The largest change of every variable in every region, when it happens and the values then.

    One row per variable and region, with the signed change in percent of the
    region's largest reference value (see :func:`peak_change`), the year of that change and the
    values of both runs in that year, in columns named after the runs. Variables whose shapes
    differ between the runs, e.g. because of another region mapping, are skipped with a warning.
    """
    rows = []
    for variable in common_variables([reference, other]):
        if variable.split(": ", 1)[0] not in groups:
            continue
        reference_array = get_array(reference, variable)
        letters = reference_array.dims.letters
        if "t" not in letters:
            continue
        kept = ("t", "r") if "r" in letters else ("t",)
        reference_summed = reference_array.sum_to(kept)
        other_summed = get_array(other, variable).sum_to(kept)
        if reference_summed.values.shape != other_summed.values.shape:
            warnings.warn(f"{variable!r} has different shapes in the two runs; skipped.")
            continue
        years = reference_summed.dims["t"].items
        series = _regional_series(reference_summed, other_summed)
        for region, (reference_values, other_values) in series.items():
            change, index = peak_change(reference_values, other_values)
            rows.append(
                {
                    VARIABLE_COLUMN: variable,
                    REGION_COLUMN: region,
                    CHANGE_COLUMN: change,
                    YEAR_COLUMN: int(years[index]),
                    reference.label: float(reference_values[index]),
                    other.label: float(other_values[index]),
                }
            )
    return pd.DataFrame(rows).reindex(
        columns=[
            VARIABLE_COLUMN,
            REGION_COLUMN,
            CHANGE_COLUMN,
            YEAR_COLUMN,
            reference.label,
            other.label,
        ]
    )


def _regional_series(
    reference: fd.FlodymArray, other: fd.FlodymArray
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Time series per region of two arrays over (time, region), the world total first."""
    time_axis = reference.dims.letters.index("t")
    reference_values = np.moveaxis(reference.values, time_axis, 0)
    other_values = np.moveaxis(other.values, time_axis, 0)
    if reference_values.ndim == 1:
        return {WORLD: (reference_values, other_values)}
    series = {WORLD: (reference_values.sum(axis=1), other_values.sum(axis=1))}
    for index, region in enumerate(reference.dims["r"].items):
        series[str(region)] = (reference_values[:, index], other_values[:, index])
    return series


@dataclass(frozen=True)
class ChangeVerdict:
    """How much two runs differ, boiled down to what a PR comment can carry."""

    n_variables: int
    n_changed: int
    largest_variable: str | None = None
    largest_change: float = np.nan
    """Signed change in percent, see :func:`peak_change`."""
    largest_region: str | None = None
    largest_year: int | None = None

    @property
    def identical(self) -> bool:
        """Whether no variable changed beyond :data:`RELATIVE_TOLERANCE` in any region."""
        return self.n_changed == 0

    def as_markdown(self) -> str:
        """One line of markdown for the PR comment, with relative numbers only."""
        if self.identical:
            return (
                f"**numerically identical** ({self.n_variables} variables agree "
                f"to within {RELATIVE_TOLERANCE:g} of their largest value)"
            )
        return (
            f"**{self.n_changed} of {self.n_variables} variables "
            f"changed**, largest `{self.largest_variable}` with "
            f"**{format_change(self.largest_change)}** "
            f"({self.largest_region}, {self.largest_year})"
        )


def summarize_changes(changes: pd.DataFrame) -> ChangeVerdict:
    """Count the variables that changed in any region and name the largest change.

    Args:
        changes: Output of :func:`regional_changes`.
    """
    n_variables = int(changes[VARIABLE_COLUMN].nunique())
    changed = changes[changes[CHANGE_COLUMN].map(is_changed)]
    if changed.empty:
        return ChangeVerdict(n_variables=n_variables, n_changed=0)
    largest = changed.loc[changed[CHANGE_COLUMN].abs().idxmax()]
    return ChangeVerdict(
        n_variables=n_variables,
        n_changed=int(changed[VARIABLE_COLUMN].nunique()),
        largest_variable=str(largest[VARIABLE_COLUMN]),
        largest_change=float(largest[CHANGE_COLUMN]),
        largest_region=str(largest[REGION_COLUMN]),
        largest_year=int(largest[YEAR_COLUMN]),
    )


def figure_change(reference: go.Figure, other: go.Figure) -> float | None:
    """Largest change of any trace of a figure, in percent of the trace's largest reference
    value; ``None`` if the figures do not have the same traces (see :func:`aligned`)."""
    if not aligned(reference, other):
        return None
    changes = [
        abs(peak_change(reference_layer, other_layer)[0])
        for reference_layer, other_layer in _trace_layers(reference, other)
    ]
    return max((change for change in changes if not np.isnan(change)), default=0.0)


def section_title(name: str, change: float | None) -> str:
    """Heading of a figure's report section, carrying how much the figure changed."""
    if change is None:
        return f"{name} — traces differ"
    if not is_changed(change):
        return name
    if np.isinf(change):
        return f"{name} — values where the reference has none"
    return f"{name} — max Δ {format_change(change, signed=False)}"


def sorted_regions(regions: list[str]) -> list[str]:
    """Return the list of regions sorted with 'World' first, then alphabetically."""
    return sorted(regions, key=lambda r: (r != WORLD, r))


def change_heatmap(
    changes: pd.DataFrame,
    clip: float = HEATMAP_CLIP_PERCENT,
) -> go.Figure:
    """Scorecard of the changed variables (rows) by region (columns).

    Cells show the signed change at the year of the largest absolute change, in percent of the
    region's largest reference value, on a diverging scale around zero clipped at ``±clip``.
    Only the ``max_rows`` variables that changed most are shown.
    """
    if changes.empty:
        return go.Figure(layout={"title": "No changes"})

    values = (
        changes.pivot(index=VARIABLE_COLUMN, columns=REGION_COLUMN, values=CHANGE_COLUMN)
        .sort_values(by="World", key=abs, ascending=False, kind="stable")
        .reindex(columns=sorted_regions(changes[REGION_COLUMN].unique()))
    )
    years = changes.pivot(index=VARIABLE_COLUMN, columns=REGION_COLUMN, values=YEAR_COLUMN).reindex(
        index=values.index,
        columns=values.columns,
    )
    hover_text = [
        [
            "" if np.isnan(change) else f"{format_change(change)} in {int(year)}"
            for change, year in zip(value_row, year_row)
        ]
        for value_row, year_row in zip(values.to_numpy(), years.to_numpy())
    ]
    fig = go.Figure(
        go.Heatmap(
            z=np.clip(values.to_numpy(dtype=float), -clip, clip),
            x=values.columns.tolist(),
            y=values.index.tolist(),
            zmid=0,
            zmin=-clip,
            zmax=clip,
            colorscale="RdBu_r",
            xgap=1,
            ygap=1,
            customdata=hover_text,
            hovertemplate="<b>%{y}</b><br>%{x}: %{customdata}<extra></extra>",
            hoverongaps=False,
            colorbar={"title": "change", "ticksuffix": " %", "thickness": 12},
        )
    )
    height = 150 + HEATMAP_ROW_HEIGHT * len(values.index)
    fig.update_layout(
        template=TEMPLATE,
        height=height,
        xaxis={"side": "top", "showgrid": False, "showline": False, "ticks": ""},
        yaxis={
            "autorange": "reversed",
            "showgrid": False,
            "automargin": True,
            "ticks": "",
        },
    )
    return fig
