from plotly import colors as plc
import numpy as np
import flodym as fd
from typing import TYPE_CHECKING

from remind_mfa.common.common_export import CommonDataExporter
from remind_mfa.common.common_cfg import CementVisualizationCfg

if TYPE_CHECKING:
    from remind_mfa.cement.cement_model import CementModel


class CementDataExporter(CommonDataExporter):
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

    def visualize_results(self, model: "CementModel"):
        if self.cfg.clinker_production["do_visualize"]:
            self.visualize_clinker_production(mfa=model.future_mfa)
        if self.cfg.cement_production["do_visualize"]:
            self.visualize_cement_production(mfa=model.future_mfa, regional=False)
            self.visualize_cement_production(mfa=model.future_mfa, regional=True)
        if self.cfg.concrete_production["do_visualize"]:
            self.visualize_concrete_production(mfa=model.future_mfa)
        if self.cfg.use_stock["do_visualize"]:
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_stock_type=False)
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_stock_type=True)
        if self.cfg.eol_stock["do_visualize"]:
            self.visualize_eol_stock(mfa=model.future_mfa)
        if self.cfg.sankey["do_visualize"]:
            self.visualize_sankey(mfa=model.future_mfa)
        if self.cfg.extrapolation["do_visualize"]:
            self.visualize_extrapolation(model=model)
        if self.cfg.sd["do_visualize"]:
            self.visualize_sd(model=model, material="concrete")
            self.visualize_sd(model=model, material="cement")
            self.visualize_sd(model=model, material="concrete", regional=False)
            self.visualize_sd(model=model, material="cement", regional=False)
            self.visualize_sd(model=model, material="concrete", regional=True, per_capita=False)
            self.visualize_sd(model=model, material="concrete", regional=False, per_capita=False)
            # self.visualize_top_vs_bottom(model=model)
        self.stop_and_show()

    def visualize_production(
        self, mfa: fd.MFASystem, production: fd.Flow, name: str, regional: bool = False
    ):

        x_array = None
        # intra_line_dim = "Time"
        # line_label = f"{name} Production"
        x_label = "Year"
        y_label = "Production [t]"
        linecolor_dim = None

        if regional:
            subplot_dim = "Region"
            title = f"Regional {name} Production"
            regional_tag = "_regional"
        else:
            subplot_dim = None
            regional_tag = ""
            title = f"Global {name} Production"
            production = production.sum_over("r")

        fig, ap_production = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=production,
            subplot_dim=subplot_dim,
            x_array=x_array,
            linecolor_dim=linecolor_dim,
            x_label=x_label,
            y_label=y_label,
            title=title,
            line_label="Production",
        )

        self.plot_and_save_figure(
            ap_production, f"{name}_production{regional_tag}.png", do_plot=False
        )

    def visualize_clinker_production(self, mfa: fd.MFASystem):
        production = mfa.flows["clinker_production => cement_grinding"]
        self.visualize_production(production, "Clinker")

    def visualize_cement_production(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["cement_grinding => concrete_production"]
        self.visualize_production(mfa=mfa, production=production, name="Cement", regional=regional)

    def visualize_concrete_production(self, mfa: fd.MFASystem):
        production = mfa.flows["concrete_production => use"].sum_over("s")
        self.visualize_production(production, "Concrete")

    def visualize_eol_stock(self, mfa: fd.MFASystem):
        over_gdp = self.cfg.eol_stock["over_gdp"]
        per_capita = self.cfg.eol_stock["per_capita"]
        stock = mfa.stocks["eol"].stock

        self.visualize_stock(mfa, stock, over_gdp, per_capita, "EOL")

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_stock_type=False):
        subplot_dim = "Stock Type" if subplots_by_stock_type else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["in_use"].stock, subplot_dim=subplot_dim)

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

    def visualize_extrapolation(self, model: "CementModel"):
        mfa = model.future_mfa
        per_capita = True  # TODO see where this shold go
        subplot_dim = "Region"
        stock = mfa.stocks["in_use"].stock
        population = mfa.parameters["population"]
        x_array = None

        pc_str = "pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Stock{pc_str} [t]"
        title = f"Stock Extrapolation: Historic and Projected vs Pure Prediction"
        if self.cfg.use_stock["over_gdp"]:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"]
            if not per_capita:
                x_array = x_array * population

        if subplot_dim is None:
            dimlist = ["t"]
        else:
            subplot_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == subplot_dim
            )
            dimlist = ["t", subplot_dimletter]

        other_dimletters = tuple(letter for letter in stock.dims.letters if letter not in dimlist)
        stock = stock.sum_over(other_dimletters)

        if per_capita:
            stock = stock / population

        fig, ap_final_stock = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=stock,
            subplot_dim=subplot_dim,
            x_array=x_array,
            x_label=x_label,
            y_label=y_label,
            title=title,
            line_label="Historic + Modelled Future",
        )

        # extrapolation
        ap_pure_prediction = self.plotter_class(
            array=model.stock_handler.pure_prediction,
            intra_line_dim="Time",
            subplot_dim=subplot_dim,
            x_array=x_array,
            title=title,
            fig=fig,
            line_type="dot",
            line_label="Pure Extrapolation",
        )
        fig = ap_pure_prediction.plot()

        self.plot_and_save_figure(
            ap_pure_prediction,
            f"stocks_extrapolation.png",
            do_plot=False,
        )

    def calculate_sd_stock(self, model: "CementModel", material="concrete") -> fd.FlodymArray:
        prm = model.parameters

        bf = prm["buildings_floorspace"]
        bf = fd.FlodymArray(dims=model.dims[("t", "r", "b", "f")])
        big_bf = prm["buildings_floorspace"] * prm["building_split"]
        bf[{"f": "Com"}][...] = big_bf[{"s": "Com", "f": "Com"}]
        bf[{"f": "RS"}][...] = big_bf[{"s": "Res", "f": "RS"}]
        bf[{"f": "RM"}][...] = big_bf[{"s": "Res", "f": "RM"}]
        
        stock =  bf * prm["concrete_building_mi"]
        if material == "cement":
            stock = stock / prm["cement_ratio"]

        return stock
    
    def visualize_sd(self, model: "CementModel", material: str = "concrete", regional: bool = True, per_capita: bool = True):

        mfa = model.future_mfa
        subplot_dim = "Region"
        stock = mfa.stocks["in_use"].stock
        stock_sd = self.calculate_sd_stock(model)
        population = mfa.parameters["population"]

        if not regional:
            subplot_dim = None
            stock = stock.sum_over("r")
            stock_sd = stock_sd.sum_over("r")
            population = population.sum_over("r")

        x_array = None

        pc_str = "pC" if per_capita else ""
        x_label = "Year"
        y_label = f"{material.capitalize()} Stock{pc_str} [t]"
        title = f"{material.capitalize()} Stock Comparison: Buttom-up SD vs Top-down Extrapolation"
        if self.cfg.sd["over_gdp"]:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"]
            if not per_capita:
                x_array = x_array * population

        if subplot_dim is None:
            dimlist = ["t"]
        else:
            subplot_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == subplot_dim
            )
            dimlist = ["t", subplot_dimletter]

        other_dimletters = tuple(letter for letter in stock.dims.letters if letter not in dimlist)
        stock = stock.sum_over(other_dimletters)

        # service demand stock
        other_dimletters_sd = tuple(letter for letter in stock_sd.dims.letters if letter not in dimlist)
        stock_sd = stock_sd.sum_over(other_dimletters_sd)

        if material == "cement":
            stock = stock * mfa.parameters["cement_ratio"]
            stock_sd = stock_sd * mfa.parameters["cement_ratio"]
        
        if per_capita:
            stock = stock / population
            stock_sd = stock_sd / population

        fig, ap_final_stock = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=stock,
            subplot_dim=subplot_dim,
            x_array=x_array,
            x_label=x_label,
            y_label=y_label,
            title=title,
            line_label="Historic + Modelled Future",
        )

        # SD
        ap_pure_prediction = self.plotter_class(
            array=stock_sd,
            intra_line_dim="Time",
            subplot_dim=subplot_dim,
            x_array=x_array,
            title=title,
            fig=fig,
            line_type="dot",
            line_label="SD Stock",
        )
        fig = ap_pure_prediction.plot()

        self.plot_and_save_figure(
            ap_pure_prediction,
            f"stocks_extrapolation.png",
            do_plot=False,
        )

    def visualize_top_vs_bottom(self, model: "CementModel", material="concrete"):
        mfa = model.future_mfa

        stock_sd = self.calculate_sd_stock(model, material=material).sum_over(("b", "f"))
        stock = mfa.stocks["in_use"].stock.sum_over("s")
        gdppc = mfa.parameters["gdppc"]

        cut_time = fd.Dimension(name="CutTime", letter="p", items=np.arange(1999, 2024))
        cut_stock_sd = stock_sd[{"t": cut_time}]
        cut_stock = stock[{"t": cut_time}]
        cut_gdppc = gdppc[{"t": cut_time}]

        ratio = cut_stock_sd / cut_stock

        # ratio over gdppc
        ap_ratio = self.plotter_class(
            array=ratio,
            linecolor_dim="Region",
            intra_line_dim="CutTime",
            x_array=cut_gdppc,
            xlabel="GDP/PPP [2005 USD]",
            ylabel="Ratio",
            title=f"Ratio of Bottom-Up (SD) Stock to Top-down (DSM) Stock Estimate (1990-2023)",
        )

        # fig = ap_ratio.plot()
        # fig.update_xaxes(type="log", range=[3, 5])

        self.plot_and_save_figure(ap_ratio, "ratio.png")

        # ratio over time
        ap_ratio = self.plotter_class(
            array=ratio,
            linecolor_dim="Region",
            intra_line_dim="CutTime",
            xlabel="Time",
            ylabel="Ratio",
            title=f"Ratio of Bottom-Up (SD) Stock to Top-down (DSM) Stock Estimate (1990-2023)",    
        )

        self.plot_and_save_figure(ap_ratio, "ratio_time.png")

        # top vs bottom
        ap_tb = self.plotter_class(
            array=cut_stock_sd,
            x_array=cut_stock,
            linecolor_dim="Region",
            intra_line_dim="CutTime",
            xlabel="Top-down (DSM) Stock Estimate (t)",
            ylabel="Bottom-up (SD) Stock Estimate (t)",
            title=f"Bottom-Up (SD) Stock vs Top-down (DSM) Stock Estimate (1990-2023)",    
        )

        fig = ap_tb.plot()
        fig.update_xaxes(type="log")
        fig.update_yaxes(type="log")

        self.plot_and_save_figure(ap_tb, "tb.png")

        cut_time = fd.Dimension(name="CutTime", letter="p", items=np.arange(2024, 2101))
        cut_stock_sd = stock_sd[{"t": cut_time}]
        cut_stock = stock[{"t": cut_time}]
        cut_gdppc = gdppc[{"t": cut_time}]

        ratio = cut_stock_sd / cut_stock

        # ratio 2024-2100 over gdppc
        ap_ratio = self.plotter_class(
            array=ratio,
            linecolor_dim="Region",
            intra_line_dim="CutTime",
            x_array=cut_gdppc,
            xlabel="GDP/PPP [2005 USD]",
            ylabel="Ratio",
            title=f"Ratio of Bottom-Up (SD) Stock to Top-down (DSM) Stock Estimate (2024-2100)",
        )

        self.plot_and_save_figure(ap_ratio, "future_ratio.png")

