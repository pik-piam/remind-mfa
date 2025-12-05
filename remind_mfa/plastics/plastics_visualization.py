import flodym as fd
import numpy as np
import pandas as pd

from plotly import colors as plc
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pyam
from typing import TYPE_CHECKING
import flodym.export as fde
from typing import Any, List, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.colors as pc


from remind_mfa.common.common_visualization import CommonVisualizer

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsVisualizer(CommonVisualizer):

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        "sysenv": "System environment",
        "virginfoss": "Prim(fossil)",
        "virginbio": "Prim(biomass)",
        "virgindaccu": "Prim(daccu)",
        "virginccu": "Prim(ccu)",
        "virgin": "Prim(total)",
        "processing": "Proc",
        "fabrication": "Fabri",
        "reclmech": "Mech recycling",
        "reclchem": "Chem recycling",
        "use": "Use Phase",
        "eol": "EoL",
        "collected": "Collect",
        "mismanaged": "Uncollected",
        "incineration": "Incineration",
        "landfill": "Landfill",
        "uncontrolled": "Uncontrolled",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
        "waste_market": "Waste Market",
        "primary_market": "Prim Market",
        "intermediate_market": "Inter Market",
        "good_market": "Good Market",
    }

    def visualize_custom(self, model: "PlasticsModel"):
        if self.cfg.production.do_visualize:
            self.visualize_demand(mfa=model.mfa_future)

        if self.cfg.extrapolation.do_visualize:
            self.visualize_extrapolation(model=model)

        if self.cfg.flows.do_visualize:
            primary_production = (
                model.mfa_future.flows["virginfoss => virgin"]
                + model.mfa_future.flows["virginbio => virgin"]
                + model.mfa_future.flows["virgindaccu => virgin"]
                + model.mfa_future.flows["virginccu => virgin"]
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=primary_production,
                name="Primary production",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["virgin => processing"],
                name="Domestic primary production",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["reclmech => processing"],
                name="Mechanical recycling",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["reclchem => virgin"],
                name="Chemical recycling",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["eol => collected"],
                name="Collected",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["collected => landfill"],
                name="Landfilled",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.stocks["in_use"].inflow,
                name="Demand",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["fabrication => good_market"],
                name="Final exports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["good_market => use"],
                name="Final imports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["processing => intermediate_market"],
                name="Intermediate exports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["intermediate_market => fabrication"],
                name="Intermediate imports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["virgin => primary_market"],
                name="Primary exports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["primary_market => processing"],
                name="Primary imports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["collected => waste_market"],
                name="Waste exports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["waste_market => collected"],
                name="Waste imports",
                subplot_dim="Region",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.mfa_future,
                flow=model.mfa_future.flows["fabrication => use"],
                name="Domestic Fabrication",
                subplot_dim="Region",
                linecolor_dim="Material",
            )

        self.stop_and_show()

    def visualize_flow(
        self, mfa: fd.MFASystem, flow: fd.Flow, name: str, subplot_dim=None, linecolor_dim=None
    ):

        x_array = None
        x_label = "Year"
        y_label = "Flow [Mt]"
        subplot_dimletter = ()
        linecolor_dimletter = ()
        if subplot_dim is not None:
            subplot_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == subplot_dim
            )
        if linecolor_dim is not None:
            linecolor_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == linecolor_dim
            )
        sum_dims = tuple(
            x for x in flow.dims.letters if x not in (subplot_dimletter, linecolor_dimletter, "t")
        )
        flow = flow.sum_over(sum_dims)

        if subplot_dim == "Region":
            title = f"Regional {name} Flow"
            tag = "_regional"
        elif subplot_dim == "Material":
            title = f"Material {name} Flow"
            tag = "_perMaterial"
        elif subplot_dim == "Good":
            title = f"Good {name} Flow"
            tag = "_perGood"
        else:
            subplot_dim = None
            tag = ""
            title = f"Global {name} Flow"

        ap = self.plotter_class(
            array=flow,
            intra_line_dim="Time",
            linecolor_dim=linecolor_dim,
            subplot_dim=subplot_dim,
            x_array=x_array,
            title=title,
            line_type="dot",
            x_label=x_label,
            y_label=y_label,
        )
        self.plot_and_save_figure(ap, f"{name}_flow{tag}.png")

    def visualize_demand(self, mfa: fd.MFASystem):
        fig, ap_demand = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=mfa.stocks["in_use"].inflow.sum_over(("m", "e")),
            subplot_dim="Region",
            linecolor_dim="Good",
            x_label="Year",
            y_label="Demand [Mt]",
        )
        self.plot_and_save_figure(ap_demand, "demand_history_and_future.png", do_plot=False)

        demand = mfa.stocks["in_use"].inflow.sum_over(("r", "m", "e"))
        good_dim = demand.dims.index("g")
        demand = demand.apply(np.cumsum, kwargs={"axis": good_dim})
        ap = self.plotter_class(
            array=demand,
            intra_line_dim="Time",
            linecolor_dim="Good",
            chart_type="area",
            display_names=self._display_names,
            title="Demand [Mt]",
        )
        fig = ap.plot()
        self.plot_and_save_figure(ap, "demand_stacked.png", do_plot=False)

    def visualize_stock(self, mfa: fd.MFASystem, subplots_by_good=False):

        stock = mfa.stocks["in_use"].stock.sum_over(("r", "m", "e"))
        good_dim = stock.dims.index("g")
        stock = stock.apply(np.cumsum, kwargs={"axis": good_dim})
        ap = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Good",
            chart_type="area",
            display_names=self._display_names,
            title="Stock [Mt]",
        )
        fig = ap.plot()
        self.plot_and_save_figure(ap, "stock_stacked.png", do_plot=False)

        per_capita = self.cfg.use_stock.per_capita

        stock = mfa.stocks["in_use"].stock * 1000 * 1000
        population = mfa.parameters["population"]
        x_array = None

        pc_str = " pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Plastic Stock{pc_str} [t]"
        title = f"Plastic Stocks{pc_str}"
        if self.cfg.use_stock.over_gdp:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"]
            if not per_capita:
                x_array = x_array * population

        if subplots_by_good:
            subplot_dim = {"subplot_dim": "Good"}
        else:
            subplot_dim = {}
            stock = stock.sum_over("g")
        stock = stock.sum_over(["e", "m"])

        if per_capita:
            stock = stock / population

        colors = plc.qualitative.Dark24
        colors = (
            colors[: stock.dims["r"].len]
            + colors[: stock.dims["r"].len]
            + ["black" for _ in range(stock.dims["r"].len)]
        )

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=title,
            color_map=colors,
            line_type="dot",
            suppress_legend=True,
        )
        fig = ap_stock.plot()

        hist_stock = stock[{"t": mfa.dims["h"]}]
        hist_x_array = x_array[{"t": mfa.dims["h"]}] if x_array is not None else None
        ap_hist_stock = self.plotter_class(
            array=hist_stock,
            intra_line_dim="Historic Time",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=hist_x_array,
            fig=fig,
            color_map=colors,
        )
        fig = ap_hist_stock.plot()

        last_year_dim = fd.Dimension(
            name="Last Historic Year", letter="l", items=[mfa.dims["h"].items[-1]]
        )
        scatter_stock = hist_stock[{"h": last_year_dim}]
        scatter_x_array = hist_x_array[{"h": last_year_dim}] if hist_x_array is not None else None
        ap_scatter_stock = self.plotter_class(
            array=scatter_stock,
            intra_line_dim="Last Historic Year",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=scatter_x_array,
            fig=fig,
            chart_type="scatter",
            color_map=colors,
            suppress_legend=True,
        )
        fig = ap_scatter_stock.plot()

        # if self.cfg.plotting_engine == "plotly":
        #     fig.update_xaxes(type="log", range=[3, 5])
        # elif self.cfg.plotting_engine == "pyplot":
        #     for ax in fig.get_axes():
        #         ax.set_xscale("log")
        #         ax.set_xlim(1e3, 1e5)

        self.plot_and_save_figure(
            ap_scatter_stock,
            f"plastic_stocks_global_by_region{'_per_capita' if per_capita else ''}.png",
            do_plot=False,
        )

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
                in ("atmosphere", "mismanaged", "incineration", "uncontrolled", "emission")
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
        display_names_fmt = {k: f"<b>{v}</b>" for k, v in self._display_names.items()}
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey.plotter_args
        )
        fig = plotter.plot()

        # Add legend entries
        legend_entries = [
            (production_color, "Production"),
            (eol_color, "End-of-Life"),
            (recycle_color, "Recycling"),
            (use_color, "Use"),
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

    def visualize_extrapolation(self, model: "PlasticsModel"):
        mfa = model.mfa_future
        per_capita = self.cfg.use_stock.per_capita
        subplot_dim = "Region"
        linecolor_dim = "Good"
        stock = mfa.stocks["in_use"].stock
        population = mfa.parameters["population"]
        x_array = None

        pc_str = "pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Stock{pc_str} [t]"
        title = f"Stock Extrapolation: Historic and Projected vs Pure Prediction"

        dimlist = ["t"]
        if subplot_dim is not None:
            subplot_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == subplot_dim
            )
            dimlist.append(subplot_dimletter)
        if linecolor_dim is not None:
            linecolor_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == linecolor_dim
            )
            dimlist.append(linecolor_dimletter)

        other_dimletters = tuple(letter for letter in stock.dims.letters if letter not in dimlist)
        stock = stock.sum_over(other_dimletters) * 1000 * 1000
        other_dimletters = tuple(
            letter
            for letter in model.mfa_future.stock_handler.pure_prediction.dims.letters
            if letter not in dimlist
        )
        pure_prediction = (
            model.mfa_future.stock_handler.pure_prediction.sum_over(other_dimletters) * 1000 * 1000
        )

        if self.cfg.use_stock.over_gdp:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"].cast_to(stock.dims)
            if self.cfg.use_stock.accumulate_gdp:
                x_array[...] = np.maximum.accumulate(x_array.values, axis=0)
                x_label = f"GDPacc/PPP{pc_str} [2005 USD]"
            if not per_capita:
                x_array = x_array * population

        if per_capita:
            stock = stock / population

        fig, ap_final_stock = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=stock,
            subplot_dim=subplot_dim,
            linecolor_dim=linecolor_dim,
            x_array=x_array,
            x_label=x_label,
            y_label=y_label,
            title=title,
            # line_label="Historic + Modelled Future",
        )

        # extrapolation
        ap_pure_prediction = self.plotter_class(
            array=pure_prediction,
            intra_line_dim="Time",
            subplot_dim=subplot_dim,
            linecolor_dim=linecolor_dim,
            x_array=x_array,
            x_label=x_label,
            y_label=y_label,
            title=title,
            fig=fig,
            line_type="dot",
            # line_label="Pure Extrapolation",
            color_map=ap_final_stock.color_map * 2,
            suppress_legend=True,
        )
        fig = ap_pure_prediction.plot()

        if self.cfg.plotting_engine == "plotly" and self.cfg.use_stock.over_gdp:
            fig.update_xaxes(title=x_label, type="log")
        elif self.cfg.plotting_engine == "pyplot" and self.cfg.use_stock.over_gdp:
            for ax in fig.get_axes():
                ax.set_xscale("log")
                ax.set_xlabel(x_label)

        self.plot_and_save_figure(
            ap_pure_prediction,
            f"stocks_extrapolation{'_overGDP' if self.cfg.use_stock.over_gdp else '_overTime'}.png",
            do_plot=False,
        )
