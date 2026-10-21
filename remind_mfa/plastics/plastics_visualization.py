from pydantic import PrivateAttr
import flodym as fd
import pandas as pd

import plotly.graph_objects as go
from typing import TYPE_CHECKING, Optional
import flodym.export as fde
import plotly.express as px

from remind_mfa.common.common_visualization import CommonVisualizer

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsVisualizer(CommonVisualizer):

    _model: Optional["PlasticsModel"] = PrivateAttr(default=None)

    def visualize_custom(self):
        if self.cfg.use_stock.do_visualize:
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.stocks["use"].stock,
                name="Stock",
                linecolor_dim="End Use",
                regional=False,
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.stocks["use"].stock,
                name="Stock",
                linecolor_dim="End Use",
                regional=True,
                per_capita=True,
            )

        if self.cfg.polymer_splits.do_visualize:
            self.visualize_polymer_splits(mfa=self._model.future_mfa)

        if self.cfg.production.do_visualize:
            self.visualize_production(mfa=self._model.future_mfa, regional=True)
            self.visualize_production(mfa=self._model.future_mfa, regional=False)

        if self.cfg.extrapolation.do_visualize:
            self.visualize_extrapolation(subplot_dim="End Use", linecolor_dim="Region")
            self.visualize_extrapolation(subplot_dim="Region", linecolor_dim="End Use")

        if self.cfg.flows.do_visualize:
            self.visualize_production_trade_consumption(
                mfa=self._model.future_mfa, per_capita=False
            )
            self.visualize_production_trade_consumption(mfa=self._model.future_mfa, per_capita=True)
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["polymerization => primary_market"],
                name="Primary production",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["polymerization => primary_market"],
                name="Primary production",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["primary_market => manufacturing"],
                name="Primary plastics demand",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["manufacturing => manufactured_products_market"],
                name="Manufacturing",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.stocks["use"].inflow,
                name="Demand",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["reclmech => aux_recyclate_market"],
                name="Mechanically recycled",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["reclchem => aux_recl_feedstock_market"],
                name="Chemically recycled",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["eol_management => sorting"],
                name="Collected",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["sorting => reclmech"],
                name="Sorted to mechanical recycling",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["sorting => landfill"],
                name="Landfilled",
                linecolor_dim="Polymer",
            )
            self.visualize_fdarr_stacked(
                mfa=self._model.future_mfa,
                flow=self._model.future_mfa.flows["sorting => incineration"],
                name="Incinerated",
                linecolor_dim="Polymer",
            )
        if self.cfg.scenario_params.do_visualize:
            self.visualize_scenario_params(mfa=self._model.future_mfa)

        self.stop_and_show()

    def visualize_consumption(self, mfa: fd.MFASystem):
        per_capita = self.cfg.consumption.per_capita
        demand = mfa.stocks["use"].inflow.sum_over(("p", "e"))
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=demand,
            name="Plastic consumption",
            linecolor_dim="End Use",
            per_capita=per_capita,
            regional=True,
        )

    def visualize_production(self, mfa: fd.MFASystem, regional=True):
        production = (
            mfa.flows["polymerization => primary_market"]
            + mfa.flows["aux_recyclate_market => primary_market"]
        )
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=production,
            name="Plastics production",
            regional=regional,
            linecolor_dim="Polymer",
        )

    def visualize_production_trade_consumption(self, mfa: fd.MFASystem, per_capita=False):
        production = (
            mfa.flows["polymerization => primary_market"]
            + mfa.flows["aux_recyclate_market => primary_market"]
        ).sum_to(("t", "r"))
        primary_net_imports = (
            mfa.flows["imports => primary_market"] - mfa.flows["primary_market => exports"]
        ).sum_to(("t", "r"))
        manufactured_net_imports = (
            mfa.flows["imports => manufactured_products_market"]
            - mfa.flows["manufactured_products_market => exports"]
        ).sum_to(("t", "r"))
        consumption = mfa.stocks["use"].inflow.sum_to(("t", "r"))

        series_specs = [
            (production, "Production", "#4E79A7"),
            (primary_net_imports, "Primary net imports", "#F28E2B"),
            (manufactured_net_imports, "Manufactured products net imports", "#E15759"),
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
            f"production_trade_consumption_by_region{'_per_capita' if per_capita else ''}",
            do_plot=False,
        )

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_end_use=False):
        subplot_dim = "End Use" if subplots_by_end_use else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["use"].stock, subplot_dim=subplot_dim)

    def visualize_trade(self, mfa: fd.MFASystem, linecolor_dims=True):
        if linecolor_dims is True:
            linecolor_dims = {
                "primary": "Polymer",
                "manufactured_products": "Polymer",
                "waste": "Polymer",
                "aux_recyclate": "Polymer",
                "aux_recl_feedstock": None,
            }
        else:
            linecolor_dims = {
                "primary": None,
                "manufactured_products": None,
                "waste": None,
                "aux_recyclate": None,
                "aux_recl_feedstock": None,
            }
        super().visualize_trade(mfa, linecolor_dims=linecolor_dims)

    def visualize_sankey(self, mfa: fd.MFASystem):
        # Define colors for each stage
        production_color = "#EDC948"
        use_color = "#D4965B"
        eol_color = "#499894"
        recycle_color = "#86BCB6"
        emission_color = "#E15759"
        trade_color = "#D37295"
        atmosphere_color = "#84A3F8"

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
                if f.from_process.name in ("eol_management", "sorting")
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

        # Assign colors to atmosphere flows
        flow_color_dict.update(
            {
                fn: atmosphere_color
                for fn, f in mfa.flows.items()
                if f.from_process.name == "atmosphere"
                or f.to_process.name in ("atmosphere", "emission")
            }
        )

        # Assign colors to emission flows
        flow_color_dict.update(
            {
                fn: emission_color
                for fn, f in mfa.flows.items()
                if f.to_process.name in ("mismanaged", "uncontrolled", "emission", "losses")
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
                "flow_color_dict": flow_color_dict,
                "node_color_dict": {"default": "#CCCCCC", "use": "#999999"},
            }
        )

        # Prepare display names and generate the Sankey diagram
        # display_names_fmt = {k: f"<b>{v}</b>" for k, v in self.display_names.dct.items()}
        display_names_fmt = self.display_names.dct
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey.plotter_args
        )
        links = plotter._get_links_dict()
        nodes = plotter._get_nodes_dict()
        nodes.update(
            {
                "pad": 15,
                "thickness": 20,
            }
        )
        fig = go.Figure(
            go.Sankey(
                arrangement="snap",
                link=links,
                node=nodes,
                orientation="v",
                textfont={
                    "size": 12,
                    # "weight": 600,
                    "shadow": "0px 0px 0px rgba(0,0,0,0)",
                },
            )
        )

        # Add legend entries
        legend_entries = [
            (production_color, "Production"),
            (use_color, "Use"),
            (eol_color, "End-of-Life"),
            (recycle_color, "Recycling"),
            (emission_color, "Losses"),
            # (trade_color, "Trade"),
            (atmosphere_color, "Atmosphere"),
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
            font_size=12,
            # font_weight = 600,
            showlegend=True,
            plot_bgcolor="rgba(0,0,0,0)",
            # font_color="black",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

        self._show_and_save_plotly(fig, base_name="sankey")

    def visualize_polymer_splits(self, mfa: fd.MFASystem):

        # polymer shares are extrapolated by keeping the last historical value constant in the future, so we visualize the last historical year
        polymer_shares = mfa.parameters["polymer_shares_use_inflow"][{"t": 2024}]
        polymer_shares = polymer_shares.cumsum(dim_letter="p")

        ap_end_use_split = self.plotter_class(
            array=polymer_shares,
            intra_line_dim="Region",
            subplot_dim="End Use",
            linecolor_dim="Polymer",
            xlabel="Year",
            ylabel="Polymer Splits [%]",
            display_names=self.display_names.dct,
            title=f"Product demand polymer splits",
            chart_type="area",
        )

        self.plot_and_save_figure(ap_end_use_split, f"polymer_splits")

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
