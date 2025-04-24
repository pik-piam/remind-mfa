import flodym as fd
import pandas as pd
import xarray as xr

from plotly import colors as plc
import plotly.graph_objects as go
from typing import TYPE_CHECKING
import flodym.export as fde

from simson.common.custom_export import CustomDataExporter

if TYPE_CHECKING:
    from simson.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CustomDataExporter):

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        "sysenv": "System environment",
        "wastetrade": "Waste trade pool",
        "virginfoss": "Virgin production (fossil)",
        "virginbio": "Virgin production (biomass)",
        "virgindaccu": "Virgin production (daccu)",
        "virginccu": "Virgin production (ccu)",
        "virgin": "Virgin production (total)",
        "fabrication": "Fabrication",
        "recl": "Recycling (total)",
        "reclmech": "Mechanical recycling",
        "reclchem": "Chemical recycling",
        "use": "Use Phase",
        "eol": "End of Life",   
        "wasteimport": "Import waste",
        "wasteexport": "Export waste",
        "collected": "Collection of plastics for disposal",
        "mismanaged": "Uncollected plastics",
        "incineration": "Incineration",
        "landfill": "Landfill",
        "uncontrolled": "Uncontrolled release",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
    }

    def visualize_results(self, model: "PlasticsModel"):
        if self.cfg.production["do_visualize"]:
            self.visualize_production(mfa=model.mfa)
            self.export_eol_data_by_region_and_year(mfa=model.mfa)
            self.export_use_data_by_region_and_year(mfa=model.mfa)

        #if self.cfg.stock["do_visualize"]:
        #    print("Stock visualization not implemented yet.")
            # self.visualize_stock(mfa=mfa)
        if self.cfg.sankey["do_visualize"]:
            self.visualize_sankey(mfa=model.mfa)
        self.stop_and_show()

    def visualize_production(self, mfa: fd.MFASystem):
        ap_modeled = self.plotter_class(
            array=mfa.stocks["in_use"].inflow.sum_over(("r","m", "e")),
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

    def visualize_stock(
        self, gdppc, historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc
    ):

        if self.cfg.stock["per_capita"]:
            stocks_plot = stocks_pc
            historic_stocks_plot = historic_stocks_pc
        else:
            stocks_plot = stocks
            historic_stocks_plot = historic_stocks

        if self.cfg.stock["over"] == "time":
            x_array, x_array_hist = None, None
            xlabel = "Year"
        elif self.cfg.stock["over"] == "gdppc":
            x_array = gdppc
            x_array_hist = historic_gdppc
            xlabel = "GDP per capita [USD]"

        ap_modeled = self.plotter_class(
            array=stocks_plot,
            intra_line_dim="Time",
            x_array=x_array,
            subplot_dim="Good",
            line_label="Modeled",
            display_names=self._display_names,
        )
        fig = ap_modeled.plot()
        ap_historic = self.plotter_class(
            array=historic_stocks_plot,
            intra_line_dim="Historic Time",
            x_array=x_array_hist,
            subplot_dim="Good",
            line_label="Historic",
            fig=fig,
            xlabel=xlabel,
            ylabel="Stock [t]",
            display_names=self._display_names,
        )

        self.plot_and_save_figure(ap_historic, "stock.png")
    
    def visualize_sankey(self, mfa: fd.MFASystem):
        # Define color palette for different plastic life-cycle stages
        production_color = "hsl(50,40,70)"
        recycling_color = "hsl(120,40,70)"
        use_color = "hsl(220,40,70)"
        eol_color = "hsl(0,40,70)"
        trade_color = "hsl(260,20,80)"
        emission_color = "hsl(30,40,70)"

        # Assign default flow color and update by category
        flow_color_dict = {"default": production_color}
        # Virgin production flows
        flow_color_dict.update({
            fn: production_color
            for fn, f in mfa.flows.items()
            if any(dim.name.startswith("virgin") for dim in f.dims)
        })
        # Recycling flows (mechanical or chemical)
        flow_color_dict.update({
            fn: recycling_color
            for fn, f in mfa.flows.items()
            if f.from_process.name in {"recl", "reclmech", "reclchem"} 
            or f.to_process.name in {"recl", "reclmech", "reclchem"}
        })
        # Use phase flows
        flow_color_dict.update({
            fn: use_color
            for fn, f in mfa.flows.items()
            if any(dim.name == "use" for dim in f.dims)
        })
        # End-of-life flows
        flow_color_dict.update({
            fn: eol_color
            for fn, f in mfa.flows.items()
            if f.from_process.name in {"eol","mismanaged","landfill","incineration"} 
            or f.to_process.name in {"eol","mismanaged","landfill","incineration"}
        })
        # Trade flows (imports/exports)
        flow_color_dict.update({
            fn: trade_color
            for fn, f in mfa.flows.items()
            if f.from_process.name in {"wastetrade","wasteimport","wasteexport"} 
            or f.to_process.name in {"wastetrade","wasteimport","wasteexport"}
        })
        # Emission flows
        flow_color_dict.update({
            fn: emission_color
            for fn, f in mfa.flows.items()
            if f.to_process.name == "atmosphere" or any(dim.name == "emission" for dim in f.dims)
        })

        # Update sankey configuration
        self.cfg.sankey["flow_color_dict"] = flow_color_dict
        self.cfg.sankey["node_color_dict"] = {"default": "gray", "use": "black"}

        # Prepare display names for plotting
        sdn = {k: f"<b>{v}</b>" for k, v in self._display_names.items()}
        plotter = fde.PlotlySankeyPlotter(mfa=mfa, display_names=sdn, **self.cfg.sankey)
        fig = plotter.plot()

        # Build legend
        legend_entries = [
            [production_color, "Virgin Production"],
            [recycling_color, "Recycling (total)"],
            [use_color, "Use Phase"],
            [eol_color, "End of Life"],
            [trade_color, "Trade Pool"],
            [emission_color, "Emissions"],
        ]
        for color, label in legend_entries:
            fig.add_trace(
                go.Scatter(
                    mode="markers",
                    x=[None], y=[None],
                    marker=dict(size=10, color=color, symbol="square"),
                    name=label
                )
            )

        # Finalize layout
        fig.update_layout(
            font_size=18,
            showlegend=True,
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="black"
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

        # Display and save
        self._show_and_save_plotly(fig, name="sankey_plastics")

    def export_eol_data_by_region_and_year(self, mfa: fd.MFASystem, output_path: str = "eol_by_region_year.csv"):
        # 假设 "eol" 是 flow 的 key
        if "use => eol" not in mfa.flows:
            raise KeyError("The MFA system does not contain 'eol' in flows.")
        
        eol_data = mfa.flows["eol => collected"].values 
        + mfa.flows["eol => mismanaged"].values 
        + mfa.flows["wasteimport => collected"].values 
        - mfa.flows["collected => wasteexport"].values  # xarray.DataArray
        # 转换为 DataFrame 并重命名列
        years = pd.read_csv("data/plastics/input/dimensions/time_in_years.csv", header=None)[0].tolist()
        elements = pd.read_csv("data/plastics/input/dimensions/elements.csv", header=None)[0].tolist()
        regions = pd.read_csv("data/plastics/input/dimensions/regions.csv", header=None)[0].tolist()
        materials = pd.read_csv("data/plastics/input/dimensions/materials.csv", header=None)[0].tolist()
        #goods = pd.read_csv("data/plastics/input/dimensions/goods_in_use.csv", header=None)[0].tolist()
        #print(mfa.flows["wasteexport => tradepool"].values)
        #print(mfa.flows["tradepool => wasteimport"].values)

        ds = xr.DataArray(
            eol_data,
            coords=[years, elements, regions, materials],
            dims=["year", "elements", "region", "material"]
        )

        # 转为 DataFrame，并处理合并和重命名
        df = ds.to_dataframe(name="EOL").reset_index()
        df_grouped = df.groupby(["year", "region"], as_index=False)["EOL"].sum()
        df_grouped.columns = [col.capitalize() if col != "EOL" else col for col in df_grouped.columns]  # 可选：统一列名风格

        # 输出为 CSV
        df_grouped.to_csv(output_path, index=False)
        print(f"EOL data exported to {output_path}")

    def export_use_data_by_region_and_year(self, mfa: fd.MFASystem, output_path: str = "use_by_region_year.csv"):
        # 假设 "eol" 是 flow 的 key
        if "fabrication => use" not in mfa.flows:
            raise KeyError("The MFA system does not contain 'use' in flows.")
        
        use_data = mfa.flows["fabrication => use"].values  # xarray.DataArray
        print(use_data.shape)
        # 转换为 DataFrame 并重命名列
        years = pd.read_csv("data/plastics/input/dimensions/time_in_years.csv", header=None)[0].tolist()
        elements = pd.read_csv("data/plastics/input/dimensions/elements.csv", header=None)[0].tolist()
        regions = pd.read_csv("data/plastics/input/dimensions/regions.csv", header=None)[0].tolist()
        materials = pd.read_csv("data/plastics/input/dimensions/materials.csv", header=None)[0].tolist()
        goods = pd.read_csv("data/plastics/input/dimensions/goods_in_use.csv", header=None)[0].tolist()

        ds = xr.DataArray(
            use_data,
            coords=[years, elements, regions, materials, goods],
            dims=["year", "elements", "region", "material", "goods"]
        )

        # 转为 DataFrame，并处理合并和重命名
        df = ds.to_dataframe(name="Use").reset_index()
        df_grouped = df.groupby(["year", "region"], as_index=False)["Use"].sum()
        df_grouped.columns = [col.capitalize() if col != "Use" else col for col in df_grouped.columns]  # 可选：统一列名风格

        # 输出为 CSV
        df_grouped.to_csv(output_path, index=False)
        print(f"Use data exported to {output_path}")