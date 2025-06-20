import flodym as fd
import numpy as np

from plotly import colors as plc
import plotly.graph_objects as go
from typing import TYPE_CHECKING
import flodym.export as fde

from remind_mfa.common.common_export import CommonDataExporter

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CommonDataExporter):

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        "sysenv": "System environment",
        "virginfoss": "Prim(fossil)",
        "virginbio": "Prim(biomass)",
        "virgindaccu": "Prim(daccu)",
        "virginccu": "Prim(ccu)",
        "virgin": "Prim(total)",
        "fabrication": "Fabri",
        "recl": "Recycling(total)",
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
        "wasteimport": "Import waste",
        "wasteexport": "Export waste",
        "wastetrade": "Waste trade",
        "final_imports": "Final Imports",
        "final_exports": "Final Exports",
        "good_market": "Good Market",
    }

    def visualize_results(self, model: "PlasticsModel"):
        self.export_eol_data_by_region_and_year(mfa=model.mfa_future)
        self.export_use_data_by_region_and_year(mfa=model.mfa_future)
        self.export_recycling_data_by_region_and_year(mfa=model.mfa_future)

        if self.cfg.production["do_visualize"]:
            self.visualize_production(mfa=model.mfa_future)

        if self.cfg.use_stock["do_visualize"]:
            self.visualize_stock(mfa=model.mfa_future, subplots_by_good=False)

        if self.cfg.sankey["do_visualize"]:
            self.visualize_sankey(mfa=model.mfa_future)
        self.stop_and_show()

    def visualize_production(self, mfa: fd.MFASystem):
        ap_modeled = self.plotter_class(
            array=mfa.stocks["in_use"].inflow.sum_over(("r", "m", "e")),
            intra_line_dim="Time",
            subplot_dim="Good",
            line_label="Modeled",
            display_names=self._display_names,
        )
        fig = ap_modeled.plot()
        ap_historic = self.plotter_class(
            array=mfa.parameters["production"].sum_over("r"),
            intra_line_dim="Historic Time",
            subplot_dim="Good",
            line_label="Historic Production",
            fig=fig,
            xlabel="Year",
            ylabel="Production [Mt]",
            display_names=self._display_names,
        )
        self.plot_and_save_figure(ap_historic, "production.png")

    def visualize_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        per_capita = self.cfg.use_stock["per_capita"]

        stock = mfa.stocks["in_use"].stock * 1000 * 1000
        population = mfa.parameters["population"]
        x_array = None

        pc_str = " pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Plastic Stock{pc_str} [t]"
        title = f"Plastic Stocks{pc_str}"
        if self.cfg.use_stock.get("over_gdp", False):
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

        if self.cfg.plotting_engine == "plotly":
            fig.update_xaxes(type="log", range=[3, 5])
        elif self.cfg.plotting_engine == "pyplot":
            for ax in fig.get_axes():
                ax.set_xscale("log")
                ax.set_xlim(1e3, 1e5)

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
                if f.from_process.name in ("reclmech", "reclchem", "recl")
                or f.to_process.name in ("reclmech", "reclchem", "recl")
            }
        )

        # Update Sankey layout configuration
        self.cfg.sankey.update(
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
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey
        )
        fig = plotter.plot()

        # Add legend entries
        legend_entries = [
            (production_color, "Production"),
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

    def export_eol_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "eol_by_region_year.csv"
    ):
        if "use => eol" not in mfa.flows:
            raise KeyError("The MFA system does not contain 'eol' in flows.")
        eol_data = (
            mfa.flows["eol => collected"]
            + mfa.flows["wasteimport => collected"]
            - mfa.flows["collected => wasteexport"]
        )
        df = eol_data.to_df(index=True)
        df_grouped = df.groupby(["Time", "Region", "Material"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)

    def export_use_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "use_by_region_year.csv"
    ):
        if "fabrication => use" not in mfa.flows:
            raise KeyError(f"The MFA system does not contain 'use' in flows.")

        df = mfa.flows["fabrication => use"].to_df(index=True)
        df_grouped = df.groupby(["Time", "Region"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)

    def export_recycling_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "recycling_by_region_year.csv"
    ):

        if "collected => reclmech" not in mfa.flows:
            raise KeyError(f"The MFA system does not contain 'reclmech' in flows.")
        recl_data = mfa.flows["collected => reclmech"] + mfa.flows["collected => reclchem"]
        df = recl_data.to_df(index=True)

        df_grouped = df.groupby(["Time", "Region", "Material"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)
