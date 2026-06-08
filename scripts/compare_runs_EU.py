"""
compare_runs_EU.py
--------------------
How it works:
- Load N model pickles and stack every flow/stock/parameter array along a new "Run" dimension.
- Build a fake MFA system whose arrays have the extra "Run" dimension.
- Run a custom Visualizer that overrides the key helper methods to use "Run" as linecolor_dim or subplot_dim, so that all runs are overlaid in the same figures.

"""

import pickle
import pathlib
import sys
import copy
import argparse
import numpy as np
import flodym as fd
import questionary
import plotly.colors as plc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional

# ── configuration ──────────────────────────────────────────────────────────────

DIRECTORIES = {
    "plastics": "data/plastics/output/transience/pickle",
    "steel":    "data/steel/output/transience/pickle",
}

_parser = argparse.ArgumentParser(description="Compare multiple model runs visually.")
_parser.add_argument("runs", nargs="*", help="Run stems (no .pickle extension)")
_parser.add_argument("--model", default="steel", choices=list(DIRECTORIES),
                     help="Which model type to compare (default: steel)")
_args = _parser.parse_args()

MODEL     = _args.model
DIRECTORY = pathlib.Path(DIRECTORIES[MODEL])
RUNS      = _args.runs or None   # e.g. ["model_plastics_SSP2_...", "model_plastics_SSP2_..."]
LABELS    = None                 # if None, derived from file stems
RUN_DIM_LETTER = "X"
RUN_DIM_NAME   = "Run"
# ──────────────────────────────────────────────────────────────────────────────


def pick_files() -> list[pathlib.Path]:
    available = sorted(DIRECTORY.glob("model_*.pickle"))
    if not available:
        raise FileNotFoundError(f"No model_*.pickle files found in {DIRECTORY}")
    if RUNS:
        return [DIRECTORY / f"{r}.pickle" for r in RUNS]
    chosen = questionary.checkbox(
        "Select runs to compare:",
        choices=[f.name for f in available],
        validate=lambda s: True if s else "Select at least one file.",
    ).ask()
    if not chosen:
        raise ValueError("No files selected.")
    return [DIRECTORY / name for name in chosen]


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
    """
    Return a copy of the base MFA where every flow/stock/parameter array has been
    stacked along `run_dim` (appended as the last dimension).
    """
    mfas = [m.future_mfa for m in models]
    base = mfas[0]

    # Extended dimension set: append the Run dimension at the end
    new_dims = fd.DimensionSet(dim_list=list(base.dims.dim_list) + [run_dim])

    # -- flows --
    new_flows = {}
    for name in base.flows:
        stacked = _stack([mfa.flows[name] for mfa in mfas], run_dim)
        new_flows[name] = base.flows[name].model_copy(
            update={"values": stacked.values, "dims": stacked.dims}
        )

    # -- stocks --
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

    # -- parameters --
    new_params = {}
    for name in base.parameters:
        try:
            new_params[name] = _stack([mfa.parameters[name] for mfa in mfas], run_dim)
        except Exception:
            new_params[name] = base.parameters[name]

    # -- trade_set --
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

_STRATEGY_TOKENS = ["Downsizing", "Redesign", "Remanufacturing", "Combined", "Baseline"]
_STRATEGY_ORDER  = ["Downsizing", "Redesign", "Remanufacturing", "Combined"]
_AMBITIONS       = ["Conservative", "Highly Ambitious"]

_STRATEGY_DISPLAY = {
    "Baseline":        "Baseline",
    "Downsizing":      "Downsizing",
    "Redesign":        "Redesign",
    "Remanufacturing": "Remanufacturing",
    "Combined":        "Combined",
}
_STRATEGY_COLORS = {
    "Baseline":        "#7f7f7f",
    "Downsizing":      "#1f77b4",
    "Redesign":        "#ff7f0e",
    "Remanufacturing": "#2ca02c",
    "Combined":        "#d62728",
}
_STRATEGY_FILL_SOLID = {
    "Baseline":        "rgba(127,127,127,0.20)",
    "Downsizing":      "rgba(31,119,180,0.20)",
    "Redesign":        "rgba(255,127,14,0.20)",
    "Remanufacturing": "rgba(44,160,44,0.20)",
    "Combined":        "rgba(214,39,40,0.20)",
}
_STRATEGY_FILL_DASHED = {
    "Baseline":        "rgba(127,127,127,0.08)",
    "Downsizing":      "rgba(31,119,180,0.08)",
    "Redesign":        "rgba(255,127,14,0.08)",
    "Remanufacturing": "rgba(44,160,44,0.08)",
    "Combined":        "rgba(214,39,40,0.08)",
}

_EU_REGION = {"steel": "EUR", "plastics": "EU27+3"}


def _make_short_label(stem: str) -> str:
    """Convert a pickle file stem to a short human-readable run label."""
    strategy = next((s for s in _STRATEGY_TOKENS if s in stem), "Unknown")
    if "fix_supply_alpha0" in stem:
        trade = "fix_supply_α0"
    elif "fix_supply_alpha1" in stem:
        trade = "fix_supply_α1"
    else:
        trade = "default"
    if strategy == "Baseline":
        return f"Baseline {trade}"
    ambition = "HA" if ("Highly_Ambitious" in stem or "Highly_mbitious" in stem) else "Cons"
    return f"{strategy} {ambition} {trade}"


