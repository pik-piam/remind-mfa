"""
compare_runs_EU.py
==================

Overlay several REMIND-MFA model runs (one pickle each) in a single set of
comparison figures, focused on the EU region.

How it works
------------
1. Load N model pickles and stack every flow / stock / parameter array along a
   new "Run" dimension (:func:`build_combined_mfa`).
2. Build a custom ``ComparisonVisualizer`` (subclass of the model's
   ``CommonVisualizer``) whose plotting methods overlay all runs in the same
   figures, using "Run" as the line-colour dimension.
3. Everything that differs between **steel** and **plastics** is captured once,
   declaratively, in a :class:`ModelConfig` (see ``MODEL_CONFIGS``). The
   plotting methods themselves are model-agnostic — they read the config.

Scenario model
--------------
Each run is identified by a *group* and a *trade* variant:

* **steel** — group = circular-economy strategy (Downsizing, Redesign, …).
  Each strategy has two *ambitions* (Conservative, Highly Ambitious) drawn as a
  filled band, plus a separate "Baseline" run drawn as a grey reference line.
  Trade variant (default vs ``fix_supply``) is encoded as solid vs dashed.
* **plastics** — group = circularity scenario ``S1``, ``S2``, plus a separate
  ``Baseline`` run (formerly ``S0``). There are **no ambitions**, so each
  scenario is a single line. The Baseline is drawn as a grey reference line on
  top (as for steel) and is the reference for the Δ-net-imports plot.

Every figure draws a dashed vertical line at the last historical year and uses
``x_start_year`` / ``x_end_year`` (from the config) as the time-axis range.

Custom runs
-----------
In addition to the scenario runs above, arbitrary extra pickles can be overlaid
with ``--custom``. These are *not* parsed into the scenario group/ambition/trade
structure; they are simply drawn as plain solid lines labelled by their pickle
stem (in a distinct colour palette), on top of the scenario figures.

Usage
-----
    python scripts/compare_runs_EU.py --model steel  [run_stem ...]
    python scripts/compare_runs_EU.py --model plastics [run_stem ...]
    python scripts/compare_runs_EU.py --model plastics S1 S2 --custom my_run other_run

With no run stems given, an interactive checkbox picker is shown (and, after the
scenario runs are chosen, a second picker for optional custom runs).
"""

import pickle
import pathlib
import sys
import copy
import argparse
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import flodym as fd
import questionary
import plotly.colors as plc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── CLI / paths ──────────────────────────────────────────────────────────────

DIRECTORIES = {
    "plastics": "data/plastics/output/transience/pickle",
    "steel":    "data/steel/output/transience/pickle",
}

RUN_DIM_LETTER = "X"
RUN_DIM_NAME   = "Run"


def _parse_args():
    p = argparse.ArgumentParser(description="Compare multiple model runs visually.")
    p.add_argument("runs", nargs="*", help="Scenario run stems (no .pickle extension)")
    p.add_argument("--model", default="steel", choices=list(DIRECTORIES),
                   help="Which model type to compare (default: steel)")
    p.add_argument("--custom", nargs="*", default=None,
                   help="Extra run stems/paths drawn as plain lines labelled by file name. "
                        "Not folded into the scenario structure.")
    return p.parse_args()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Model configuration — the single place where steel and plastics differ.   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass(frozen=True)
class MarketSpec:
    """A trade market plus the optional good / material slice we focus on."""
    name: str
    good: Optional[str] = None
    material: Optional[str] = None


@dataclass(frozen=True)
class DependencyPanel:
    """A market whose net imports are divided by a demand quantity.

    ``demand`` is either ``"stock_inflow"`` (``in_use`` stock inflow) or
    ``"flow:<flow name>"``. The good/material slice is taken from ``market``.
    """
    market: MarketSpec
    demand: str


@dataclass(frozen=True)
class DemandPanel:
    """A standalone demand time series shown in the 'demands' figure."""
    title: str
    source: str                     # "stock_inflow" or "flow:<name>"
    good: Optional[str] = None
    material: Optional[str] = None


@dataclass(frozen=True)
class FlowPlot:
    """A single overlaid flow figure (one line per run)."""
    source: str                     # "stock_inflow" or "flow:<name>"
    name: str
    subplot_dim: Optional[str] = None
    good: Optional[str] = None
    material: Optional[str] = None


@dataclass(frozen=True)
class TradeOverlay:
    """An external cs4r time series overlaid on one market's trade figure.

    Used to compare an auxiliary flow (e.g. traded recyclate, produced by
    ``map_EU-MFA_flows.py``) against that market's imports/exports. One dotted
    line is drawn per scenario in ``scenarios``.
    """
    market: str                      # trade market figure to draw on (e.g. "primary")
    label: str                       # legend prefix (e.g. "Traded recyclate")
    filename: str                    # cs4r file name within each scenario dir
    base_dir: str                    # dir holding the per-scenario subdirs
    scenarios: dict                  # {legend suffix: scenario subdir}
    region: Optional[str] = None
    material: Optional[str] = None
    good: Optional[str] = None
    sign: float = -1.0                # multiply values (use -1 to align with exports)


@dataclass(frozen=True)
class ModelConfig:
    """Everything that differs between steel and plastics for these figures."""
    name: str
    region: str
    x_start_year: int               # left edge for most time-axis plots
    x_end_year: int                 # right edge for all time-axis plots
    delta_start_year: int           # left edge for the Δ-net-imports plot

    # Scenario groups (steel strategies / plastics scenarios) and their styling.
    group_order: list[str]
    display: dict[str, str]
    color: dict[str, str]
    fill_solid: dict[str, str]
    fill_dashed: dict[str, str]
    use_ambition_bands: bool        # steel: True (Conservative→HA band); plastics: False
    baseline_group: str             # group used as Δ reference + for baseline-only plots
    show_baseline_line: bool        # draw a separate grey baseline line on top (steel only)
    color_baseline: str

    # Market display names (e.g. steel "primary" = "Primary steel").
    market_display: dict[str, str]

    # Markets / panels used by the various figures.
    markets: list[MarketSpec]
    dependency_panels: list[DependencyPanel]
    demand_panels: list[DemandPanel]
    demand_title: str
    region_panels: list[DependencyPanel]   # for stacked-by-region + trade-mechanism
    flow_plots: list[FlowPlot]
    csv_flows: list[tuple[str, str]]        # (label, source) for CSV export

    # Filters for the raw per-market trade overlay figure.
    trade_good_filters: dict[str, str] = field(default_factory=dict)
    trade_material_filters: dict[str, str] = field(default_factory=dict)

    # External cs4r series overlaid on specific market trade figures.
    trade_overlays: list = field(default_factory=list)


# Shared colour palette (Plotly default qualitative colours).
_GREY   = "#7f7f7f"
_BLUE   = "#1f77b4"
_ORANGE = "#ff7f0e"
_GREEN  = "#2ca02c"
_RED    = "#d62728"
_PURPLE = "#9467bd"

# Distinct palette for custom (non-scenario) runs, kept clear of the scenario
# colours above so custom overlays stand out.
_CUSTOM_COLORS = ["#17becf", "#bcbd22", "#e377c2", "#8c564b", "#393b79", "#000000"]


