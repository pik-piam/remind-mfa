import flodym as fd
import numpy as np
import pandas as pd

import plotly.graph_objects as go
from typing import TYPE_CHECKING
import flodym.export as fde
import plotly.express as px

from remind_mfa.common.common_visualization import CommonVisualizer

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsVisualizer(CommonVisualizer):

    def visualize_custom(self, model: "PlasticsModel"):
        if self.cfg.use_stock.do_visualize:
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.stocks["in_use"].stock,
                name="Stock",
                linecolor_dim="Good",
                regional=False,
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.stocks["in_use"].stock,
                name="Stock",
                linecolor_dim="Good",
                regional=True,
                per_capita=True,
            )

        if self.cfg.material_splits.do_visualize:
            self.visualize_material_splits(mfa=model.future_mfa)

        if self.cfg.production.do_visualize:
            self.visualize_production(mfa=model.future_mfa, regional=True)
            self.visualize_production(mfa=model.future_mfa, regional=False)

        if self.cfg.extrapolation.do_visualize:
            self.visualize_extrapolation(model=model, subplot_dim="Good", linecolor_dim="Region")
            self.visualize_extrapolation(model=model, subplot_dim="Region", linecolor_dim="Good")

        if self.cfg.flows.do_visualize:
            self.visualize_production_trade_consumption(mfa=model.future_mfa, per_capita=False)
            self.visualize_production_trade_consumption(mfa=model.future_mfa, per_capita=True)
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["polymerization => primary_market"],
                name="Primary production",
                linecolor_dim="Material",
            )
            self.visualize_fdarr(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["polymerization => primary_market"],
                name="Primary production",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["primary_market => fabrication"],
                name="Primary plastics demand",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["fabrication => good_market"],
                name="Fabrication",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.stocks["in_use"].inflow,
                name="Demand",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["reclmech => aux_recyclate_trade"],
                name="Mechanically recycled",
                linecolor_dim="Material",
            )
            self.visualize_fdarr(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["reclchem => HVC_input"],
                name="Chemically recycled",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["eol => collected"],
                name="Collected",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => reclmech"],
                name="Sorted to mechanical recycling",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => landfill"],
                name="Landfilled",
                linecolor_dim="Material",
            )
            self.visualize_fdarr_stacked(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => incineration"],
                name="Incinerated",
                linecolor_dim="Material",
            )
        if self.cfg.scenario_params.do_visualize:
            self.visualize_scenario_params(mfa=model.future_mfa)

        self.stop_and_show()

    def visualize_consumption(self, mfa: fd.MFASystem):
        per_capita = self.cfg.consumption.per_capita
        demand = mfa.stocks["in_use"].inflow.sum_over(("p", "m", "e"))
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=demand,
            name="Plastic consumption",
            linecolor_dim="Good",
            per_capita=per_capita,
            regional=True,
        )

    def visualize_production(self, mfa: fd.MFASystem, regional=True):
        production = (
            mfa.flows["polymerization => primary_market"] + mfa.flows["reclmech => aux_recyclate_trade"]
        )
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=production,
            name="Plastics production",
            regional=regional,
            linecolor_dim="Material",
        )

    def visualize_production_trade_consumption(self, mfa: fd.MFASystem, per_capita=False):
        production = (
            mfa.flows["polymerization => primary_market"] + mfa.flows["reclmech => primary_market"]
        ).sum_to(("t", "r"))
        primary_net_imports = (
            mfa.flows["imports => primary_market"] - mfa.flows["primary_market => exports"]
        ).sum_to(("t", "r"))
        final_net_imports = (
            mfa.flows["imports => good_market"] - mfa.flows["good_market => exports"]
        ).sum_to(("t", "r"))
        consumption = mfa.stocks["in_use"].inflow.sum_to(("t", "r"))

        series_specs = [
            (production, "Production", "#4E79A7"),
            (primary_net_imports, "Primary net imports", "#F28E2B"),
            (final_net_imports, "Final net imports", "#E15759"),
            (consumption, "Consumption", "#59A14F"),
        ]

        if per_capita:
            population = mfa.parameters["population"]
            series_specs = [
                (array / population, f"{label} (per capita)", color)
                for array, label, color in series_specs
            ]

        series_colors = [color for _, _, color in series_specs]

        fig = None
        for idx, (array, label, color) in enumerate(series_specs):
            ap = self.plotter_class(
                array=array,
                intra_line_dim="Time",
                subplot_dim="Region",
                fig=fig,
                title=(
                    "Plastics production, net imports, and consumption by region"
                    if idx == 0
                    else None
                ),
                xlabel="Year",
                ylabel="Flow [t]",
                line_label=label,
                color_map=series_colors,
            )
            fig = ap.plot()

        self.plot_and_save_figure(
            ap,
            f"production_trade_consumption_by_region{'_per_capita' if per_capita else ''}.png",
            do_plot=False,
        )

    def compare_demand(self, mfa: fd.MFASystem):
        df = pd.read_csv("data/plastics/input/validation.csv", sep=";")

        # Convert year to numeric
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        # Convert Mt to t
        df["value"] = df["value"] * 1000 * 1000

        # Plotly line plot
        fig = px.line(df, x="year", y="value", color="source", markers=True)

        ap = self.plotter_class(
            array=mfa.stocks["in_use"].inflow.sum_over(("r", "p", "m", "e", "g")),
            intra_line_dim="Time",
            title="Demand [t]",
            line_label="REMIND-MFA",
            fig=fig,
        )
        ap.plot()
        self.plot_and_save_figure(ap, "demand_validation.png", do_plot=False)

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        subplot_dim = "Good" if subplots_by_good else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["in_use"].stock, subplot_dim=subplot_dim)

    def visualize_trade(self, mfa: fd.MFASystem, linecolor_dims=True):
        if linecolor_dims is True:
            linecolor_dims = {
                "primary": "Material",
                "final": "Material",
                "waste": "Material",
            }
        else:
            linecolor_dims = {
                "primary": None,
                "final": None,
                "waste": None,
            }
        super().visualize_trade(mfa, linecolor_dims=linecolor_dims)

    def visualize_sankey(self, mfa: fd.MFASystem):
        # Define colors for each stage
        production_color = "#EDC948"
        use_color = "#9EC3D5"
        eol_color = "#499894"
        recycle_color = "#86BCB6"
        emission_color = "#E15759"
        trade_color = "#D37295"

        # Initialize default flow color mapping
        flow_color_dict = {"default": production_color}

        # Assign colors to 'use' flows
        flow_color_dict.update(
            {
                fn: use_color
                for fn, f in mfa.flows.items()
                if f.from_process.name == "use" or f.to_process.name == "use"
            }
        )

        # Assign colors to end-of-life flows
        flow_color_dict.update(
            {
                fn: eol_color
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("eol", "collected")
            }
        )

        # Assign colors to emission flows
        flow_color_dict.update(
            {
                fn: emission_color
                for fn, f in mfa.flows.items()
                if f.to_process.name
                in ("atmosphere", "mismanaged", "uncontrolled", "emission", "losses")
            }
        )

        # Assign colors to recycling flows
        flow_color_dict.update(
            {
                fn: recycle_color
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("reclmech", "reclchem")
                or f.to_process.name in ("reclmech", "reclchem")
            }
        )

        # Assign colors to trade flows
        flow_color_dict.update(
            {
                fn: trade_color
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("imports", "exports")
                or f.to_process.name in ("imports", "exports")
            }
        )

        # Update Sankey layout configuration
        self.cfg.sankey.plotter_args.update(
            {
                "valueformat": ".2s",  # scientific notation, two significant digits
                "node_pad": 15,  # padding between nodes
                "node_thickness": 20,  # node thickness
                "arrangement": "snap",  # reduce crossings by snapping nodes
                "flow_color_dict": flow_color_dict,
                "node_color_dict": {"default": "gray", "use": "black"},
            }
        )

        # Prepare display names and generate the Sankey diagram
        display_names_fmt = {k: f"<b>{v}</b>" for k, v in self.display_names.dct.items()}
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey.plotter_args
        )
        fig = plotter.plot()

        # Add legend entries
        legend_entries = [
            (production_color, "Production"),
            (use_color, "Use"),
            (eol_color, "End-of-Life"),
            (recycle_color, "Recycling"),
            (emission_color, "Losses"),
            (trade_color, "Trade"),
        ]
        for color, label in legend_entries:
            fig.add_trace(
                go.Scatter(
                    mode="markers",
                    x=[None],
                    y=[None],
                    marker=dict(size=10, color=color, symbol="square"),
                    name=label,
                )
            )

        # Final layout adjustments and display
        fig.update_layout(
            font_size=18, showlegend=True, plot_bgcolor="rgba(0,0,0,0)", font_color="black"
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

        self._show_and_save_plotly(fig, name="sankey")

    def visualize_material_splits(self, mfa: fd.MFASystem):

        # material shares are extrapolated by keeping the last historic value constant in the future, so we visualize the last historic year
        material_shares = mfa.parameters["material_shares_use_inflow"][{"t": 2024}].sum_over(("p",))
        material_shares = material_shares.cumsum(dim_letter="m")

        ap_sector_splits = self.plotter_class(
            array=material_shares,
            intra_line_dim="Region",
            subplot_dim="Good",
            linecolor_dim="Material",
            xlabel="Year",
            ylabel="Material Splits [%]",
            display_names=self.display_names.dct,
            title=f"Product demand material splits",
            chart_type="area",
        )

        self.plot_and_save_figure(ap_sector_splits, f"material_splits.png")

    def visualize_extrapolation(
        self,
        model: "PlasticsModel",
        subplot_dim: str = "Region",
        linecolor_dim: str = None,
        show_extrapolation: bool = True,
        show_future: bool = True,
    ):
        super().visualize_extrapolation(
            model=model,
            subplot_dim=subplot_dim,
            linecolor_dim=linecolor_dim,
            show_extrapolation=show_extrapolation,
            show_future=show_future,
        )

    def visualize_scenario_params(self, mfa: fd.MFASystem):
        rates = [
            ("collection_rate", "Collection rate"),
            ("landfill_rate", "Landfill rate"),
            ("mechanical_recycling_rate", "Mechanical recycling rate"),
            ("chemical_recycling_rate", "Chemical recycling rate"),
            ("bio_production_rate", "Bio-based production rate"),
            ("daccu_production_rate", "DACCU production rate"),
        ]
        for param_name, display_name in rates:
            self.visualize_fdarr(
                mfa=mfa,
                flow=mfa.parameters[param_name],
                name=display_name,
                y_unit="%",
                scale=100,
            )
