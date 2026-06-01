import flodym as fd
from typing import TYPE_CHECKING
import numpy as np
import logging

from remind_mfa.common.common_visualization import CommonVisualizer
from remind_mfa.cement.cement_config import CementVisualizationCfg
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem

if TYPE_CHECKING:
    from remind_mfa.cement.cement_model import CementModel


class CementVisualizer(CommonVisualizer):
    cfg: CementVisualizationCfg

    def visualize_custom(self, model: "CementModel"):
        mfa: StockDrivenCementMFASystem = model.future_mfa
        if self.cfg.prod_clinker.do_visualize:
            self.visualize_prod_clinker(mfa=mfa)
        if self.cfg.prod_cement.do_visualize:
            self.visualize_prod_cement(mfa=mfa, regional=False)
            self.visualize_prod_cement(mfa=mfa, regional=True)
        if self.cfg.prod_product.do_visualize:
            self.visualize_prod_product(mfa=mfa)
        if self.cfg.eol_stock.do_visualize:
            self.visualize_eol_stock(mfa=mfa)
        if self.cfg.carbonation.do_visualize:
            if not model.cfg.model_switches.carbonation:
                logging.warning(
                    "Carbonation visualization requested, but carbonation module not activated."
                )
            else:
                self.visualize_carbonation(mfa=mfa)

    def visualize_prod_clinker(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["prod_clinker => market_clinker"]
        self.visualize_flow(mfa=mfa, flow=production, name="Clinker production", regional=regional)

    def visualize_prod_cement(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["prod_cement => market_cement"]
        self.visualize_flow(mfa=mfa, flow=production, name="Cement production", regional=regional)

    def visualize_prod_product(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["prod_product => use"].sum_over("s")
        self.visualize_flow(mfa=mfa, flow=production, name="Product production", regional=regional)

    def visualize_consumption(self, mfa: fd.MFASystem):
        consumption = mfa.stocks["in_use"].inflow[{"k": "cement"}]
        self.visualize_flow_stacked(
            mfa=mfa,
            flow=consumption,
            name="Cement consumption",
            linecolor_dim="Stock Type",
            regional=True,
        )

    def visualize_eol_stock(self, mfa: fd.MFASystem):
        pass

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        # TODO: find way to name subplots_by_good back to subplot_by_stock_type
        # This is a workaround to streamline across materials.
        subplot_dim = "Stock Type" if subplots_by_good else None
        stock = mfa.stocks["in_use"].stock[{"k": "cement"}]
        super().visualize_use_stock(mfa, stock=stock, subplot_dim=subplot_dim)

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
        self.visualize_global_stock(
            stock, x_array, population, x_label, y_label, title, per_capita, over_gdp
        )

    def visualize_global_stock(
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
        plot_letters = ["t", "s"]
        stock = stock / population.sum_over("r") if per_capita else stock
        other_letters = tuple(letter for letter in stock.dims.letters if letter not in plot_letters)
        stock = stock.sum_over(other_letters)
        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Stock Type",
            display_names=self.display_names.dct,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f"{title} (global by stock type)",
            area=True,
        )

        self.plot_and_save_figure(ap_stock, "use_stocks_global_by_type.png")

    def visualize_carbonation(self, mfa: fd.MFASystem):
        annual_uptake = mfa.stocks["carbonated_co2"].inflow
        cumulative_uptake = mfa.stocks["carbonated_co2"].stock
        linecolor_dim = "Carbonation Location"
        self.visualize_flow_stacked(
            mfa=mfa,
            flow=annual_uptake,
            name="Annual CO2 uptake from carbonation",
            linecolor_dim=linecolor_dim,
            regional=False,
        )