def _parse_run_labels(labels: list[str]) -> dict:
    """Return {strategy: {ambition: {trade: run_index}}} from short or full-stem labels."""
    result = {}
    for i, label in enumerate(labels):
        if "fix_supply_alpha0" in label or "fix_supply_α0" in label:
            trade = "fix_supply_alpha0"
        elif "fix_supply_alpha1" in label or "fix_supply_α1" in label:
            trade = "fix_supply_alpha1"
        else:
            trade = "default"

        strategy = next((s for s in _STRATEGY_TOKENS if s in label), "Unknown")

        if strategy == "Baseline":
            ambition = "Baseline"
        elif "Highly Ambitious" in label or "Highly_Ambitious" in label or "Highly_mbitious" in label or " HA " in label or label.endswith(" HA"):
            ambition = "Highly Ambitious"
        else:
            ambition = "Conservative"

        result.setdefault(strategy, {}).setdefault(ambition, {})[trade] = i
    return result


def _fs_index(trade_dict: dict) -> Optional[int]:
    """Return the fix_supply index from a trade dict, preferring alpha1."""
    for k in ("fix_supply_alpha1", "fix_supply_alpha0"):
        if k in trade_dict:
            return trade_dict[k]
    return None


def make_comparison_visualizer(model_name: str, run_dim_name: str):
    
    from remind_mfa.common.common_visualization import CommonVisualizer as BaseVis

    RUN = run_dim_name

    class ComparisonVisualizer(BaseVis):
        """Visualizer that overlays multiple runs by injecting a Run dimension."""

        def visualize(self, model):
            mfa = model.future_mfa
            run_letter = mfa.dims[RUN].letter
            eu_region = _EU_REGION.get(model_name, "EUR")
            linecolor_dims = {name: RUN for name in model.future_mfa.trade_set.markets}
            subplot_dims = {name: None for name in model.future_mfa.trade_set.markets}
            if model_name == "steel":
                subplot_dims["indirect"] = "Good"
            self.visualize_trade(mfa, linecolor_dims=linecolor_dims, region=eu_region, subplot_dims=subplot_dims)
            self.visualize_flow(mfa, flow=mfa.stocks["in_use"].inflow, name="Stock inflow", region=eu_region, linecolor_dim=RUN, subplot_dim="Good")
            self.visualize_flow(mfa, flow=mfa.flows["fabrication => good_market"], name="Good supply", region=eu_region, linecolor_dim=RUN, subplot_dim="Good")
            self.visualize_flow(mfa, flow=mfa.flows["ip_market => fabrication"], name="Steel demand", region=eu_region, linecolor_dim=RUN, subplot_dim=None)
            run_labels = list(mfa.dims[RUN].items)
            self.visualize_delta_net_imports(mfa, run_labels, run_letter, region=eu_region)
            self.visualize_import_dependency(mfa, run_labels, run_letter, region=eu_region)
            self.visualize_gross_trade_eu(mfa, run_labels, run_letter, region=eu_region)
            self.visualize_bracketing(mfa, run_labels, run_letter, region=eu_region)
            self.visualize_global_net_imports(mfa, run_labels, run_letter, region=eu_region)
            first_future_year = max(model.historic_mfa.dims["h"].items) + 1
            self.visualize_trade_mechanism(mfa, run_labels, run_letter, first_future_year=first_future_year)
            # ── transport-only repeats ──────────────────────────────────────
            self.visualize_delta_net_imports(mfa, run_labels, run_letter, region=eu_region, good="Transport")
            self.visualize_import_dependency(mfa, run_labels, run_letter, region=eu_region, good="Transport")
            self.visualize_gross_trade_eu(mfa, run_labels, run_letter, region=eu_region, good="Transport")
            self.visualize_bracketing(mfa, run_labels, run_letter, region=eu_region, good="Transport")
            self.visualize_global_net_imports(mfa, run_labels, run_letter, region=eu_region, good="Transport")
            self.visualize_trade_mechanism(mfa, run_labels, run_letter, first_future_year=first_future_year, good="Transport")
        
        def visualize_trade(
            self, mfa: fd.MFASystem, region: Optional[str] = None, linecolor_dims: Optional[dict[str, Optional[str]]] = None, subplot_dims: Optional[dict[str, Optional[str]]] = None
        ):

            for name, trade in mfa.trade_set.markets.items():
                imports = trade.imports[{"r": region}] if region is not None else trade.imports
                exports = trade.exports[{"r": region}] if region is not None else trade.exports

                if region is None:
                    subplot_dim = "Region"

                linecolor_dim = linecolor_dims[name] if linecolor_dims is not None else None
                linecolor_dim_letter = (
                    imports.dims[linecolor_dim].letter if linecolor_dim is not None else None
                )
                subplot_dim = subplot_dims[name] if subplot_dims is not None else None
                subplot_dim_letter = (
                    imports.dims[subplot_dim].letter if subplot_dim is not None else None
                )
                dimlist = [
                    "t",
                ] + ([linecolor_dim_letter] if linecolor_dim_letter is not None else []) + ([subplot_dim_letter] if subplot_dim_letter is not None else [])
                imports = imports.sum_to(dimlist)
                exports = exports.sum_to(dimlist)

                if linecolor_dim is not None:
                    n_colors = mfa.dims[linecolor_dim].len
                else:
                    n_colors = 1
                _base = plc.qualitative.Dark24
                colors = (_base * (2 * n_colors // len(_base) + 2))[:2 * n_colors]
                ap_imports = self.plotter_class(
                    array=imports,
                    intra_line_dim="Time",
                    subplot_dim=subplot_dim,
                    linecolor_dim=linecolor_dim,
                    display_names=self.display_names.dct,
                    color_map=colors,
                )
                fig = ap_imports.plot()
                ap_exports = self.plotter_class(
                    array=-exports,
                    intra_line_dim="Time",
                    subplot_dim=subplot_dim,
                    linecolor_dim=linecolor_dim,
                    line_type="dash",
                    display_names=self.display_names.dct,
                    title=f"{name} Trade",
                    ylabel="Trade (Exports negative)",
                    suppress_legend=True,
                    fig=fig,
                    color_map=colors,
                )
                fig = ap_exports.plot()
                fig.update_xaxes(range=[1950, max(mfa.dims["t"].items)])
                self.plot_and_save_figure(ap_exports, f"trade_{name}.png", do_plot=False)

        def visualize_flow(
            self,
            mfa: fd.MFASystem,
            flow: fd.Flow,
            name: str,
            region: Optional[str] = None,
            linecolor_dim: Optional[str] = None,
            subplot_dim: Optional[str] = None,
        ):
            flow = flow[{"r": region}] if region is not None else flow

            linecolor_dim_letter = mfa.dims[linecolor_dim].letter if linecolor_dim is not None else None
            subplot_dim_letter = mfa.dims[subplot_dim].letter if subplot_dim is not None else None
            dimlist = [
                "t",
            ] + ([linecolor_dim_letter] if linecolor_dim_letter is not None else []) + ([subplot_dim_letter] if subplot_dim_letter is not None else [])
            flow = flow.sum_to(dimlist)

            fig, ap_flow = self.plot_history_and_future(
                mfa=mfa,
                data_to_plot=flow,
                subplot_dim=subplot_dim,
                x_array=None,
                linecolor_dim=linecolor_dim,
                x_label="Year",
                y_label=f"{name} [t]",
                title=f"{name}",
                line_label=name if linecolor_dim is None else None,
            )

            fig.update_xaxes(range=[1950, max(mfa.dims["t"].items)])
            self.plot_and_save_figure(ap_flow, f"{name}.png", do_plot=False)

        # ── scenario-comparison helpers ───────────────────────────────────────

        def _net_imports_eur(self, mfa, market_name, region, run_letter, good=None):
            """Net imports for one market and region, shape (n_time, n_runs)."""
            trade = mfa.trade_set.markets[market_name]
            sel = {"r": region}
            if good is not None and "g" in trade.imports.dims.letters:
                sel["g"] = good
            arr = (trade.imports - trade.exports)[sel].sum_to(["t", run_letter])
            return arr.values

        def _market_has_good_dim(self, mfa, market_name):
            return "g" in mfa.trade_set.markets[market_name].imports.dims.letters

        def visualize_delta_net_imports(self, mfa, run_labels, run_letter, region="EUR", good=None):
            """Δ net imports vs Baseline.

            Strategy = color. Ambition = filled band (Conservative → Highly Ambitious).
            Trade = line style: solid band = demand-following, dashed band = fix_supply.
            Net imports are alpha-invariant under fix_supply; alpha1 is used as representative.
            """
            scenario_map = _parse_run_labels(run_labels)
            baseline_idx = scenario_map.get("Baseline", {}).get("Baseline", {}).get("default")
            if baseline_idx is None:
                return

            good_suffix = f"_{good.lower()}" if good is not None else ""
            times = list(mfa.dims["t"].items)
            all_markets = [m for m in ["steel", "indirect", "primary", "final"] if m in mfa.trade_set.markets]
            markets = [m for m in all_markets if good is None or self._market_has_good_dim(mfa, m)]
            fig = make_subplots(rows=1, cols=len(markets), subplot_titles=markets)
            legend_shown = set()

            for col, market_name in enumerate(markets, start=1):
                vals  = self._net_imports_eur(mfa, market_name, region, run_letter, good=good)
                delta = (vals - vals[:, baseline_idx : baseline_idx + 1]) / 1e6  # Mt

                for strategy in _STRATEGY_ORDER:
                    ambition_dict = scenario_map.get(strategy, {})
                    if not ambition_dict:
                        continue

                    color        = _STRATEGY_COLORS[strategy]
                    fill_solid   = _STRATEGY_FILL_SOLID[strategy]
                    fill_dashed  = _STRATEGY_FILL_DASHED[strategy]
                    display      = _STRATEGY_DISPLAY[strategy]
                    show_leg     = col == 1 and strategy not in legend_shown

                    c_def  = ambition_dict.get("Conservative", {}).get("default")
                    ha_def = ambition_dict.get("Highly Ambitious", {}).get("default")
                    c_fs   = _fs_index(ambition_dict.get("Conservative", {}))
                    ha_fs  = _fs_index(ambition_dict.get("Highly Ambitious", {}))

                    # solid band: Conservative → Highly Ambitious, demand-following trade
                    if c_def is not None and ha_def is not None:
                        y_lo = np.minimum(delta[:, c_def], delta[:, ha_def])
                        y_hi = np.maximum(delta[:, c_def], delta[:, ha_def])
                        fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                            line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                        ), row=1, col=col)
                        fig.add_trace(go.Scatter(x=times, y=y_hi,
                            name=display, showlegend=show_leg,
                            fill="tonexty", fillcolor=fill_solid,
                            line=dict(color=color, width=1.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)
                    elif c_def is not None:
                        fig.add_trace(go.Scatter(x=times, y=delta[:, c_def],
                            name=f"{display} (Conservative)", showlegend=show_leg,
                            line=dict(color=color, width=1.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)
                    elif ha_def is not None:
                        fig.add_trace(go.Scatter(x=times, y=delta[:, ha_def],
                            name=f"{display} (Highly Ambitious)", showlegend=show_leg,
                            line=dict(color=color, width=2.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)

                    # dashed band: Conservative → Highly Ambitious, fix_supply trade
                    if c_fs is not None and ha_fs is not None:
                        y_lo = np.minimum(delta[:, c_fs], delta[:, ha_fs])
                        y_hi = np.maximum(delta[:, c_fs], delta[:, ha_fs])
                        fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                            line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                        ), row=1, col=col)
                        fig.add_trace(go.Scatter(x=times, y=y_hi,
                            name=f"{display} (fixed supply)", showlegend=(col == 1),
                            fill="tonexty", fillcolor=fill_dashed,
                            line=dict(color=color, width=1.5, dash="dash"), mode="lines",
                        ), row=1, col=col)
                    elif c_fs is not None:
                        fig.add_trace(go.Scatter(x=times, y=delta[:, c_fs],
                            name=f"{display} (Conservative, fixed supply)", showlegend=False,
                            line=dict(color=color, width=1.5, dash="dash"), mode="lines",
                        ), row=1, col=col)
                    elif ha_fs is not None:
                        fig.add_trace(go.Scatter(x=times, y=delta[:, ha_fs],
                            name=f"{display} (Highly Ambitious, fixed supply)", showlegend=False,
                            line=dict(color=color, width=2.5, dash="dash"), mode="lines",
                        ), row=1, col=col)

                fig.add_hline(y=0, line_dash="dot", line_color="gray", row=1, col=col)

            good_label = f" — {good}" if good is not None else ""
            fig.update_xaxes(title_text="Year", range=[2026, max(times)])
            fig.update_yaxes(title_text="Δ Net Imports [Mt]")
            fig.update_layout(title_text=f"Δ Net Imports vs Baseline — {region}{good_label}", hovermode="x unified")
            self._show_and_save_plotly(fig, f"delta_net_imports{good_suffix}")

        def visualize_import_dependency(self, mfa, run_labels, run_letter, region="EUR", good=None):
            """Import dependency ratios: goods-based and material-based.

            Strategy = color. Ambition = filled band (Conservative → Highly Ambitious).
            Trade = line style: solid band = demand-following, dashed band = fix_supply.
            Ratios are net-import-based and therefore alpha-invariant under fix_supply.
            """
            scenario_map = _parse_run_labels(run_labels)
            times = list(mfa.dims["t"].items)
            eps   = 1.0
            good_suffix = f"_{good.lower()}" if good is not None else ""
            good_label  = f" — {good}" if good is not None else ""

            panels = []
            if "indirect" in mfa.trade_set.markets and (good is None or self._market_has_good_dim(mfa, "indirect")):
                inflow_sel = {"r": region}
                if good is not None:
                    inflow_sel["g"] = good
                indirect_net = self._net_imports_eur(mfa, "indirect", region, run_letter, good=good)
                inflow = mfa.stocks["in_use"].inflow[inflow_sel].sum_to(["t", run_letter]).values
                panels.append((
                    indirect_net / np.maximum(inflow, eps),
                    "Goods trade dependency<br>(net indirect imports / stock inflow)",
                ))
            if good is None and "steel" in mfa.trade_set.markets and "ip_market => fabrication" in mfa.flows:
                steel_net = self._net_imports_eur(mfa, "steel", region, run_letter)
                demand = mfa.flows["ip_market => fabrication"][{"r": region}].sum_to(["t", run_letter]).values
                panels.append((
                    steel_net / np.maximum(demand, eps),
                    "Steel trade dependency<br>(net steel imports / total steel demand)",
                ))
            if good is None and "primary" in mfa.trade_set.markets and "primary_market => fabrication" in mfa.flows:
                primary_net = self._net_imports_eur(mfa, "primary", region, run_letter)
                demand = mfa.flows["primary_market => fabrication"][{"r": region}].sum_to(["t", run_letter]).values
                panels.append((
                    primary_net / np.maximum(demand, eps),
                    "Primary plastics trade dependency<br>(net primary imports / primary demand)",
                ))
            if not panels:
                return

            fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[1] for p in panels])
            legend_shown = set()

            for col, (dep, _) in enumerate(panels, start=1):
                # Baseline
                bl = scenario_map.get("Baseline", {}).get("Baseline", {})
                bl_def = bl.get("default")
                if bl_def is not None:
                    fig.add_trace(go.Scatter(x=times, y=dep[:, bl_def],
                        name="Baseline", showlegend=(col == 1 and "Baseline" not in legend_shown),
                        line=dict(color=_STRATEGY_COLORS["Baseline"], width=2), mode="lines",
                    ), row=1, col=col)
                    legend_shown.add("Baseline")

                for strategy in _STRATEGY_ORDER:
                    ambition_dict = scenario_map.get(strategy, {})
                    if not ambition_dict:
                        continue

                    color       = _STRATEGY_COLORS[strategy]
                    fill_solid  = _STRATEGY_FILL_SOLID[strategy]
                    fill_dashed = _STRATEGY_FILL_DASHED[strategy]
                    display     = _STRATEGY_DISPLAY[strategy]
                    show_leg    = col == 1 and strategy not in legend_shown

                    c_def  = ambition_dict.get("Conservative", {}).get("default")
                    ha_def = ambition_dict.get("Highly Ambitious", {}).get("default")
                    c_fs   = _fs_index(ambition_dict.get("Conservative", {}))
                    ha_fs  = _fs_index(ambition_dict.get("Highly Ambitious", {}))

                    # solid band: ambition range, demand-following trade
                    if c_def is not None and ha_def is not None:
                        y_lo = np.minimum(dep[:, c_def], dep[:, ha_def])
                        y_hi = np.maximum(dep[:, c_def], dep[:, ha_def])
                        fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                            line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                        ), row=1, col=col)
                        fig.add_trace(go.Scatter(x=times, y=y_hi,
                            name=display, showlegend=show_leg,
                            fill="tonexty", fillcolor=fill_solid,
                            line=dict(color=color, width=1.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)
                    elif c_def is not None:
                        fig.add_trace(go.Scatter(x=times, y=dep[:, c_def],
                            name=f"{display} (Conservative)", showlegend=show_leg,
                            line=dict(color=color, width=1.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)
                    elif ha_def is not None:
                        fig.add_trace(go.Scatter(x=times, y=dep[:, ha_def],
                            name=f"{display} (Highly Ambitious)", showlegend=show_leg,
                            line=dict(color=color, width=2.5), mode="lines",
                        ), row=1, col=col)
                        legend_shown.add(strategy)

                    # dashed band: ambition range, fix_supply trade
                    if c_fs is not None and ha_fs is not None:
                        y_lo = np.minimum(dep[:, c_fs], dep[:, ha_fs])
                        y_hi = np.maximum(dep[:, c_fs], dep[:, ha_fs])
                        fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                            line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                        ), row=1, col=col)
                        fig.add_trace(go.Scatter(x=times, y=y_hi,
                            name=f"{display} (fixed supply)", showlegend=(col == 1),
                            fill="tonexty", fillcolor=fill_dashed,
                            line=dict(color=color, width=1.5, dash="dash"), mode="lines",
                        ), row=1, col=col)

            fig.update_xaxes(title_text="Year", range=[1950, max(times)])
            fig.update_yaxes(title_text="Dependency ratio")
            fig.update_layout(title_text=f"Import Dependency Indicators — {region}{good_label}", hovermode="x unified")
            self._show_and_save_plotly(fig, f"import_dependency{good_suffix}")

        def visualize_bracketing(self, mfa, run_labels, run_letter, region="EUR", good=None):
            """Absolute net imports level with trade-scenario uncertainty band.

            Strategy = color. Ambition = line weight (thin=Conservative, thick=Highly Ambitious).
            Band = demand-following to fix_supply range per (strategy, ambition) combination.

            Note: with small CE effects the strategy lines will overlap closely, which itself
            communicates that CE barely shifts the absolute net import level relative to the
            trade uncertainty.
            """
            scenario_map = _parse_run_labels(run_labels)
            times = list(mfa.dims["t"].items)
            good_suffix = f"_{good.lower()}" if good is not None else ""
            good_label  = f" — {good}" if good is not None else ""
            all_markets = [m for m in ["steel", "indirect", "primary", "final"] if m in mfa.trade_set.markets]
            markets = [m for m in all_markets if good is None or self._market_has_good_dim(mfa, m)]
            fig = make_subplots(rows=1, cols=len(markets), subplot_titles=markets)
            legend_shown = set()

            for col, market_name in enumerate(markets, start=1):
                vals = self._net_imports_eur(mfa, market_name, region, run_letter, good=good)

                # Baseline
                bl = scenario_map.get("Baseline", {}).get("Baseline", {})
                bl_def = bl.get("default")
                bl_fs  = _fs_index(bl)
                if bl_def is not None and bl_fs is not None:
                    y_lo = np.minimum(vals[:, bl_def], vals[:, bl_fs]) / 1e6
                    y_hi = np.maximum(vals[:, bl_def], vals[:, bl_fs]) / 1e6
                    fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                        line=dict(color=_STRATEGY_COLORS["Baseline"], width=0), mode="lines", hoverinfo="skip",
                    ), row=1, col=col)
                    fig.add_trace(go.Scatter(x=times, y=y_hi,
                        name="Baseline", showlegend=(col == 1 and "Baseline" not in legend_shown),
                        fill="tonexty", fillcolor=_STRATEGY_FILL_SOLID["Baseline"],
                        line=dict(color=_STRATEGY_COLORS["Baseline"], width=2), mode="lines",
                    ), row=1, col=col)
                    legend_shown.add("Baseline")
                elif bl_def is not None:
                    fig.add_trace(go.Scatter(x=times, y=vals[:, bl_def] / 1e6,
                        name="Baseline", showlegend=(col == 1 and "Baseline" not in legend_shown),
                        line=dict(color=_STRATEGY_COLORS["Baseline"], width=2), mode="lines",
                    ), row=1, col=col)
                    legend_shown.add("Baseline")

                for strategy in _STRATEGY_ORDER:
                    ambition_dict = scenario_map.get(strategy, {})
                    if not ambition_dict:
                        continue
                    color   = _STRATEGY_COLORS[strategy]
                    fill    = _STRATEGY_FILL_SOLID[strategy]
                    display = _STRATEGY_DISPLAY[strategy]

                    for ambition in _AMBITIONS:
                        trade_dict = ambition_dict.get(ambition, {})
                        if not trade_dict:
                            continue
                        lw      = 2.5 if ambition == "Highly Ambitious" else 1.5
                        def_idx = trade_dict.get("default")
                        fs_idx  = _fs_index(trade_dict)
                        leg_key = f"{strategy}_{ambition}"
                        show_leg = col == 1 and leg_key not in legend_shown

                        if def_idx is not None and fs_idx is not None:
                            y_lo = np.minimum(vals[:, def_idx], vals[:, fs_idx]) / 1e6
                            y_hi = np.maximum(vals[:, def_idx], vals[:, fs_idx]) / 1e6
                            fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                                line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                            ), row=1, col=col)
                            fig.add_trace(go.Scatter(x=times, y=y_hi,
                                name=f"{display} ({ambition})", showlegend=show_leg,
                                fill="tonexty", fillcolor=fill,
                                line=dict(color=color, width=lw), mode="lines",
                            ), row=1, col=col)
                            legend_shown.add(leg_key)
                        elif def_idx is not None:
                            fig.add_trace(go.Scatter(x=times, y=vals[:, def_idx] / 1e6,
                                name=f"{display} ({ambition})", showlegend=show_leg,
                                line=dict(color=color, width=lw), mode="lines",
                            ), row=1, col=col)
                            legend_shown.add(leg_key)

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text="Net Imports [Mt]")
            fig.update_layout(
                title_text=f"Net Imports — trade-scenario bracket — {region}{good_label}",
                hovermode="x unified",
            )
            self._show_and_save_plotly(fig, f"bracketing_net_imports{good_suffix}")

        def visualize_gross_trade_eu(self, mfa, run_labels, run_letter, region="EUR", good=None):
            """Gross imports and exports per market for the EU region.

            Strategy = color. Ambition = filled band (Conservative → Highly Ambitious).
            Demand-following trade = solid band. Fixed-supply alpha range = dashed band
            (alpha0 to alpha1); this is where alpha matters — net imports are alpha-invariant
            but the gross import/export split is not.
            """
            scenario_map = _parse_run_labels(run_labels)
            times = list(mfa.dims["t"].items)
            good_suffix = f"_{good.lower()}" if good is not None else ""
            good_label  = f" — {good}" if good is not None else ""
            all_markets = [m for m in ["steel", "indirect", "primary", "final"] if m in mfa.trade_set.markets]
            markets = [m for m in all_markets if good is None or self._market_has_good_dim(mfa, m)]

            for market_name in markets:
                trade_mkt = mfa.trade_set.markets[market_name]
                sel = {"r": region}
                if good is not None and self._market_has_good_dim(mfa, market_name):
                    sel["g"] = good
                imports_all = trade_mkt.imports[sel].sum_to(["t", run_letter]).values
                exports_all = trade_mkt.exports[sel].sum_to(["t", run_letter]).values

                fig = make_subplots(rows=1, cols=2,
                    subplot_titles=[f"{market_name} imports", f"{market_name} exports"])
                legend_shown = set()

                for col, vals in enumerate([imports_all, exports_all], start=1):
                    # Baseline
                    bl = scenario_map.get("Baseline", {}).get("Baseline", {})
                    bl_def = bl.get("default")
                    if bl_def is not None:
                        fig.add_trace(go.Scatter(x=times, y=vals[:, bl_def] / 1e6,
                            name="Baseline",
                            showlegend=(col == 1 and "Baseline" not in legend_shown),
                            line=dict(color=_STRATEGY_COLORS["Baseline"], width=2), mode="lines",
                        ), row=1, col=col)
                        if col == 1:
                            legend_shown.add("Baseline")

                    for strategy in _STRATEGY_ORDER:
                        ambition_dict = scenario_map.get(strategy, {})
                        if not ambition_dict:
                            continue
                        color       = _STRATEGY_COLORS[strategy]
                        fill_solid  = _STRATEGY_FILL_SOLID[strategy]
                        fill_dashed = _STRATEGY_FILL_DASHED[strategy]
                        display     = _STRATEGY_DISPLAY[strategy]

                        # solid band: ambition range, demand-following
                        c_def  = ambition_dict.get("Conservative", {}).get("default")
                        ha_def = ambition_dict.get("Highly Ambitious", {}).get("default")
                        show_leg = col == 1 and strategy not in legend_shown
                        if c_def is not None and ha_def is not None:
                            y_lo = np.minimum(vals[:, c_def], vals[:, ha_def]) / 1e6
                            y_hi = np.maximum(vals[:, c_def], vals[:, ha_def]) / 1e6
                            fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                                line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                            ), row=1, col=col)
                            fig.add_trace(go.Scatter(x=times, y=y_hi,
                                name=display, showlegend=show_leg,
                                fill="tonexty", fillcolor=fill_solid,
                                line=dict(color=color, width=1.5), mode="lines",
                            ), row=1, col=col)
                            if col == 1:
                                legend_shown.add(strategy)

                        # dashed band: ambition range across alpha0→alpha1 fix_supply
                        # Gather all 4 fix_supply endpoints (C/HA × alpha0/alpha1)
                        fs_indices = [
                            ambition_dict.get(amb, {}).get(k)
                            for amb in _AMBITIONS
                            for k in ("fix_supply_alpha0", "fix_supply_alpha1")
                        ]
                        fs_indices = [i for i in fs_indices if i is not None]
                        if len(fs_indices) >= 2:
                            y_lo = np.min([vals[:, i] for i in fs_indices], axis=0) / 1e6
                            y_hi = np.max([vals[:, i] for i in fs_indices], axis=0) / 1e6
                            fig.add_trace(go.Scatter(x=times, y=y_lo, showlegend=False,
                                line=dict(color=color, width=0), mode="lines", hoverinfo="skip",
                            ), row=1, col=col)
                            fig.add_trace(go.Scatter(x=times, y=y_hi,
                                name=f"{display} (fixed supply, α∈[0,1])",
                                showlegend=(col == 1),
                                fill="tonexty", fillcolor=fill_dashed,
                                line=dict(color=color, width=1.5, dash="dash"), mode="lines",
                            ), row=1, col=col)
                        elif len(fs_indices) == 1:
                            fig.add_trace(go.Scatter(x=times, y=vals[:, fs_indices[0]] / 1e6,
                                name=f"{display} (fixed supply)", showlegend=(col == 1),
                                line=dict(color=color, width=1.5, dash="dash"), mode="lines",
                            ), row=1, col=col)

                fig.update_xaxes(title_text="Year", range=[1950, max(times)])
                fig.update_yaxes(title_text="[Mt]")
                fig.update_layout(
                    title_text=f"Gross trade ({market_name}) — {region}{good_label}",
                    hovermode="x unified",
                )
                self._show_and_save_plotly(fig, f"gross_trade_{market_name}_eu{good_suffix}")

        def visualize_global_net_imports(self, mfa, run_labels, run_letter, region="EUR", good=None):
            """Stacked gross imports and exports by region — baseline only.

            Left panel: imports stacked by region. Right panel: exports stacked by region.
            EU region highlighted in red, placed on top of the stack.
            One figure per trade market (steel, indirect).

            Shows how growing non-EU production drives export growth that the balance
            step redistributes, shrinking EU's import share over time.
            """
            scenario_map = _parse_run_labels(run_labels)
            baseline_idx = scenario_map.get("Baseline", {}).get("Baseline", {}).get("default")
            if baseline_idx is None:
                return

            baseline_label = run_labels[baseline_idx]
            times = list(mfa.dims["t"].items)
            regions = list(mfa.dims["r"].items)
            good_suffix = f"_{good.lower()}" if good is not None else ""
            good_label  = f" — {good}" if good is not None else ""

            # Colour palette: EU in red, others from qualitative palettes
            other_colors = plc.qualitative.D3 + plc.qualitative.Plotly
            palette_idx = 0
            region_colors = {}
            for r in regions:
                if r == region:
                    region_colors[r] = "#d62728"
                else:
                    region_colors[r] = other_colors[palette_idx % len(other_colors)]
                    palette_idx += 1

            all_markets = [m for m in ["steel", "indirect"] if m in mfa.trade_set.markets]
            markets = [m for m in all_markets if good is None or self._market_has_good_dim(mfa, m)]

            for market_name in markets:
                trade = mfa.trade_set.markets[market_name]
                sel = {run_letter: baseline_label}
                if good is not None and self._market_has_good_dim(mfa, market_name):
                    sel["g"] = good
                imp = trade.imports[sel].sum_to(["t", "r"]).values / 1e6
                exp = trade.exports[sel].sum_to(["t", "r"]).values / 1e6
                # shape: (n_t, n_r)

                # Sort regions by average imports ascending so EU (largest) ends on top
                avg_imp = imp.mean(axis=0)
                sorted_regions = sorted(
                    [r for r in regions if r != region],
                    key=lambda r: avg_imp[regions.index(r)],
                )
                ordered_regions = sorted_regions + [region]  # EU on top

                fig = make_subplots(
                    rows=1, cols=2,
                    subplot_titles=[f"{market_name} imports", f"{market_name} exports"],
                )
                legend_shown = set()

                for col, vals in enumerate([imp, exp], start=1):
                    for r in ordered_regions:
                        r_idx = regions.index(r)
                        fig.add_trace(go.Scatter(
                            x=times, y=vals[:, r_idx],
                            name=r,
                            stackgroup="one",
                            mode="lines",
                            line=dict(color=region_colors[r], width=0.5),
                            fillcolor=region_colors[r],
                            showlegend=(col == 1 and r not in legend_shown),
                        ), row=1, col=col)
                        legend_shown.add(r)

                fig.update_xaxes(title_text="Year", range=[1950, max(times)])
                fig.update_yaxes(title_text="[Mt]")
                fig.update_layout(
                    title_text=f"Global {market_name} trade by region — Baseline{good_label}",
                    hovermode="x unified",
                )
                self._show_and_save_plotly(fig, f"global_trade_stacked_{market_name}{good_suffix}")

        def visualize_trade_mechanism(self, mfa, run_labels, run_letter, first_future_year=None, good=None):
            """Trade mechanism per region: one subplot per region — imports/demand and exports/supply ratios over
            the full period (all years in the t dimension).
            """
            scenario_map = _parse_run_labels(run_labels)
            baseline_idx = scenario_map.get("Baseline", {}).get("Baseline", {}).get("default")
            if baseline_idx is None:
                return

            baseline_label = run_labels[baseline_idx]
            times = list(mfa.dims["t"].items)
            all_regions = list(mfa.dims["r"].items)
            n_regions = len(all_regions)
            good_suffix = f"_{good.lower()}" if good is not None else ""
            good_label  = f" — {good}" if good is not None else ""

            _ratio_colors = {
                "Imports / Demand": "#2ca02c",
                "Exports / Supply": "#d62728",
            }

            ncols = 3
            nrows = (n_regions + ncols - 1) // ncols
            all_markets = [m for m in ["indirect", "steel"] if m in mfa.trade_set.markets]
            markets = [m for m in all_markets if good is None or self._market_has_good_dim(mfa, m)]

            for market_name in markets:
                sel_base = {run_letter: baseline_label}
                if good is not None and self._market_has_good_dim(mfa, market_name):
                    sel_base["g"] = good

                # --- arrays over all t, shape (n_t, n_r) ---
                if market_name == "indirect" and "in_use" in mfa.stocks:
                    demand = (mfa.stocks["in_use"].inflow[sel_base]
                              .sum_to(["t", "r"]).values)
                elif market_name == "steel" and "ip_market => fabrication" in mfa.flows:
                    demand = (mfa.flows["ip_market => fabrication"][sel_base]
                              .sum_to(["t", "r"]).values)
                else:
                    continue

                trade = mfa.trade_set.markets[market_name]
                imp = trade.imports[sel_base].sum_to(["t", "r"]).values
                exp = trade.exports[sel_base].sum_to(["t", "r"]).values
                sup = demand + exp - imp

                # --- trade dependency ratios over full t period ---
                eps = 1.0
                ratio_id = imp / np.maximum(np.abs(demand), eps)
                ratio_es = exp / np.maximum(np.abs(sup), eps)

                fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=all_regions)
                for r_i in range(n_regions):
                    row, col = r_i // ncols + 1, r_i % ncols + 1
                    show_legend = r_i == 0
                    for label, ratios in [
                        ("Imports / Demand", ratio_id[:, r_i]),
                        ("Exports / Supply", ratio_es[:, r_i]),
                    ]:
                        fig.add_trace(go.Scatter(
                            x=times, y=ratios,
                            name=label, showlegend=show_legend,
                            line=dict(color=_ratio_colors[label], width=2),
                            mode="lines",
                        ), row=row, col=col)

                fig.add_vline(x=2022, line_dash="dot", line_color="lightgray")
                fig.update_xaxes(title_text="Year", range=[1950, max(times)])
                fig.update_yaxes(title_text="Ratio")
                fig.update_layout(
                    title_text=f"{market_name} trade ratios by region — Baseline{good_label}",
                    hovermode="x unified",
                    height=300 * nrows,
                )
                self._show_and_save_plotly(fig, f"trade_ratios_{market_name}_by_region{good_suffix}")

    return ComparisonVisualizer