def _fill(hex_color: str, alpha: float) -> str:
    """Convert a ``#rrggbb`` colour to an ``rgba(...)`` string with given alpha."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


# ── steel config ───────────────────────────────────────────────────────────

_STEEL_GROUPS = {
    "Downsizing":      _BLUE,
    "Redesign":        _ORANGE,
    "Remanufacturing": _GREEN,
    "Combined":        _RED,
    "AHSS":            _PURPLE,
}
_STEEL_DISPLAY = {**{g: g for g in _STEEL_GROUPS}, "AHSS": "AHSS & HSS", "Baseline": "Baseline"}

STEEL_CONFIG = ModelConfig(
    name="steel",
    region="EUR",
    x_start_year=2000,
    x_end_year=2050,
    delta_start_year=2026,
    group_order=list(_STEEL_GROUPS),
    display=_STEEL_DISPLAY,
    color={**_STEEL_GROUPS, "Baseline": _GREY},
    fill_solid={g: _fill(c, 0.20) for g, c in {**_STEEL_GROUPS, "Baseline": _GREY}.items()},
    fill_dashed={g: _fill(c, 0.08) for g, c in {**_STEEL_GROUPS, "Baseline": _GREY}.items()},
    use_ambition_bands=True,
    baseline_group="Baseline",
    show_baseline_line=True,
    color_baseline=_GREY,
    market_display={
        "indirect": "Steel in goods",
        "steel":    "Intermediate steel products",
    },
    markets=[
        MarketSpec("indirect", good="Transport"),
        MarketSpec("steel"),
    ],
    dependency_panels=[
        DependencyPanel(MarketSpec("indirect", good="Transport"), "stock_inflow"),
        DependencyPanel(MarketSpec("steel"), "flow:ip_market => fabrication"),
    ],
    demand_panels=[
        DemandPanel("Steel in goods — Transport", "stock_inflow", good="Transport"),
        DemandPanel("Intermediate steel products", "flow:ip_market => fabrication"),
    ],
    demand_title="Steel demands",
    region_panels=[
        DependencyPanel(MarketSpec("indirect", good="Transport"), "stock_inflow"),
        DependencyPanel(MarketSpec("steel"), "flow:ip_market => fabrication"),
    ],
    flow_plots=[
        FlowPlot("stock_inflow", "Stock inflow", subplot_dim="Good"),
        FlowPlot("flow:fabrication => good_market", "Good supply", subplot_dim="Good"),
        FlowPlot("flow:ip_market => fabrication", "Steel demand", subplot_dim=None),
    ],
    csv_flows=[
        ("inflow", "stock_inflow"),
        ("supply_by_good", "flow:fabrication => good_market"),
        ("steel_demand", "flow:ip_market => fabrication"),
    ],
    trade_good_filters={"indirect": "Transport"},
)

# ── plastics config ──────────────────────────────────────────────────────────
# Baseline (formerly "S0") = baseline scenario, S1 / S2 = circularity strategies.
# No ambitions. The Baseline is drawn as a grey line on top (as for steel).
# We focus on PET in packaging (final-goods market) and PET in the primary market.

_PL_GROUPS = {"S1": _BLUE, "S2": _ORANGE}              # circularity scenarios (coloured lines)
_PL_ALL = {**_PL_GROUPS, "Baseline": _GREY}           # incl. the grey baseline

PLASTICS_CONFIG = ModelConfig(
    name="plastics",
    region="EU27+3",
    x_start_year=2000,
    x_end_year=2050,
    delta_start_year=2018,
    group_order=list(_PL_GROUPS),
    display={g: g for g in _PL_ALL},
    color=dict(_PL_ALL),
    fill_solid={g: _fill(c, 0.20) for g, c in _PL_ALL.items()},
    fill_dashed={g: _fill(c, 0.08) for g, c in _PL_ALL.items()},
    use_ambition_bands=False,
    baseline_group="Baseline",
    show_baseline_line=True,
    color_baseline=_GREY,
    market_display={
        "primary": "Primary",
        "final":   "Final goods",
        "waste":   "Waste",
    },
    markets=[
        MarketSpec("final", good="Packaging", material="PET"),
        MarketSpec("primary", material="PET"),
    ],
    dependency_panels=[
        DependencyPanel(MarketSpec("final", good="Packaging", material="PET"), "stock_inflow"),
        DependencyPanel(MarketSpec("primary", material="PET"), "flow:primary_market => fabrication"),
    ],
    demand_panels=[
        DemandPanel("Final goods — PET × Packaging", "stock_inflow", good="Packaging", material="PET"),
        DemandPanel("Primary — PET", "flow:primary_market => fabrication", material="PET"),
    ],
    demand_title="PET demands",
    region_panels=[
        DependencyPanel(MarketSpec("final", good="Packaging", material="PET"), "stock_inflow"),
        DependencyPanel(MarketSpec("primary", material="PET"), "flow:primary_market => fabrication"),
    ],
    flow_plots=[
        FlowPlot("stock_inflow", "Stock inflow — PET", material="PET", subplot_dim="Good"),
        FlowPlot("flow:fabrication => good_market", "Good supply — PET", material="PET", subplot_dim="Good"),
        FlowPlot("flow:primary_market => fabrication", "PET demand", material="PET"),
    ],
    csv_flows=[
        ("demand", "flow:good_market => use"),
        ("stock_outflow", "flow:use => eol"),
        ("collected_eol", "flow:eol => collected"),
        ("recycled_mech", "flow:collected => reclmech"),
    ],
    trade_good_filters={"final": "Packaging"},
    trade_material_filters={"final": "PET", "primary": "PET", "waste": "PET"},
    trade_overlays=[
        TradeOverlay(
            market="primary",
            label="Traded recyclate",
            filename="pl_traded_recyclate_EU-MFA.cs4r",
            base_dir="../remind_mfa_data/transience",
            scenarios={
                "S0": "CE-PET_fd_plastics_S0",
                "S1": "CE-PET_fd_plastics_S1",
                "S2": "CE-PET_fd_plastics_S2",
            },
            region="EU27+3",
            material="PET",
            good="Packaging",
        ),
    ],
)

MODEL_CONFIGS = {"steel": STEEL_CONFIG, "plastics": PLASTICS_CONFIG}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Loading and stacking model pickles                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def pick_files(directory: pathlib.Path, runs: Optional[list[str]]) -> list[pathlib.Path]:
    available = sorted(directory.glob("model_*.pickle"))
    if not available:
        raise FileNotFoundError(f"No model_*.pickle files found in {directory}")
    if runs:
        return [directory / f"{r}.pickle" for r in runs]
    chosen = questionary.checkbox(
        "Select runs to compare:",
        choices=[f.name for f in available],
        validate=lambda s: True if s else "Select at least one file.",
    ).ask()
    if not chosen:
        raise ValueError("No files selected.")
    return [directory / name for name in chosen]


def _resolve_path(run: str, directory: pathlib.Path) -> pathlib.Path:
    """Turn a stem or path into a concrete pickle path under ``directory``."""
    p = pathlib.Path(run)
    if not p.suffix:
        p = p.with_suffix(".pickle")
    if not p.is_absolute():
        p = directory / p
    return p


def pick_custom_files(directory: pathlib.Path, custom_args: Optional[list[str]],
                      exclude: list[pathlib.Path]) -> list[pathlib.Path]:
    """Resolve custom run paths.

    * ``custom_args`` given (``--custom a b``) → resolve those stems/paths.
    * ``custom_args is None`` (flag omitted) and we are interactive (no scenario
      stems on the CLI) → offer a second checkbox of the remaining pickles.
    * otherwise → no custom runs.
    """
    if custom_args:
        return [_resolve_path(r, directory) for r in custom_args]
    if custom_args is not None:
        return []  # --custom passed with no values
    # interactive fallback: only when the scenario picker was interactive
    available = sorted(directory.glob("model_*.pickle"))
    excluded = {p.resolve() for p in exclude}
    remaining = [f for f in available if f.resolve() not in excluded]
    if not remaining:
        return []
    chosen = questionary.checkbox(
        "Select optional custom runs (plain lines, labelled by file name):",
        choices=[f.name for f in remaining],
    ).ask()
    return [directory / name for name in (chosen or [])]


def custom_label(stem: str, model: str) -> str:
    """Short label for a custom run: the pickle stem minus ``model_<model>_``."""
    parts = [p for p in stem.split("_") if p not in ("model", model)]
    return "_".join(parts) or stem


def load_cs4r_series(path: pathlib.Path, region=None, material=None, good=None,
                     sign: float = 1.0):
    """Read a cs4r flow file and return ``(years, values)`` summed over Time.

    cs4r layout: comment lines start with ``*``; the data is comma-separated with
    no header. The value is always the last column; the leading columns are
    ``Time, Region, [Material], [Good]`` (column count varies by flow).
    """
    raw = pd.read_csv(path, comment="*", header=None)
    ncol = raw.shape[1]
    if ncol == 5:
        raw.columns = ["Time", "Region", "Material", "Good", "value"]
    elif ncol == 4:
        raw.columns = ["Time", "Region", "Good", "value"]
    elif ncol == 3:
        raw.columns = ["Time", "Region", "value"]
    else:
        raise ValueError(f"Unexpected cs4r column count {ncol} in {path}")

    if region is not None and "Region" in raw:
        raw = raw[raw["Region"] == region]
    if material is not None and "Material" in raw:
        raw = raw[raw["Material"] == material]
    if good is not None and "Good" in raw:
        raw = raw[raw["Good"] == good]

    series = raw.groupby("Time")["value"].sum().sort_index()
    return series.index.to_numpy(), sign * series.to_numpy()


def load_models(paths: list[pathlib.Path]):
    models = []
    for p in paths:
        with p.open("rb") as fh:
            models.append(pickle.load(fh))
    return models


def _stack(arrays: list[fd.FlodymArray], run_dim: fd.Dimension) -> fd.FlodymArray:
    """Stack FlodymArrays along a new trailing Run dimension."""
    return fd.flodym_array_stack(arrays, dimension=run_dim)


def build_combined_mfa(models, run_dim: fd.Dimension) -> fd.MFASystem:
    """Return a copy of the base MFA where every flow/stock/parameter array has
    been stacked along ``run_dim`` (appended as the last dimension)."""
    mfas = [m.future_mfa for m in models]
    base = mfas[0]

    new_dims = fd.DimensionSet(dim_list=list(base.dims.dim_list) + [run_dim])

    new_flows = {}
    for name in base.flows:
        stacked = _stack([mfa.flows[name] for mfa in mfas], run_dim)
        new_flows[name] = base.flows[name].model_copy(
            update={"values": stacked.values, "dims": stacked.dims}
        )

    new_stocks = {}
    for name in base.stocks:
        s0 = base.stocks[name]
        new_stock_dims = fd.DimensionSet(dim_list=list(s0.dims.dim_list) + [run_dim])
        updates: dict = {"dims": new_stock_dims}
        for attr in ("stock", "inflow", "outflow"):
            arrs = [getattr(mfa.stocks[name], attr) for mfa in mfas]
            if arrs[0] is not None:
                updates[attr] = _stack(arrs, run_dim)
        new_stocks[name] = s0.model_copy(update=updates)

    new_params = {}
    for name in base.parameters:
        try:
            new_params[name] = _stack([mfa.parameters[name] for mfa in mfas], run_dim)
        except Exception:
            new_params[name] = base.parameters[name]

    from remind_mfa.common.trade import Trade, TradeSet
    new_trade_set = None
    if base.trade_set is not None:
        new_markets = {}
        for name, trade in base.trade_set.markets.items():
            stacked_imp = _stack([mfa.trade_set.markets[name].imports for mfa in mfas], run_dim)
            stacked_exp = _stack([mfa.trade_set.markets[name].exports for mfa in mfas], run_dim)
            new_markets[name] = Trade.model_construct(imports=stacked_imp, exports=stacked_exp)
        new_trade_set = TradeSet.model_construct(markets=new_markets)

    return base.model_copy(
        update={"dims": new_dims, "flows": new_flows, "stocks": new_stocks,
                "parameters": new_params, "trade_set": new_trade_set}
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Run-label parsing                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# A run label encodes a group, an ambition (steel only) and a trade variant.
# ``scenario_map`` is a nested dict: {group: {ambition: {trade: run_index}}}.

_STRATEGY_TOKENS = ["Downsizing", "Redesign", "Remanufacturing", "Combined", "AHSS",
                    "Baseline", "S2", "S1", "S0"]
_AMBITIONS = ["Conservative", "Highly Ambitious"]


def _trade_variant(label: str) -> str:
    if "fix_supply_alpha0" in label or "fix_supply_α0" in label:
        return "fix_supply_alpha0"
    if "fix_supply_alpha1" in label or "fix_supply_α1" in label:
        return "fix_supply_alpha1"
    return "default"


def make_short_label(stem: str, model: str) -> str:
    """Convert a pickle file stem to a short, human-readable run label."""
    trade = _trade_variant(stem)
    trade_suffix = {"fix_supply_alpha0": " fix_supply_α0",
                    "fix_supply_alpha1": " fix_supply_α1",
                    "default": ""}[trade]

    if model == "plastics":
        # S1 / S2 = circularity scenarios; everything else (incl. S0) is the Baseline.
        group = next((s for s in ("S2", "S1") if s in stem), "Baseline")
        return f"{group}{trade_suffix}"

    strategy = next((s for s in _STRATEGY_TOKENS if s in stem), "Unknown")
    if strategy == "Baseline":
        return f"Baseline{trade_suffix}"
    ambition = "HA" if ("Highly_Ambitious" in stem or "Highly_mbitious" in stem) else "Cons"
    return f"{strategy} {ambition}{trade_suffix}"


def parse_run_labels(labels: list[str]) -> dict:
    """Return {group: {ambition: {trade: run_index}}} from run labels."""
    result: dict = {}
    for i, label in enumerate(labels):
        trade = _trade_variant(label)
        group = next((s for s in _STRATEGY_TOKENS if s in label), "Unknown")
        if group == "Baseline":
            ambition = "Baseline"
        elif any(tok in label for tok in ("Highly Ambitious", "Highly_Ambitious",
                                          "Highly_mbitious", " HA ")) or label.endswith(" HA"):
            ambition = "Highly Ambitious"
        else:
            ambition = "Conservative"
        result.setdefault(group, {}).setdefault(ambition, {})[trade] = i
    return result


def _fs_index(trade_dict: dict) -> Optional[int]:
    """Return the fix_supply index from a trade dict, preferring alpha1."""
    for k in ("fix_supply_alpha1", "fix_supply_alpha0"):
        if k in trade_dict:
            return trade_dict[k]
    return None


def _baseline_index(scenario_map: dict, cfg: ModelConfig) -> Optional[int]:
    """Run index of the default-trade run of the baseline group, or None."""
    group = scenario_map.get(cfg.baseline_group, {})
    for ambition in group.values():
        if "default" in ambition:
            return ambition["default"]
    for ambition in group.values():           # fallback: any trade variant
        for idx in ambition.values():
            return idx
    return None


def market_title(market_display: dict, name: str,
                 good: Optional[str] = None, material: Optional[str] = None) -> str:
    """Human-readable market title, optionally annotated with material/good."""
    base = market_display.get(name, name)
    parts = [p for p in (material, good) if p is not None]
    return f"{base} — {' × '.join(parts)}" if parts else base


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Comparison visualizer factory                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def make_comparison_visualizer(cfg: ModelConfig, run_dim_name: str):
    """Build a ``ComparisonVisualizer`` class bound to one model's config."""
    from remind_mfa.common.common_visualization import CommonVisualizer as BaseVis

    RUN = run_dim_name

    class ComparisonVisualizer(BaseVis):
        """Visualizer that overlays multiple runs by injecting a Run dimension.

        All model-specific behaviour comes from the captured ``cfg``; the methods
        below contain no ``if model == ...`` branching.
        """

        # ── entry point ────────────────────────────────────────────────────
        def visualize(self, model):
            mfa = model.future_mfa
            run_letter = mfa.dims[RUN].letter
            run_labels = list(mfa.dims[RUN].items)
            # last historical year — marked with a dashed vertical line in every figure
            self._last_hist_year = model.historic_mfa.dims["h"].items[-1]

            # 1. raw per-market trade overlay (one coloured line per run)
            self.visualize_trade(
                mfa,
                linecolor_dims={n: RUN for n in mfa.trade_set.markets},
                subplot_dims={n: None for n in mfa.trade_set.markets},
                good_filters=cfg.trade_good_filters,
                material_filters=cfg.trade_material_filters,
            )

            # 2. individual flow figures
            self._visualize_flows(mfa)

            # 3. scenario-comparison figures
            self.visualize_delta_net_imports(mfa, run_labels, run_letter)
            self.visualize_import_dependency(mfa, run_labels, run_letter)
            self.visualize_gross_trade(mfa, run_labels, run_letter)
            self.visualize_net_imports(mfa, run_labels, run_letter)
            self.visualize_global_trade_stacked(mfa, run_labels, run_letter)
            self.visualize_trade_mechanism(mfa, run_labels, run_letter)
            self.visualize_demands(mfa, run_labels, run_letter)

        # ── small array helpers ────────────────────────────────────────────
        @staticmethod
        def _sel(arr: fd.FlodymArray, sel: dict) -> dict:
            """Keep only selection keys whose dimension exists on ``arr``."""
            return {k: v for k, v in sel.items() if k in arr.dims.letters}

        def _resolve(self, mfa, source: str) -> fd.FlodymArray:
            """Resolve a ``"stock_inflow"`` / ``"flow:<name>"`` source string."""
            if source == "stock_inflow":
                return mfa.stocks["in_use"].inflow
            return mfa.flows[source[len("flow:"):]]

        def _has_source(self, mfa, source: str) -> bool:
            return source == "stock_inflow" or source[len("flow:"):] in mfa.flows

        def _present_markets(self, mfa, specs: list[MarketSpec]) -> list[MarketSpec]:
            return [s for s in specs if s.name in mfa.trade_set.markets]

        def _net_imports(self, mfa, spec: MarketSpec, run_letter) -> np.ndarray:
            """Net imports (imports − exports) for one market, shape (n_t, n_run)."""
            trade = mfa.trade_set.markets[spec.name]
            sel = self._sel(trade.imports, {"r": cfg.region, "g": spec.good, "m": spec.material})
            sel = {k: v for k, v in sel.items() if v is not None}
            return (trade.imports - trade.exports)[sel].sum_to(["t", run_letter]).values

        def _demand_matrix(self, mfa, source, run_letter,
                           good=None, material=None) -> np.ndarray:
            """Summed demand series over (t, run), filtered to good/material."""
            arr = self._resolve(mfa, source)
            sel = self._sel(arr, {"r": cfg.region, "g": good, "m": material})
            sel = {k: v for k, v in sel.items() if v is not None}
            return arr[sel].sum_to(["t", run_letter]).values

        # last historical year; set in ``visualize`` before any figure is drawn
        _last_hist_year = None

        # Custom (non-scenario) runs: list of (run_index, label), set in ``main``.
        # These are drawn as plain solid lines and excluded from the scenario map.
        _custom_runs: list = []
        _custom_indices: set = set()

        def _scenario_map(self, run_labels: list[str]) -> dict:
            """``parse_run_labels`` with any custom-run indices removed, so custom
            runs are never folded into a scenario group/ambition/trade."""
            smap = parse_run_labels(run_labels)
            if not self._custom_indices:
                return smap
            cleaned: dict = {}
            for group, ambitions in smap.items():
                new_ambitions = {}
                for ambition, trades in ambitions.items():
                    kept = {t: i for t, i in trades.items() if i not in self._custom_indices}
                    if kept:
                        new_ambitions[ambition] = kept
                if new_ambitions:
                    cleaned[group] = new_ambitions
            return cleaned

        def _draw_custom_lines(self, fig, col, times, signed_vals, scale, legend_shown):
            """Overlay each custom run as a plain solid line.

            ``signed_vals`` is a list of ``(sign, matrix)`` (one entry for most
            figures; ``[(1, imp), (-1, exp)]`` for gross trade). Each matrix is
            shape (n_t, n_run); the run column is selected by the custom index.
            """
            for ci, (idx, label) in enumerate(self._custom_runs):
                color = _CUSTOM_COLORS[ci % len(_CUSTOM_COLORS)]
                show = col == 1 and label not in legend_shown
                for sign, mat in signed_vals:
                    self._add_line(fig, col, times, sign * mat[:, idx] / scale,
                                   color, label, show, width=2)
                    show = False
                if col == 1:
                    legend_shown.add(label)

        # ── generic plotly primitives ──────────────────────────────────────
        def _add_hist_line(self, fig, row=None, col=None):
            """Dashed vertical marker at the last historical year."""
            if self._last_hist_year is None:
                return
            if row is None:
                fig.add_vline(x=self._last_hist_year, line_dash="dash", line_color="lightgray")
            else:
                fig.add_vline(x=self._last_hist_year, line_dash="dash",
                              line_color="lightgray", row=row, col=col)

        def _add_band(self, fig, col, times, y_lo, y_hi, color, fillcolor,
                      name, showlegend, dash=False):
            fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                line=dict(color=color, width=0), mode="lines", hoverinfo="skip"),
                row=1, col=col)
            fig.add_trace(go.Scatter(x=times, y=y_hi, name=name, showlegend=showlegend,
                fill="tonexty", fillcolor=fillcolor,
                line=dict(color=color, width=1.5, dash="dash" if dash else "solid"),
                mode="lines"), row=1, col=col)

        def _add_line(self, fig, col, times, y, color, name, showlegend,
                      dash=False, width=1.5):
            fig.add_trace(go.Scatter(x=times, y=y, name=name, showlegend=showlegend,
                line=dict(color=color, width=width, dash="dash" if dash else "solid"),
                mode="lines"), row=1, col=col)

        @staticmethod
        def _suffix(is_conservative: bool, fixed_supply: bool = False) -> str:
            """Label suffix. For models without ambition bands this is empty
            (except a plain '(fixed supply)' tag)."""
            if not cfg.use_ambition_bands:
                return " (fixed supply)" if fixed_supply else ""
            amb = "Conservative" if is_conservative else "Highly Ambitious"
            return f" ({amb}, fixed supply)" if fixed_supply else f" ({amb})"

        # ── the shared scenario drawer ──────────────────────────────────────
        def _draw_scenario_panel(self, fig, col, times, mat, scenario_map, *,
                                 scale, legend_shown, draw_baseline_line,
                                 skip_group=None):
            """Draw all scenario groups into one subplot column.

            ``mat`` is a (n_t, n_run) matrix. For each group:
              * solid trace  — demand-following trade; a Conservative→HA band when
                ambition bands are used, otherwise a single line.
              * dashed trace — the fix_supply trade variant, same shape.
            When ``draw_baseline_line`` and the model uses a separate baseline
            run, a grey reference line is drawn on top.
            """
            for group in cfg.group_order:
                if group == skip_group:
                    continue
                ambition_dict = scenario_map.get(group)
                if not ambition_dict:
                    continue
                color = cfg.color[group]
                display = cfg.display[group]
                show_leg = col == 1 and group not in legend_shown

                c_def = ambition_dict.get("Conservative", {}).get("default")
                ha_def = ambition_dict.get("Highly Ambitious", {}).get("default")
                c_fs = _fs_index(ambition_dict.get("Conservative", {}))
                ha_fs = _fs_index(ambition_dict.get("Highly Ambitious", {}))

                # solid (demand-following trade)
                if c_def is not None and ha_def is not None:
                    lo = np.minimum(mat[:, c_def], mat[:, ha_def]) / scale
                    hi = np.maximum(mat[:, c_def], mat[:, ha_def]) / scale
                    self._add_band(fig, col, times, lo, hi, color,
                                   cfg.fill_solid[group], display, show_leg)
                    legend_shown.add(group)
                else:
                    idx = c_def if c_def is not None else ha_def
                    if idx is not None:
                        width = 1.5 if c_def is not None else 2.5
                        self._add_line(fig, col, times, mat[:, idx] / scale, color,
                                       display + self._suffix(c_def is not None),
                                       show_leg, width=width)
                        legend_shown.add(group)

                # dashed (fix_supply trade)
                if c_fs is not None and ha_fs is not None:
                    lo = np.minimum(mat[:, c_fs], mat[:, ha_fs]) / scale
                    hi = np.maximum(mat[:, c_fs], mat[:, ha_fs]) / scale
                    self._add_band(fig, col, times, lo, hi, color,
                                   cfg.fill_dashed[group], f"{display} (fixed supply)",
                                   col == 1, dash=True)
                else:
                    idx = c_fs if c_fs is not None else ha_fs
                    if idx is not None:
                        width = 1.5 if c_fs is not None else 2.5
                        self._add_line(fig, col, times, mat[:, idx] / scale, color,
                                       display + self._suffix(c_fs is not None, fixed_supply=True),
                                       col == 1, dash=True, width=width)

            if draw_baseline_line and cfg.show_baseline_line:
                bl = _baseline_index(scenario_map, cfg)
                if bl is not None:
                    self._add_line(fig, col, times, mat[:, bl] / scale, cfg.color_baseline,
                                   "Baseline", col == 1 and "Baseline" not in legend_shown,
                                   width=2)
                    legend_shown.add("Baseline")

            self._draw_custom_lines(fig, col, times, [(1, mat)], scale, legend_shown)

        # ── raw trade overlay ───────────────────────────────────────────────
        def visualize_trade(self, mfa, region=None, linecolor_dims=None,
                            subplot_dims=None, good_filters=None, material_filters=None):
            region = cfg.region if region is None else region
            for name, trade in mfa.trade_set.markets.items():
                imports = trade.imports[{"r": region}] if region is not None else trade.imports
                exports = trade.exports[{"r": region}] if region is not None else trade.exports

                mkt_good = (good_filters or {}).get(name)
                if mkt_good is not None and "g" in imports.dims.letters:
                    imports, exports = imports[{"g": mkt_good}], exports[{"g": mkt_good}]
                mkt_mat = (material_filters or {}).get(name)
                if mkt_mat is not None and "m" in imports.dims.letters:
                    imports, exports = imports[{"m": mkt_mat}], exports[{"m": mkt_mat}]

                linecolor_dim = (linecolor_dims or {}).get(name)
                subplot_dim = (subplot_dims or {}).get(name)
                lc_letter = imports.dims[linecolor_dim].letter if linecolor_dim else None
                sp_letter = imports.dims[subplot_dim].letter if subplot_dim else None
                dimlist = ["t"] + [d for d in (lc_letter, sp_letter) if d is not None]
                imports, exports = imports.sum_to(dimlist), exports.sum_to(dimlist)

                n_colors = mfa.dims[linecolor_dim].len if linecolor_dim else 1
                base = plc.qualitative.Dark24
                # Imports are drawn first (lines 0..n_colors-1), exports second
                # (lines n_colors..2*n_colors-1, see PlotlyArrayPlotter.add_line).
                # Duplicate the per-run palette so each export reuses its import's
                # colour, distinguished only by the dashed line style.
                per_run = (base * (n_colors // len(base) + 1))[:n_colors]
                colors = per_run + per_run

                ap_imports = self.plotter_class(
                    array=imports, intra_line_dim="Time", subplot_dim=subplot_dim,
                    linecolor_dim=linecolor_dim, display_names=self.display_names.dct,
                    color_map=colors,
                )
                fig = ap_imports.plot()
                title = f"{market_title(cfg.market_display, name, mkt_good, mkt_mat)} Trade"
                ap_exports = self.plotter_class(
                    array=-exports, intra_line_dim="Time", subplot_dim=subplot_dim,
                    linecolor_dim=linecolor_dim, line_type="dash",
                    display_names=self.display_names.dct, title=title,
                    ylabel="Trade (Exports negative)", suppress_legend=True,
                    fig=fig, color_map=colors,
                )
                fig = ap_exports.plot()
                fig.update_xaxes(range=[cfg.x_start_year, cfg.x_end_year])
                self._add_hist_line(fig)
                self._draw_trade_overlays(fig, name)
                self.plot_and_save_figure(ap_exports, f"trade_{name}.png", do_plot=False)

        # ── external cs4r overlays on a trade figure ────────────────────────
        def _draw_trade_overlays(self, fig, market_name):
            """Overlay external cs4r series (e.g. traded recyclate) for the given
            market, one dotted line per scenario in the overlay spec."""
            for ov in cfg.trade_overlays:
                if ov.market != market_name:
                    continue
                base = pathlib.Path(ov.base_dir)
                for ci, (suffix, subdir) in enumerate(ov.scenarios.items()):
                    path = base / subdir / ov.filename
                    if not path.exists():
                        print(f"  overlay file missing, skipping: {path}")
                        continue
                    years, vals = load_cs4r_series(
                        path, region=ov.region, material=ov.material,
                        good=ov.good, sign=ov.sign)
                    color = _CUSTOM_COLORS[ci % len(_CUSTOM_COLORS)]
                    fig.add_trace(go.Scatter(
                        x=years, y=vals, mode="lines",
                        name=f"{ov.label} {suffix}",
                        line=dict(color=color, width=2, dash="dot"),
                    ))

        # ── individual flow overlays ────────────────────────────────────────
        def _visualize_flows(self, mfa):
            for spec in cfg.flow_plots:
                if not self._has_source(mfa, spec.source):
                    continue
                arr = self._resolve(mfa, spec.source)
                sel = self._sel(arr, {"m": spec.material, "g": spec.good})
                sel = {k: v for k, v in sel.items() if v is not None}
                self.visualize_flow(mfa, flow=arr[sel] if sel else arr, name=spec.name,
                                    region=cfg.region, linecolor_dim=RUN,
                                    subplot_dim=spec.subplot_dim)

        def visualize_flow(self, mfa, flow, name, region=None,
                          linecolor_dim=None, subplot_dim=None):
            flow = flow[{"r": region}] if region is not None else flow
            lc_letter = mfa.dims[linecolor_dim].letter if linecolor_dim else None
            sp_letter = mfa.dims[subplot_dim].letter if subplot_dim else None
            dimlist = ["t"] + [d for d in (lc_letter, sp_letter) if d is not None]
            flow = flow.sum_to(dimlist)

            fig, ap_flow = self.plot_history_and_future(
                mfa=mfa, data_to_plot=flow, subplot_dim=subplot_dim, x_array=None,
                linecolor_dim=linecolor_dim, x_label="Year", y_label=f"{name} [t]",
                title=name, line_label=name if linecolor_dim is None else None,
            )
            fig.update_xaxes(range=[cfg.x_start_year, cfg.x_end_year])
            self._add_hist_line(fig)
            self.plot_and_save_figure(ap_flow, f"{name}.png", do_plot=False)

        # ── Δ net imports vs baseline ───────────────────────────────────────
        def visualize_delta_net_imports(self, mfa, run_labels, run_letter):
            """Net imports relative to the baseline group (S0 / Baseline)."""
            scenario_map = self._scenario_map(run_labels)
            bl = _baseline_index(scenario_map, cfg)
            if bl is None:
                return
            times = list(mfa.dims["t"].items)
            markets = self._present_markets(mfa, cfg.markets)
            titles = [market_title(cfg.market_display, m.name, m.good, m.material) for m in markets]
            fig = make_subplots(rows=1, cols=len(markets), subplot_titles=titles)
            legend_shown = set()

            for col, m in enumerate(markets, start=1):
                vals = self._net_imports(mfa, m, run_letter)
                delta = (vals - vals[:, bl:bl + 1]) / 1e6   # Mt
                self._draw_scenario_panel(fig, col, times, delta, scenario_map,
                                          scale=1, legend_shown=legend_shown,
                                          draw_baseline_line=False,
                                          skip_group=cfg.baseline_group)
                fig.add_hline(y=0, line_dash="dot", line_color="gray", row=1, col=col)
                self._add_hist_line(fig, row=1, col=col)

            fig.update_xaxes(title_text="Year", range=[cfg.delta_start_year, cfg.x_end_year])
            fig.update_yaxes(title_text="Δ Net Imports [Mt]")
            fig.update_layout(
                title_text=f"Δ Net Imports vs {cfg.display[cfg.baseline_group]} — {cfg.region}",
                hovermode="x unified")
            self._show_and_save_plotly(fig, "delta_net_imports")

        # ── absolute net imports ────────────────────────────────────────────
        def visualize_net_imports(self, mfa, run_labels, run_letter):
            scenario_map = self._scenario_map(run_labels)
            times = list(mfa.dims["t"].items)
            markets = self._present_markets(mfa, cfg.markets)
            titles = [market_title(cfg.market_display, m.name, m.good, m.material) for m in markets]
            fig = make_subplots(rows=1, cols=len(markets), subplot_titles=titles)
            legend_shown = set()

            for col, m in enumerate(markets, start=1):
                vals = self._net_imports(mfa, m, run_letter)
                self._draw_scenario_panel(fig, col, times, vals, scenario_map,
                                          scale=1e6, legend_shown=legend_shown,
                                          draw_baseline_line=True)
                self._add_hist_line(fig, row=1, col=col)

            fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
            fig.update_yaxes(title_text="Net Imports [Mt]")
            fig.update_layout(title_text=f"Net Imports — {cfg.region}", hovermode="x unified")
            self._show_and_save_plotly(fig, "net_imports")

        # ── import dependency ratios ────────────────────────────────────────
        def visualize_import_dependency(self, mfa, run_labels, run_letter):
            """Net imports divided by demand, per dependency panel."""
            scenario_map = self._scenario_map(run_labels)
            times = list(mfa.dims["t"].items)
            eps = 1.0

            panels = []
            for dp in cfg.dependency_panels:
                if dp.market.name not in mfa.trade_set.markets:
                    continue
                if not self._has_source(mfa, dp.demand):
                    continue
                net = self._net_imports(mfa, dp.market, run_letter)
                demand = self._demand_matrix(mfa, dp.demand, run_letter,
                                             good=dp.market.good, material=dp.market.material)
                title = market_title(cfg.market_display, dp.market.name,
                                     dp.market.good, dp.market.material)
                panels.append((net / np.maximum(demand, eps), title))
            if not panels:
                return

            fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[1] for p in panels])
            legend_shown = set()
            for col, (dep, _) in enumerate(panels, start=1):
                self._draw_scenario_panel(fig, col, times, dep, scenario_map,
                                          scale=1, legend_shown=legend_shown,
                                          draw_baseline_line=True)
                self._add_hist_line(fig, row=1, col=col)

            fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
            fig.update_yaxes(title_text="Dependency ratio")
            fig.update_layout(
                title_text=f"Import Dependency (Net imports / Demand) — {cfg.region}",
                hovermode="x unified")
            self._show_and_save_plotly(fig, "import_dependency")

        # ── demands ──────────────────────────────────────────────────────────
        def visualize_demands(self, mfa, run_labels, run_letter):
            scenario_map = self._scenario_map(run_labels)
            times = list(mfa.dims["t"].items)

            panels = []
            for dpan in cfg.demand_panels:
                if not self._has_source(mfa, dpan.source):
                    continue
                vals = self._demand_matrix(mfa, dpan.source, run_letter,
                                           good=dpan.good, material=dpan.material)
                panels.append((vals, dpan.title))
            if not panels:
                return

            fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[1] for p in panels])
            legend_shown = set()
            for col, (vals, _) in enumerate(panels, start=1):
                self._draw_scenario_panel(fig, col, times, vals, scenario_map,
                                          scale=1e6, legend_shown=legend_shown,
                                          draw_baseline_line=True)
                self._add_hist_line(fig, row=1, col=col)

            fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
            fig.update_yaxes(title_text="[Mt]")
            fig.update_layout(title_text=f"{cfg.demand_title} — {cfg.region}", hovermode="x unified")
            self._show_and_save_plotly(fig, "demands")

        # ── gross trade ──────────────────────────────────────────────────────
        def _gross_matrices(self, mfa, spec: MarketSpec, run_letter):
            trade = mfa.trade_set.markets[spec.name]
            sel = self._sel(trade.imports, {"r": cfg.region, "g": spec.good, "m": spec.material})
            sel = {k: v for k, v in sel.items() if v is not None}
            return (trade.imports[sel].sum_to(["t", run_letter]).values,
                    trade.exports[sel].sum_to(["t", run_letter]).values)

        def _draw_gross_groups(self, fig, col, times, signed_vals, scenario_map, legend_shown):
            """Draw scenario groups for a gross-trade subplot.

            ``signed_vals`` is a list of ``(sign, matrix)``; imports use sign +1
            and exports −1 in the combined figure (single (+1, matrix) otherwise).
            The fix_supply variant is drawn as a band spanning the α∈{0,1} runs.
            """
            for group in cfg.group_order:
                ambition_dict = scenario_map.get(group)
                if not ambition_dict:
                    continue
                color = cfg.color[group]
                display = cfg.display[group]
                show_leg = col == 1 and group not in legend_shown

                c_def = ambition_dict.get("Conservative", {}).get("default")
                ha_def = ambition_dict.get("Highly Ambitious", {}).get("default")
                fs_indices = [ambition_dict.get(amb, {}).get(k)
                              for amb in _AMBITIONS
                              for k in ("fix_supply_alpha0", "fix_supply_alpha1")]
                fs_indices = [i for i in fs_indices if i is not None]

                for sign, vals in signed_vals:
                    leg = show_leg and sign == 1
                    # solid (demand-following)
                    if c_def is not None and ha_def is not None:
                        lo = np.minimum(sign * vals[:, c_def], sign * vals[:, ha_def]) / 1e6
                        hi = np.maximum(sign * vals[:, c_def], sign * vals[:, ha_def]) / 1e6
                        self._add_band(fig, col, times, lo, hi, color,
                                       cfg.fill_solid[group], display, leg)
                        if sign == 1 and col == 1:
                            legend_shown.add(group)
                    else:
                        idx = c_def if c_def is not None else ha_def
                        if idx is not None:
                            width = 1.5 if c_def is not None else 2.5
                            self._add_line(fig, col, times, sign * vals[:, idx] / 1e6, color,
                                           display + self._suffix(c_def is not None), leg, width=width)
                            if sign == 1 and col == 1:
                                legend_shown.add(group)
                    # dashed (fix_supply, α range)
                    if len(fs_indices) >= 2:
                        lo = np.min([sign * vals[:, i] for i in fs_indices], axis=0) / 1e6
                        hi = np.max([sign * vals[:, i] for i in fs_indices], axis=0) / 1e6
                        self._add_band(fig, col, times, lo, hi, color, cfg.fill_dashed[group],
                                       f"{display} (fixed supply, α∈[0,1])",
                                       col == 1 and sign == 1, dash=True)
                    elif len(fs_indices) == 1:
                        self._add_line(fig, col, times, sign * vals[:, fs_indices[0]] / 1e6, color,
                                       f"{display} (fixed supply)", col == 1 and sign == 1, dash=True)

        def _draw_gross_baseline(self, fig, col, times, signed_vals, scenario_map, legend_shown):
            if not cfg.show_baseline_line:
                return
            bl = _baseline_index(scenario_map, cfg)
            if bl is None:
                return
            show_bl = col == 1 and "Baseline" not in legend_shown
            for sign, vals in signed_vals:
                self._add_line(fig, col, times, sign * vals[:, bl] / 1e6,
                               cfg.color_baseline, "Baseline", show_bl, width=2)
                show_bl = False
            if col == 1:
                legend_shown.add("Baseline")

        def visualize_gross_trade(self, mfa, run_labels, run_letter):
            """Gross imports (+) and exports (−) for the EU region.
            """
            scenario_map = self._scenario_map(run_labels)
            times = list(mfa.dims["t"].items)

            combined = []
            for spec in self._present_markets(mfa, cfg.markets):
                imp, exp = self._gross_matrices(mfa, spec, run_letter)
                combined.append((market_title(cfg.market_display, spec.name, spec.good, spec.material), imp, exp))
            if not combined:
                return

            fig = make_subplots(rows=1, cols=len(combined), subplot_titles=[c[0] for c in combined])
            legend_shown = set()
            for col, (_, imp, exp) in enumerate(combined, start=1):
                fig.add_hline(y=0, line_dash="dot", line_color="lightgray", row=1, col=col)
                self._draw_gross_groups(fig, col, times, [(1, imp), (-1, exp)], scenario_map, legend_shown)
                self._draw_gross_baseline(fig, col, times, [(1, imp), (-1, exp)], scenario_map, legend_shown)
                self._draw_custom_lines(fig, col, times, [(1, imp), (-1, exp)], 1e6, legend_shown)
                self._add_hist_line(fig, row=1, col=col)
            fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
            fig.update_yaxes(title_text="Imports [+] / Exports [−] [Mt]")
            fig.update_layout(title_text=f"Gross trade — {cfg.region}", hovermode="x unified")
            self._show_and_save_plotly(fig, "gross_trade_eu")

        # ── stacked gross trade by region (baseline only) ───────────────────
        def visualize_global_trade_stacked(self, mfa, run_labels, run_letter):
            """Gross imports/exports stacked by region, for the baseline run only.

            EU region highlighted in red and placed on top of the stack.
            """
            scenario_map = self._scenario_map(run_labels)
            bl = _baseline_index(scenario_map, cfg)
            if bl is None:
                return
            baseline_label = run_labels[bl]
            times = list(mfa.dims["t"].items)
            regions = list(mfa.dims["r"].items)

            other_colors = plc.qualitative.D3 + plc.qualitative.Plotly
            palette_idx = 0
            region_colors = {}
            for r in regions:
                if r == cfg.region:
                    region_colors[r] = "#d62728"
                else:
                    region_colors[r] = other_colors[palette_idx % len(other_colors)]
                    palette_idx += 1

            for dp in self._region_market_specs(mfa):
                spec = dp.market
                trade = mfa.trade_set.markets[spec.name]
                sel = self._sel(trade.imports, {run_letter: baseline_label, "g": spec.good, "m": spec.material})
                sel = {k: v for k, v in sel.items() if v is not None}
                imp = trade.imports[sel].sum_to(["t", "r"]).values / 1e6
                exp = trade.exports[sel].sum_to(["t", "r"]).values / 1e6

                # EU largest → place on top by sorting others by mean imports
                avg_imp = imp.mean(axis=0)
                ordered = sorted([r for r in regions if r != cfg.region],
                                 key=lambda r: avg_imp[regions.index(r)]) + [cfg.region]

                title = market_title(cfg.market_display, spec.name, spec.good, spec.material)
                fig = make_subplots(rows=1, cols=2,
                                    subplot_titles=[f"{title} imports", f"{title} exports"])
                legend_shown = set()
                for col, vals in enumerate([imp, exp], start=1):
                    for r in ordered:
                        r_idx = regions.index(r)
                        fig.add_trace(go.Scatter(
                            x=times, y=vals[:, r_idx], name=r, stackgroup="one", mode="lines",
                            line=dict(color=region_colors[r], width=0.5),
                            fillcolor=region_colors[r],
                            showlegend=(col == 1 and r not in legend_shown),
                        ), row=1, col=col)
                        legend_shown.add(r)
                self._add_hist_line(fig)
                fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
                fig.update_yaxes(title_text="[Mt]")
                fig.update_layout(
                    title_text=f"Global {title} trade by region — {cfg.display[cfg.baseline_group]}",
                    hovermode="x unified")
                self._show_and_save_plotly(fig, f"global_trade_stacked_{spec.name}{self._suffix_fname(spec)}")

        # ── trade mechanism by region (baseline only) ───────────────────────
        def visualize_trade_mechanism(self, mfa, run_labels, run_letter):
            """Imports/Demand and Exports/Supply ratios per region (baseline run)."""
            scenario_map = self._scenario_map(run_labels)
            bl = _baseline_index(scenario_map, cfg)
            if bl is None:
                return
            baseline_label = run_labels[bl]
            times = list(mfa.dims["t"].items)
            all_regions = list(mfa.dims["r"].items)
            n_regions = len(all_regions)
            ratio_colors = {"Imports / Demand": "#2ca02c", "Exports / Supply": "#d62728"}
            ncols = 3
            nrows = (n_regions + ncols - 1) // ncols

            for dp in self._region_market_specs(mfa):
                if not self._has_source(mfa, dp.demand):
                    continue
                spec = dp.market
                base_sel = {run_letter: baseline_label, "g": spec.good, "m": spec.material}

                demand_arr = self._resolve(mfa, dp.demand)
                demand = demand_arr[self._clean(self._sel(demand_arr, base_sel))].sum_to(["t", "r"]).values

                trade = mfa.trade_set.markets[spec.name]
                t_sel = self._clean(self._sel(trade.imports, base_sel))
                imp = trade.imports[t_sel].sum_to(["t", "r"]).values
                exp = trade.exports[t_sel].sum_to(["t", "r"]).values
                sup = demand + exp - imp

                eps = 1.0
                ratio_id = imp / np.maximum(np.abs(demand), eps)
                ratio_es = exp / np.maximum(np.abs(sup), eps)

                fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=all_regions)
                for r_i in range(n_regions):
                    row, col = r_i // ncols + 1, r_i % ncols + 1
                    for label, ratios in [("Imports / Demand", ratio_id[:, r_i]),
                                          ("Exports / Supply", ratio_es[:, r_i])]:
                        fig.add_trace(go.Scatter(
                            x=times, y=ratios, name=label, showlegend=(r_i == 0),
                            line=dict(color=ratio_colors[label], width=2), mode="lines",
                        ), row=row, col=col)
                self._add_hist_line(fig)
                fig.update_xaxes(title_text="Year", range=[cfg.x_start_year, cfg.x_end_year])
                fig.update_yaxes(title_text="Ratio")
                title = market_title(cfg.market_display, spec.name, spec.good, spec.material)
                fig.update_layout(
                    title_text=f"{title} trade ratios by region — {cfg.display[cfg.baseline_group]}",
                    hovermode="x unified", height=300 * nrows)
                self._show_and_save_plotly(fig, f"trade_ratios_{spec.name}_by_region{self._suffix_fname(spec)}")

        # ── helpers for the region-level (baseline-only) figures ─────────────
        def _region_market_specs(self, mfa) -> list[DependencyPanel]:
            return [dp for dp in cfg.region_panels if dp.market.name in mfa.trade_set.markets]

        @staticmethod
        def _clean(sel: dict) -> dict:
            return {k: v for k, v in sel.items() if v is not None}

        @staticmethod
        def _suffix_fname(spec: MarketSpec) -> str:
            tag = spec.good or spec.material
            return f"_{tag.lower()}" if tag else ""

    return ComparisonVisualizer


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ CSV export                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def export_trade_csv(models, labels, directory: pathlib.Path, output_dir=None):
    """One CSV per (run, market): [dims…, imports_t, exports_t, net_imports_t]."""
    if output_dir is None:
        output_dir = directory.parent / "trade_csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    for model, label in zip(models, labels):
        mfa = model.future_mfa
        if mfa.trade_set is None:
            continue
        safe_label = label.replace(" ", "_").replace("/", "_").replace("α", "alpha")
        for market_name, trade in mfa.trade_set.markets.items():
            imp_df = trade.imports.to_df().reset_index().rename(columns={"value": "imports_t"})
            exp_df = trade.exports.to_df().reset_index().rename(columns={"value": "exports_t"})
            dim_cols = [c for c in imp_df.columns if c != "imports_t"]
            merged = imp_df.merge(exp_df, on=dim_cols)
            merged["net_imports_t"] = merged["imports_t"] - merged["exports_t"]
            out_path = output_dir / f"{safe_label}_{market_name}.csv"
            merged.to_csv(out_path, index=False)
            print(f"  {out_path.name}")
    print(f"Trade CSVs written to {output_dir}")


