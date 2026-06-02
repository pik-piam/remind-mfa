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

def _parse_run_labels(labels: list[str]) -> dict:
    """Return {ce_scenario: {trade_scenario: run_index}} parsed from file-stem labels."""
    CE_TOKENS = ["Baseline", "Conservative", "Highly_mbitious"]
    result = {}
    for i, label in enumerate(labels):
        trade = "fix_supply" if "fix_supply" in label else "default"
        ce = next((tok for tok in CE_TOKENS if tok in label), "Unknown")
        result.setdefault(ce, {})[trade] = i
    return result


_CE_DISPLAY  = {"Baseline": "Baseline", "Conservative": "Conservative", "Highly_mbitious": "Highly Ambitious"}
_CE_COLORS   = {"Baseline": "#7f7f7f", "Conservative": "#1f77b4", "Highly_mbitious": "#2ca02c"}
_TRADE_DASH  = {"default": "solid", "fix_supply": "dash"}
_TRADE_LABEL = {"default": "default trade", "fix_supply": "fixed supply"}


def make_comparison_visualizer(model_name: str, run_dim_name: str):
    
    from remind_mfa.common.common_visualization import CommonVisualizer as BaseVis

    RUN = run_dim_name

    class ComparisonVisualizer(BaseVis):
        """Visualizer that overlays multiple runs by injecting a Run dimension."""

        def visualize(self, model):
            mfa = model.future_mfa
            run_letter = mfa.dims[RUN].letter
            linecolor_dims = {name: RUN for name in model.future_mfa.trade_set.markets}
            subplot_dims = {
                "steel": None,
                "indirect": "Good",
                "scrap": None,
            }
            self.visualize_trade(mfa, linecolor_dims=linecolor_dims, region = "EUR", subplot_dims=subplot_dims)
            self.visualize_flow(mfa, flow=mfa.stocks["in_use"].inflow, name="Stock inflow", region = "EUR", linecolor_dim=RUN, subplot_dim="Good")
            self.visualize_flow(mfa, flow=mfa.stocks["in_use"].outflow, name="Stock outflow", region = "EUR", linecolor_dim=RUN, subplot_dim="Good")
            if model_name == "steel":
                self.visualize_transience_eol_parameters(
                    model,
                    parameter_REMIND_MFA=mfa.parameters["recovery_rate"][{"r": "EUR", "t": mfa.dims["u"], "g": mfa.dims["f"]}],
                    parameter_EU_MFA=mfa.parameters["recovery_rate_EU-MFA"]*mfa.parameters["collection_rate_EU-MFA"],
                    subplot_dim="EU-MFA_Good",
                    linecolor_dim=RUN,
                )
                self.visualize_transience_eol_parameters(
                    model,
                    parameter_REMIND_MFA=mfa.flows["use => eol_market"].sum_to(("t", "r", run_letter))[{"r": "EUR", "t": mfa.dims["u"]}],
                    parameter_EU_MFA=mfa.parameters["available_scrap_EU-MFA"][{"r": "EUR"}],
                    linecolor_dim=RUN,
                )
            run_labels = list(mfa.dims[RUN].items)
            self.visualize_delta_net_imports(mfa, run_labels, run_letter)
            self.visualize_import_dependency(mfa, run_labels, run_letter)
            self.visualize_bracketing(mfa, run_labels, run_letter)
        
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
                colors = plc.qualitative.Dark24[:n_colors] * 2
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

            self.plot_and_save_figure(ap_flow, f"{name}.png", do_plot=False)

        # ── scenario-comparison helpers ───────────────────────────────────────

        def _net_imports_eur(self, mfa, market_name, region, run_letter):
            """Net imports for one market and region, shape (n_time, n_runs)."""
            trade = mfa.trade_set.markets[market_name]
            arr = (trade.imports - trade.exports)[{"r": region}].sum_to(["t", run_letter])
            return arr.values

        def visualize_delta_net_imports(self, mfa, run_labels, run_letter, region="EUR"):
            """Δ net imports vs Baseline for steel and indirect trade, EUR."""
            scenario_map = _parse_run_labels(run_labels)
            baseline_idx = scenario_map.get("Baseline", {}).get("default")
            if baseline_idx is None:
                return
            times = list(mfa.dims["t"].items)

            fig = make_subplots(
                rows=1, cols=2,
                subplot_titles=["Steel trade", "Indirect (goods-embedded) trade"],
            )
            for col, market_name in enumerate(["steel", "indirect"], start=1):
                vals = self._net_imports_eur(mfa, market_name, region, run_letter)
                delta = vals - vals[:, baseline_idx : baseline_idx + 1]
                for ce, trade_dict in scenario_map.items():
                    for trade_sc, run_idx in trade_dict.items():
                        if ce == "Baseline":
                            continue
                        name = f"{_CE_DISPLAY.get(ce, ce)} ({_TRADE_LABEL.get(trade_sc, trade_sc)})"
                        fig.add_trace(
                            go.Scatter(
                                x=times, y=delta[:, run_idx] / 1e6,
                                name=name,
                                showlegend=(col == 1),
                                line=dict(
                                    color=_CE_COLORS.get(ce, "black"),
                                    dash=_TRADE_DASH.get(trade_sc, "solid"),
                                ),
                                mode="lines",
                            ),
                            row=1, col=col,
                        )
                fig.add_hline(y=0, line_dash="dot", line_color="gray", row=1, col=col)

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text="Δ Net Imports [Mt]")
            fig.update_layout(
                title_text="Δ Net Imports vs Baseline — EUR steel trade",
                hovermode="x unified",
            )
            self._show_and_save_plotly(fig, "delta_net_imports")

        def visualize_import_dependency(self, mfa, run_labels, run_letter, region="EUR"):
            """Import dependency ratios for EUR: goods-based and steel-based."""
            scenario_map = _parse_run_labels(run_labels)
            times = list(mfa.dims["t"].items)
            eps = 1.0

            indirect_net = self._net_imports_eur(mfa, "indirect", region, run_letter)
            inflow = (
                mfa.stocks["in_use"].inflow[{"r": region}]
                .sum_to(["t", run_letter])
                .values
            )
            dep_goods = indirect_net / np.maximum(inflow, eps)

            steel_net = self._net_imports_eur(mfa, "steel", region, run_letter)
            production = (
                mfa.flows["ip_market => fabrication"][{"r": region}].sum_to(["t", run_letter]).values
            )
            dep_steel = steel_net / np.maximum(production, eps)

            fig = make_subplots(
                rows=1, cols=2,
                subplot_titles=[
                    "Goods trade dependency<br>(net indirect imports / stock inflow)",
                    "Steel trade dependency<br>(net steel imports / total steel supply)",
                ],
            )
            for col, dep in enumerate([dep_goods, dep_steel], start=1):
                for ce, trade_dict in scenario_map.items():
                    for trade_sc, run_idx in trade_dict.items():
                        name = f"{_CE_DISPLAY.get(ce, ce)} ({_TRADE_LABEL.get(trade_sc, trade_sc)})"
                        fig.add_trace(
                            go.Scatter(
                                x=times, y=dep[:, run_idx],
                                name=name,
                                showlegend=(col == 1),
                                line=dict(
                                    color=_CE_COLORS.get(ce, "black"),
                                    dash=_TRADE_DASH.get(trade_sc, "solid"),
                                ),
                                mode="lines",
                            ),
                            row=1, col=col,
                        )

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text="Dependency ratio")
            fig.update_layout(
                title_text="Import Dependency Indicators — EUR",
                hovermode="x unified",
            )
            self._show_and_save_plotly(fig, "import_dependency")

        def visualize_bracketing(self, mfa, run_labels, run_letter, region="EUR"):
            """Net imports with trade-scenario uncertainty bands (shaded) per CE scenario."""
            scenario_map = _parse_run_labels(run_labels)
            times = list(mfa.dims["t"].items)
            _FILL = {
                "Baseline": "rgba(127,127,127,0.15)",
                "Conservative": "rgba(31,119,180,0.15)",
                "Highly_mbitious": "rgba(44,160,44,0.15)",
            }

            fig = make_subplots(
                rows=1, cols=2,
                subplot_titles=["Steel trade", "Indirect (goods-embedded) trade"],
            )
            for col, market_name in enumerate(["steel", "indirect"], start=1):
                vals = self._net_imports_eur(mfa, market_name, region, run_letter)
                for ce, trade_dict in scenario_map.items():
                    color = _CE_COLORS.get(ce, "black")
                    fill  = _FILL.get(ce, "rgba(0,0,0,0.1)")
                    ce_label = _CE_DISPLAY.get(ce, ce)

                    if "default" in trade_dict and "fix_supply" in trade_dict:
                        y_def = vals[:, trade_dict["default"]] / 1e6
                        y_fix = vals[:, trade_dict["fix_supply"]] / 1e6
                        y_lo = np.minimum(y_def, y_fix)
                        y_hi = np.maximum(y_def, y_fix)
                        fig.add_trace(
                            go.Scatter(
                                x=times, y=y_lo,
                                name=f"{ce_label} (default trade)",
                                showlegend=(col == 1),
                                line=dict(color=color, dash="solid", width=1.5),
                                mode="lines",
                            ),
                            row=1, col=col,
                        )
                        fig.add_trace(
                            go.Scatter(
                                x=times, y=y_hi,
                                name=f"{ce_label} (fixed supply)",
                                showlegend=(col == 1),
                                line=dict(color=color, dash="dash", width=1.5),
                                fill="tonexty", fillcolor=fill,
                                mode="lines",
                            ),
                            row=1, col=col,
                        )
                    elif "default" in trade_dict:
                        y = vals[:, trade_dict["default"]] / 1e6
                        fig.add_trace(
                            go.Scatter(
                                x=times, y=y,
                                name=ce_label,
                                showlegend=(col == 1),
                                line=dict(color=color, dash="solid", width=2),
                                mode="lines",
                            ),
                            row=1, col=col,
                        )

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text="Net Imports [Mt]")
            fig.update_layout(
                title_text="Net Imports with Trade Scenario Uncertainty — EUR",
                hovermode="x unified",
            )
            self._show_and_save_plotly(fig, "bracketing_net_imports")

    return ComparisonVisualizer


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    paths  = pick_files()
    labels = LABELS or [p.stem for p in paths]

    print(f"Loading {len(paths)} runs:")
    for label, path in zip(labels, paths):
        print(f"  {label}: {path}")

    models = load_models(paths)

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