# ── export ─────────────────────────────────────────────────────────────────────

def export_trade_csv(models, labels: list[str], output_dir: pathlib.Path = None):
    """Export imports and exports for every trade market and every run as CSV files.

    One file per (run, market): <run_label>_<market>.csv
    Columns: [Time, Region, (Good,) imports_t, exports_t, net_imports_t]
    """
    import pandas as pd

    if output_dir is None:
        output_dir = DIRECTORY.parent / "trade_csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    for model, label in zip(models, labels):
        mfa = model.future_mfa
        if mfa.trade_set is None:
            continue

        safe_label = (
            label.replace(" ", "_").replace("/", "_").replace("α", "alpha")
        )

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


def export_flows_csv(models, labels: list[str], output_dir: pathlib.Path = None):
    """Export steel demand and supply flows for every run as CSV files.

    Three files per run:
      <run_label>_inflow.csv          — mfa.stocks["in_use"].inflow  (demand in products)
      <run_label>_supply_by_good.csv  — mfa.flows["fabrication => good_market"]
      <run_label>_steel_demand.csv    — mfa.flows["ip_market => fabrication"]
    Columns: [Time, Region, (Good,) value_t]
    """
    if output_dir is None:
        output_dir = DIRECTORY.parent / "flows_csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    _arrays = [
        ("inflow",         lambda mfa: mfa.stocks["in_use"].inflow),
        ("supply_by_good", lambda mfa: mfa.flows["fabrication => good_market"]),
        ("steel_demand",   lambda mfa: mfa.flows["ip_market => fabrication"]),
    ]

    for model, label in zip(models, labels):
        mfa = model.future_mfa
        safe_label = label.replace(" ", "_").replace("/", "_").replace("α", "alpha")

        for name, getter in _arrays:
            try:
                arr = getter(mfa)
            except KeyError:
                continue
            df = arr.to_df().reset_index().rename(columns={"value": "value_t"})
            out_path = output_dir / f"{safe_label}_{name}.csv"
            df.to_csv(out_path, index=False)
            print(f"  {out_path.name}")

    print(f"Flow CSVs written to {output_dir}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    paths  = pick_files()
    labels = LABELS or [_make_short_label(p.stem) for p in paths]

    print(f"Loading {len(paths)} runs:")
    for label, path in zip(labels, paths):
        print(f"  {label}: {path}")

    models = load_models(paths)

    print("Exporting trade CSVs…")
    export_trade_csv(models, labels)
    print("Exporting flow CSVs…")
    export_flows_csv(models, labels)

    run_dim = fd.Dimension(letter=RUN_DIM_LETTER, name=RUN_DIM_NAME, items=labels)
    combined_mfa = build_combined_mfa(models, run_dim)

    VisualizerCls = make_comparison_visualizer(MODEL, RUN_DIM_NAME)

    # Build a fake model shell that just holds the combined MFA and the base config
    base_model = models[0]
    fake_model = copy.copy(base_model)
    fake_model.future_mfa = combined_mfa

    # Initialise visualizer from the base model's visualizer config
    base_vis = base_model.visualizer
    vis = VisualizerCls(cfg=base_vis.cfg, display_names=base_vis.display_names)

    # Force show; skip saving (filenames would collide)
    vis.cfg = vis.cfg.model_copy(update={"do_show_figs": True, "do_save_figs": False})

    print("Plotting comparison figures…")
    vis.visualize(model=fake_model)
    vis.stop_and_show()
    print("Done.")


if __name__ == "__main__":
    main()
