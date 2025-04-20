import flodym as fd
from typing import TYPE_CHECKING

from simson.common.custom_export import CustomDataExporter

if TYPE_CHECKING:
    from simson.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CustomDataExporter):

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        "sysenv": "System environment",
        "virginfoss": "Virgin production (fossil)",
        "virginbio": "Virgin production (biomass)",
        "virgindaccu": "Virgin production (daccu)",
        "virginccu": "Virgin production (ccu)",
        "virgin": "Virgin production (total)",
        "fabrication": "Fabrication",
        "recl": "Recycling (total)",
        "reclmech": "Mechanical recycling",
        "reclchem": "Chemical recycling",
        "reclsolv": "Solvent-based recycling",
        "use": "Use Phase",
        "eol": "End of Life",
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