def export_flows_csv(models, labels, cfg: ModelConfig, directory: pathlib.Path, output_dir=None):
    """One CSV per (run, flow) for the model's configured demand/supply flows."""
    if output_dir is None:
        output_dir = directory.parent / "flows_csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    def resolve(mfa, source):
        if source == "stock_inflow":
            return mfa.stocks["in_use"].inflow
        return mfa.flows[source[len("flow:"):]]

    for model, label in zip(models, labels):
        mfa = model.future_mfa
        safe_label = label.replace(" ", "_").replace("/", "_").replace("α", "alpha")
        for name, source in cfg.csv_flows:
            try:
                arr = resolve(mfa, source)
            except KeyError:
                continue
            df = arr.to_df().reset_index().rename(columns={"value": "value_t"})
            out_path = output_dir / f"{safe_label}_{name}.csv"
            df.to_csv(out_path, index=False)
            print(f"  {out_path.name}")
    print(f"Flow CSVs written to {output_dir}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Main                                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def main():
    args = _parse_args()
    cfg = MODEL_CONFIGS[args.model]
    directory = pathlib.Path(DIRECTORIES[args.model])

    scenario_paths = pick_files(directory, args.runs or None)
    scenario_labels = [make_short_label(p.stem, args.model) for p in scenario_paths]

    custom_paths = pick_custom_files(directory, args.custom, exclude=scenario_paths)
    custom_labels = [custom_label(p.stem, args.model) for p in custom_paths]

    # Scenario runs first, then custom runs; custom indices are the trailing ones.
    paths = scenario_paths + custom_paths
    labels = scenario_labels + custom_labels
    n_scenario = len(scenario_paths)
    custom_runs = [(n_scenario + i, lab) for i, lab in enumerate(custom_labels)]

    print(f"Loading {len(paths)} runs ({n_scenario} scenario, {len(custom_paths)} custom):")
    for i, (label, path) in enumerate(zip(labels, paths)):
        tag = "custom" if i >= n_scenario else "scenario"
        print(f"  [{tag}] {label}: {path}")
    models = load_models(paths)

    print("Exporting trade CSVs…")
    export_trade_csv(models, labels, directory)
    print("Exporting flow CSVs…")
    export_flows_csv(models, labels, cfg, directory)

    run_dim = fd.Dimension(letter=RUN_DIM_LETTER, name=RUN_DIM_NAME, items=labels)
    combined_mfa = build_combined_mfa(models, run_dim)

    VisualizerCls = make_comparison_visualizer(cfg, RUN_DIM_NAME)

    base_model = models[0]
    fake_model = copy.copy(base_model)
    fake_model.future_mfa = combined_mfa

    base_vis = base_model.visualizer
    vis = VisualizerCls(cfg=base_vis.cfg, display_names=base_vis.display_names)
    vis.cfg = vis.cfg.model_copy(update={"do_show_figs": True, "do_save_figs": True})
    vis._custom_runs = custom_runs
    vis._custom_indices = {idx for idx, _ in custom_runs}

    print("Plotting comparison figures…")
    vis.visualize(model=fake_model)
    vis.stop_and_show()
    print("Done.")


if __name__ == "__main__":
    main()
