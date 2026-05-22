import numpy as np
import os
from plotly import colors as plc
import plotly.graph_objects as go
import pyam
import flodym as fd
from typing import TYPE_CHECKING
import flodym.export as fde

from remind_mfa.common.common_visualization import CommonVisualizer
from remind_mfa.steel.steel_config import SteelVisualizationCfg

if TYPE_CHECKING:
    from remind_mfa.steel.steel_model import SteelModel


class SteelVisualizer(CommonVisualizer):

    cfg: SteelVisualizationCfg

    def visualize_custom(self, model: "SteelModel"):
        if self.cfg.production.do_visualize:
            self.visualize_production(mfa=model.future_mfa, regional=True)
            self.visualize_production(mfa=model.future_mfa, regional=False)
        if self.cfg.scrap_demand_supply.do_visualize:
            self.visualize_scrap_demand_supply(model.future_mfa, regional=True)
            self.visualize_scrap_demand_supply(model.future_mfa, regional=False)
        self.stop_and_show()

    def visualize_consumption(self, mfa: fd.MFASystem):
        self.visualize_flow_stacked(
            mfa=mfa,
            flow=mfa.stocks["in_use"].inflow,
            name="Consumption",
            linecolor_dim="Good",
            regional=True,
        )

    def visualize_sankey(self, mfa: fd.MFASystem):
        good_colors = [f"hsl({190 + 10 *i},40,{77-5*i})" for i in range(4)]
        production_color = "hsl(50,40,70)"
        scrap_color = "hsl(120,40,70)"
        losses_color = "hsl(20,40,70)"
        trade_color = "hsl(260,20,80)"

        flow_color_dict = {"default": production_color}
        flow_color_dict.update(
            {fn: ("Good", good_colors) for fn, f in mfa.flows.items() if "Good" in f.dims}
        )
        flow_color_dict.update(
            {
                fn: scrap_color
                for fn, f in mfa.flows.items()
                if f.from_process.name == "scrap_market" or f.to_process.name == "scrap_market"
            }
        )
        flow_color_dict.update(
            {
                fn: losses_color
                for fn, f in mfa.flows.items()
                if f.to_process.name in ["losses", "excess_scrap", "obsolete"]
            }
        )
        flow_color_dict.update(
            {
                fn: trade_color
                for fn, f in mfa.flows.items()
                if f.from_process.name == "imports" or f.to_process.name == "exports"
            }
        )
        self.cfg.sankey.plotter_args["flow_color_dict"] = flow_color_dict

        self.cfg.sankey.plotter_args["node_color_dict"] = {"default": "gray", "use": "black"}

        sdn = {k: f"<b>{v}</b>" for k, v in self.display_names.dct.items()}
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=sdn, **self.cfg.sankey.plotter_args
        )
        fig = plotter.plot()

        legend_entries = [
            [production_color, "Production Phase"],
            [scrap_color, "Scrap Treatment"],
            [losses_color, "Losses and Waste"],
            ["white", ""],
            ["white", "Product Phase"],
        ]
        for good, color in zip(mfa.dims["Good"].items, good_colors):
            # legend_entries.append([color, f"Product Phase ({good})"])
            legend_entries.append([color, good])

        for entry in legend_entries:
            fig.add_trace(
                go.Scatter(
                    mode="markers",
                    x=[None],
                    y=[None],
                    marker=dict(size=10, color=entry[0], symbol="square"),
                    name=entry[1],
                )
            )

        fig.update_layout(
            # title_text=f"Steel Flows ({', '.join([str(v) for v in self.sankey['slice_dict'].values()])})",
            font_size=18,
            showlegend=True,
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="black",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

        self._show_and_save_plotly(fig, name="sankey")

    def visualize_production_consumption(self, mfa: fd.MFASystem, regional=True):
        flw = mfa.flows
        production = flw["bof_production => forming"] + flw["eaf_production => forming"]
        fabrication = flw["ip_market => fabrication"]
        consumption = mfa.stocks["in_use"].inflow.sum_over("g")
        array_dict = {
            "Production": production,
            "Fabrication": fabrication,
            "Consumption": consumption,
        }

        subplot_dim, summing_func, name_str = self._get_regional_vs_global_params(regional)

        # visualize regional production
        fig = None
        for label, array in array_dict.items():
            plotter = self.plotter_class(
                array=summing_func(array),
                intra_line_dim="Time",
                **subplot_dim,
                line_label=label,
                display_names=self.display_names.dct,
                xlabel="Year",
                ylabel="Steel Flows [t]",
                fig=fig,
                # title=f"Steel Production {name_str}",
            )
            fig = plotter.plot()

        self.plot_and_save_figure(plotter, f"production_{name_str}.png", do_plot=False)

    def visualize_production(self, mfa: fd.MFASystem, regional=True):
        production = mfa.flows["bof_production => forming"] + mfa.flows["eaf_production => forming"]
        self.visualize_flow(mfa=mfa, flow=production, name="Steel production", regional=regional)

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        subplot_dim = "Good" if subplots_by_good else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["in_use"].stock, subplot_dim=subplot_dim)

    def visualize_trade(self, mfa: fd.MFASystem, linecolor_dims=False):
        if linecolor_dims is True:
            linecolor_dims = {
                "steel": None,
                "indirect": "Good",
                "scrap": None,
            }
        else:
            linecolor_dims = {
                "steel": None,
                "indirect": None,
                "scrap": None,
            }
        super().visualize_trade(mfa, linecolor_dims=linecolor_dims)

    def visualize_scrap_demand_supply(self, mfa: fd.MFASystem, regional=True):

        subplot_dim, summing_func, name_str = self._get_regional_vs_global_params(regional)

        flw = mfa.flows
        prm = mfa.parameters

        total_production = (
            flw["forming => ip_market"] / (prm["forming_yield"] * (1 - prm["production_loss_rate"]))
        )[{"t": mfa.dims["h"]}]
        scrap_supply = (
            flw["recycling => scrap_market"]
            + flw["forming => scrap_market"]
            + flw["fabrication => scrap_market"]
        )
        scrap_supply = scrap_supply[{"t": mfa.dims["h"]}]

        ap = self.plotter_class(
            array=summing_func(scrap_supply),
            intra_line_dim="Historic Time",
            **subplot_dim,
            line_label="Model",
            # fig=fig,
            display_names=self.display_names.dct,
        )
        fig = ap.plot()

        ap = self.plotter_class(
            array=summing_func(mfa.parameters["scrap_consumption"]),
            intra_line_dim="Historic Time",
            **subplot_dim,
            line_label="Real World" + (" - Reconstructed" if regional else ""),
            fig=fig,
            xlabel="Year",
            ylabel="Scrap [t]",
            line_type="dot" if regional else "solid",
            display_names=self.display_names.dct,
            title="Scrap Demand and Supply",
        )
        fig = ap.plot()

        if regional:
            v = mfa.parameters["scrap_consumption_no_assumptions"].values
            v[v == 0] = np.nan
            ap = self.plotter_class(
                array=summing_func(mfa.parameters["scrap_consumption_no_assumptions"]),
                intra_line_dim="Historic Time",
                **subplot_dim,
                line_label="Real World",
                fig=fig,
                xlabel="Year",
                ylabel="Scrap [t]",
                display_names=self.display_names.dct,
                title="Scrap Demand and Supply",
            )
            fig = ap.plot()

        ap = self.plotter_class(
            array=summing_func(total_production.sum_to(("h", "r"))),
            intra_line_dim="Historic Time",
            **subplot_dim,
            line_label="Total Production",
            line_type="dash",
            fig=fig,
        )

        # for trade_name, trade in mfa.trade_set.markets.items():
        #     fig = ap.plot()

        #     ap = self.plotter_class(
        #         array=summing_func(trade.net_imports[{"t": mfa.dims["h"]}].sum_to(("h", "r"))),
        #         intra_line_dim="Historic Time",
        #         **subplot_dim,
        #         line_label=f"Net imports ({trade_name})",
        #         line_type="dot",
        #         fig=fig,
        #     )

        self.plot_and_save_figure(ap, f"scrap_demand_supply_{name_str}.png")
