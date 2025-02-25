import flodym as fd
from typing import TYPE_CHECKING

from simson.common.custom_export import CustomDataExporter
from simson.common.common_cfg import CementVisualizationCfg

if TYPE_CHECKING:
    from simson.cement.cement_model import CementModel

class CementDataExporter(CustomDataExporter):
    # They have to be defined here but are eventually overwritten by yml definitions
    cfg: CementVisualizationCfg

    _display_names: dict = {
        "sysenv": "System environment",
        "raw_meal_preparation": "Raw meal preparation",
        "clinker_production": "Clinker production",
        "cement_grinding": "Cement grinding",
        "concrete_production": "Concrete production",
        "use": "Use phase",
        "eol": "End of life",
    }

    def visualize_results(self, model: 'CementModel'):
        if self.cfg.clinker_production["do_visualize"]:
            self.visualize_clinker_production(mfa=model.future_mfa)
        if self.cfg.cement_production["do_visualize"]:
            self.visualize_cement_production(mfa=model.future_mfa)
        if self.cfg.concrete_production["do_visualize"]:
            self.visualize_concrete_production(mfa=model.future_mfa)
        if self.cfg.use_stock["do_visualize"]:
            self.visualize_use_stock(mfa=model.future_mfa)
        if self.cfg.eol_stock["do_visualize"]:
            self.visualize_eol_stock(mfa=model.future_mfa)
        if self.cfg.sankey["do_visualize"]:
            self.visualize_sankey(mfa=model.future_mfa)
        self.stop_and_show()

    def visualize_production(self, production: fd.Flow, name: str):

        if "r" in production.dims.letters:
            # regional production
            ap_production = self.plotter_class(
                array=production,
                intra_line_dim="Time",
                subplot_dim="Region",
                line_label=f"{name} Production",
                display_names=self._display_names,
                xlabel="Year",
                ylabel="Production [t]",
                title=f"Regional {name} Production",
            )

            self.plot_and_save_figure(ap_production, f"{name}_production_regional.png")

            # global production
            global_production = production.sum_over("r")

        else:
            global_production = production

        ap_global_production = self.plotter_class(
            array=global_production,
            intra_line_dim="Time",
            line_label=f"{name} Production",
            display_names=self._display_names,
            xlabel="Year",
            ylabel="Production [t]",
            title=f"Global {name} Production",
        )

        self.plot_and_save_figure(ap_global_production, f"{name}_production_global.png")


    def visualize_clinker_production(self, mfa: fd.MFASystem):
        production = mfa.flows["clinker_production => cement_grinding"]
        self.visualize_production(production, "Clinker")
    
    def visualize_cement_production(self, mfa: fd.MFASystem):
        production = mfa.flows["cement_grinding => concrete_production"]
        self.visualize_production(production, "Cement")

    def visualize_concrete_production(self, mfa: fd.MFASystem):
        production = mfa.flows["concrete_production => use"].sum_over("s")
        self.visualize_production(production, "Concrete")

    def visualize_use_stock(self, mfa: fd.MFASystem):
        over_gdp = self.cfg.use_stock["over_gdp"]
        per_capita = self.cfg.use_stock["per_capita"]
        stock = mfa.stocks["in_use"].stock

        self.visualize_stock(mfa, stock, over_gdp, per_capita, "In use")

    def visualize_eol_stock(self, mfa: fd.MFASystem):
        over_gdp = self.cfg.eol_stock["over_gdp"]
        per_capita = self.cfg.eol_stock["per_capita"]
        stock = mfa.stocks["eol"].stock

        self.visualize_stock(mfa, stock, over_gdp, per_capita, "EOL")

    def visualize_stock(self, mfa: fd.MFASystem, stock, over_gdp, per_capita, name):
        population = mfa.parameters["population"]
        x_array = None

        pc_str = " pC" if per_capita else ""
        x_label = "Year"
        y_label = f"{name} Stock{pc_str}[t]"
        title = f"{name} stocks{pc_str}"
        if over_gdp:
            title = title + f" over GDP{pc_str}"

        if over_gdp:
            x_array = mfa.parameters["gdppc"]
            x_label = f"GDP/PPP{pc_str}[2005 USD]"

        # self.visualize_regional_stock(
        #     stock, x_array, population, x_label, y_label, title, per_capita, over_gdp
        # )
        self.visiualize_global_stock(
            stock, x_array, population, x_label, y_label, title, per_capita, over_gdp
        )
    
    def visiualize_global_stock(
        self, stock, x_array, population, x_label, y_label, title, per_capita, over_gdp
    ):
        if over_gdp:
            x_array = x_array * population
            x_array = x_array.sum_over("r")
            if per_capita:
                # get global GDP per capita
                x_array = x_array / population.sum_over("r")

        self.visualize_global_stock_by_type(
            stock, x_array, population, x_label, y_label, title, per_capita
        )
        # self.visualize_global_stock_by_region(stock, x_array, x_label, y_label, title, per_capita)
    
    def visualize_global_stock_by_type(
        self, stock, x_array, population, x_label, y_label, title, per_capita
    ):
        if "r" in stock.dims.letters:
            stock = stock.sum_over("r")
        stock = stock / population.sum_over("r") if per_capita else stock

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Stock Type",
            display_names=self._display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f"{title} (global by stock type)",
            area=True,
        )

        self.plot_and_save_figure(ap_stock, "use_stocks_global_by_type.png")

    def visualize_extrapolation(self, mfa: fd.MFASystem, future_demand):
        stock = mfa.stocks["historic_in_use"].stock.sum_over("s")

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim="Historic Time",
            subplot_dim="Region",
            line_label=f"Stock",
            display_names=self._display_names,
            xlabel="Year",
            ylabel="Stock [t]",
            title=f"Regional Stock",
        )

        self.plot_and_save_figure(ap_stock, f"Stock_regional.png")
