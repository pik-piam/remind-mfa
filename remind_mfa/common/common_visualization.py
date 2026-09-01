import os
import numpy as np
from matplotlib import pyplot as plt
import plotly.graph_objects as go
import plotly.colors as plc
import plotly.io as pio
from typing import Optional, TYPE_CHECKING
from pydantic import model_validator, PrivateAttr
import flodym as fd
import flodym.export as fde

from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.common_config import VisualizationCfg
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.helpers import RegressOverModes
from remind_mfa.common.data_transformations import broadcast_trailing_dimensions
from remind_mfa.common.data_extrapolations import TwoPredictorExtrapolation
from remind_mfa.common.stock_extrapolation import StockExtrapolation

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel


class CommonVisualizer(RemindMFABaseModel):
    cfg: VisualizationCfg
    display_names: CommonDisplayNames

    _model: Optional["CommonModel"] = PrivateAttr(default=None)

    @model_validator(mode="after")
    def set_plotly_renderer(self):
        if self.cfg.plotting_engine == "plotly":
            pio.renderers.default = self.cfg.plotly_renderer
        return self

    def visualize(self, model: "CommonModel"):
        if not self.cfg.do_visualize:
            return
        self._model = model
        self.visualize_common(model=model)
        self.visualize_custom(model=model)
        self.stop_and_show()

    def visualize_common(self, model: "CommonModel"):
        if self.cfg.gdp.do_visualize:
            self.visualize_gdppc(model.future_mfa, change=False, per_capita=self.cfg.gdp.per_capita)
        if self.cfg.use_stock.do_visualize:
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_good=True)
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_good=False)
        if self.cfg.trade.do_visualize:
            self.visualize_trade(model.future_mfa)
        if self.cfg.sankey.do_visualize:
            self.visualize_sankey(model.future_mfa)
        if self.cfg.consumption.do_visualize:
            self.visualize_consumption(mfa=model.future_mfa)
        if self.cfg.sector_splits.do_visualize:
            self.visualize_sector_splits(model, regional=True)
            self.visualize_sector_splits(model, regional=False)
        if self.cfg.extrapolation.do_visualize:
            self.visualize_extrapolation(model=model)
            self.visualize_extrapolation_functions(model=model, stock_handler=model.stock_handler)

    def visualize_custom(self, model: "CommonModel"):
        """To be overwritten by model subclasses"""
        pass

    def _show_and_save_plotly(self, fig: go.Figure, name):
        if self.cfg.do_save_figs:
            fig.write_image(self.figure_path(f"{name}.png"))
        if self.cfg.do_show_figs:
            fig.show()

    def visualize_sankey(self, mfa: fd.MFASystem):
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=self.display_names.dct, **self.cfg.sankey.plotter_args
        )
        fig = plotter.plot()

        fig.update_layout(
            # title_text=f"Steel Flows ({', '.join([str(v) for v in self.cfg.sankey.plotter_args['slice_dict'].values()])})",
            font_size=20,
        )

        self._show_and_save_plotly(fig, name="sankey")

    def figure_path(self, filename: str) -> str:
        figures_dir = os.path.join(self._model.data_writer.run_path(self._model), "figures")
        os.makedirs(figures_dir, exist_ok=True)
        return os.path.join(figures_dir, filename)

    def plot_and_save_figure(self, plotter: fde.ArrayPlotter, filename: str, do_plot: bool = True):
        if do_plot:
            plotter.plot()
        if self.cfg.do_show_figs:
            plotter.show()
        if self.cfg.do_save_figs:
            plotter.save(self.figure_path(filename), width=2200, height=1300, scale=3)

    def stop_and_show(self):
        if self.cfg.plotting_engine == "pyplot" and self.cfg.do_show_figs:
            plt.show()

    @property
    def plotter_class(self):
        if self.cfg.plotting_engine == "plotly":
            return fde.PlotlyArrayPlotter
        elif self.cfg.plotting_engine == "pyplot":
            return fde.PyplotArrayPlotter
        else:
            raise ValueError(f"Unknown plotting engine: {self.cfg.plotting_engine}")

    def visualize_use_stock(
        self, mfa: fd.MFASystem, stock: fd.FlodymArray, subplot_dim: str = None
    ):
        """Visualize the use stock. If subplot_dim is not None, a separate plot for each item in the given dimension is created. Otherwise, one accumulated plot is generated."""
        per_capita = self.cfg.use_stock.per_capita

        population = mfa.parameters["population"]
        x_array = None
        linecolor_dim = "Region"

        pc_str = " pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Stock{pc_str} [t]"
        title = f"Stocks{pc_str}"
        if self.cfg.use_stock.over_gdp:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"]
            if not per_capita:
                # get global GDP per capita
                x_array = x_array * population

        dimlist = ["t", "r"]
        if subplot_dim is not None:
            subplot_dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == subplot_dim
            )
            dimlist.append(subplot_dimletter)
        # sum over all dimensions except time, subplot_dim and linecolor_dim
        other_dimletters = tuple(letter for letter in stock.dims.letters if letter not in dimlist)
        for dimletter in other_dimletters:
            stock = stock.sum_over(dimletter)

        # Remove stocks below a threshold to avoid plots being dominated by very small regions with bad data.
        # pop_threshold = 1e6
        # current_pop = population[{"t": mfa.dims["h"].items[-1]}]
        # current_pop = current_pop.cast_values_to(stock.dims)
        # stock.values[current_pop < pop_threshold] = 0

        if per_capita:
            stock = stock / population

        fig, ap_scatter_stock = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=stock,
            subplot_dim=subplot_dim,
            x_array=x_array,
            linecolor_dim=linecolor_dim,
            x_label=x_label,
            y_label=y_label,
            title=title,
        )

        # Adjust x-axis
        if self.cfg.use_stock.over_gdp:
            if self.cfg.plotting_engine == "plotly":
                fig.update_xaxes(title=x_label, type="log")
            elif self.cfg.plotting_engine == "pyplot":
                for ax in fig.get_axes():
                    ax.set_xscale("log")
                    ax.set_xlabel(x_label)

        self.plot_and_save_figure(
            ap_scatter_stock,
            f"stocks_global_by_region{'_and_' + subplot_dim if subplot_dim is not None else ''}{'_per_capita' if per_capita else ''}.png",
            do_plot=False,
        )

    def plot_history_and_future(
        self,
        mfa: fd.MFASystem,
        data_to_plot: fd.FlodymArray,
        subplot_dim: Optional[str] = None,
        x_array: Optional[fd.FlodymArray] = None,
        linecolor_dim: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        title: Optional[str] = None,
        future_stock: bool = True,
        **kwargs,
    ):

        colors = plc.qualitative.Dark24 * 20
        if linecolor_dim:
            dimletter = next(
                dimlist.letter for dimlist in mfa.dims.dim_list if dimlist.name == linecolor_dim
            )
            n_linecolor_dim = data_to_plot.dims[dimletter].len
        else:
            n_linecolor_dim = 1

        colors = (
            colors[:n_linecolor_dim]  # future (dotted) color
            + colors[:n_linecolor_dim]  # historic (solid) color
            + ["black" for _ in range(n_linecolor_dim)]  # dot color
        )

        # data preparation
        hist = data_to_plot[{"t": mfa.dims["h"]}]
        last_year_dim = fd.Dimension(
            name="Last Historic Year", letter="l", items=[mfa.dims["h"].items[-1]]
        )
        scatter = hist[{"h": last_year_dim}]
        if x_array is None:
            hist_x_array = None
            scatter_x_array = None
        else:
            hist_x_array = x_array[{"t": mfa.dims["h"]}]
            scatter_x_array = hist_x_array[{"h": last_year_dim}]

        # Future stock (dotted)
        ap = self.plotter_class(
            array=data_to_plot,
            intra_line_dim="Time",
            linecolor_dim=linecolor_dim,
            subplot_dim=subplot_dim,
            x_array=x_array,
            title=title,
            color_map=colors,
            line_type="dot",
            suppress_legend=True,
            **kwargs,
        )
        fig = ap.plot()

        # Historic stock (solid)
        ap = self.plotter_class(
            array=hist,
            intra_line_dim="Historic Time",
            linecolor_dim=linecolor_dim,
            subplot_dim=subplot_dim,
            x_array=hist_x_array,
            color_map=colors,
            fig=fig,
            **kwargs,
        )
        fig = ap.plot()

        if not future_stock:
            # Hack to remove future line from the plot, but keep the axis range
            colors = ["rgba(0,0,0,0)"] * len(colors)

        # Last historic year (dot)
        ap = self.plotter_class(
            array=scatter,
            intra_line_dim="Last Historic Year",
            linecolor_dim=linecolor_dim,
            subplot_dim=subplot_dim,
            x_array=scatter_x_array,
            xlabel=x_label,
            ylabel=y_label,
            fig=fig,
            chart_type="scatter",
            color_map=colors,
            suppress_legend=True,
            **kwargs,
        )
        fig = ap.plot()

        return fig, ap

    def _get_regional_vs_global_params(self, regional: bool):
        if regional:
            subplot_dim = {"subplot_dim": "Region"}
            summing_func = lambda l: l
            name_str = "regional"
        else:
            subplot_dim = {}
            summing_func = lambda l: l.sum_over("r")
            name_str = "global"
        return subplot_dim, summing_func, name_str

    def visualize_extrapolation_functions(
        self, model: "CommonModel", stock_handler: StockExtrapolation
    ):
        regional = "r" in stock_handler.indep_fit_dim_letters
        subplot_dim, _, regional_str = self._get_regional_vs_global_params(regional)
        if goods_dim_letter := set(stock_handler.indep_fit_dim_letters) - set(("r")):
            assert (
                len(goods_dim_letter) == 1
            ), "Only one non-region dimension supported in extrapolation visualization"
            linecolor_dim = model.dims[goods_dim_letter.pop()].name
        else:
            linecolor_dim = None
        extrapolation = stock_handler.extrapolation
        fit_prms = extrapolation.fit_prms

        log_gdppc = np.log10(stock_handler.gdppc.values)
        gdppc = np.logspace(np.min(log_gdppc), np.max(log_gdppc), model.dims["t"].len)
        gdppc = broadcast_trailing_dimensions(gdppc, stock_handler.dims_out)
        predictor = stock_handler.get_predictor(gdppc)

        def to_flodym(np_array, name=None):
            fda = fd.FlodymArray(dims=stock_handler.dims_out, values=np_array, name=name)
            if not regional:
                first_region = model.dims["r"].items[0]
                fda = fda[first_region]
            return fda

        prms = [fit_prms[np.newaxis, ..., i] for i in range(extrapolation.n_prms)]

        if isinstance(extrapolation, TwoPredictorExtrapolation):
            # see loop below for purposes of the list entries
            factors = [
                ["f1", "Saturation level", "x2", "Time"],
                ["f2", "Growth over GDP", "x1", "log10(GDPpC)"],
                ["f3", "Growth over Time", "x2", "Time"],
            ]
        else:
            factors = [
                [None, "Growth", None, stock_handler.cfg.regress_over],
            ]

        for factor_name, title, predictor_key, predictor_name in factors:
            kwargs = {} if factor_name is None else {"factor": factor_name}
            values = extrapolation.func(predictor, prms, **kwargs)
            array = to_flodym(values, name=factor_name)
            if predictor_key:
                x_array = predictor[predictor_key]
            else:
                x_array = predictor
            x_array = to_flodym(x_array, predictor_name)

            ap = self.plotter_class(
                array=array,
                intra_line_dim="Time",
                title=title,
                x_array=x_array,
                linecolor_dim=linecolor_dim,
                **subplot_dim,
            )
            fig = ap.plot()

            self.plot_and_save_figure(
                ap,
                f"regression_function_{factor_name}_{regional_str}",
                do_plot=False,
            )

    def visualize_trade(
        self, mfa: fd.MFASystem, linecolor_dims: Optional[dict[str, Optional[str]]] = None
    ):

        for name, trade in mfa.trade_set.markets.items():
            imports = trade.imports
            exports = trade.exports

            linecolor_dim = linecolor_dims[name] if linecolor_dims is not None else None
            linecolor_dim_letter = (
                imports.dims[linecolor_dim].letter if linecolor_dim is not None else None
            )
            dimlist = [
                "t",
                "r",
            ] + ([linecolor_dim_letter] if linecolor_dim_letter is not None else [])
            imports = imports.sum_to(dimlist)
            exports = exports.sum_to(dimlist)

            if linecolor_dim is not None:
                n_colors = mfa.dims[linecolor_dim].len
                imports = imports.cumsum(dim_letter=linecolor_dim_letter)
                exports = exports.cumsum(dim_letter=linecolor_dim_letter)
                chart_type = "area"
            else:
                n_colors = 1
                chart_type = "line"
            colors = plc.qualitative.Dark24[:n_colors] * 2
            ap_imports = self.plotter_class(
                array=imports,
                intra_line_dim="Time",
                subplot_dim="Region",
                linecolor_dim=linecolor_dim,
                display_names=self.display_names.dct,
                color_map=colors,
                chart_type=chart_type,
            )
            fig = ap_imports.plot()
            ap_exports = self.plotter_class(
                array=-exports,
                intra_line_dim="Time",
                subplot_dim="Region",
                linecolor_dim=linecolor_dim,
                display_names=self.display_names.dct,
                title=f"{name} Trade",
                ylabel="Trade (Exports negative)",
                suppress_legend=True,
                fig=fig,
                color_map=colors,
                chart_type=chart_type,
            )
            fig = ap_exports.plot()
            self.plot_and_save_figure(ap_exports, f"trade_{name}.png", do_plot=False)

    def visualize_sector_splits(self, model: "CommonModel", regional: bool = True):

        end_use_good_letter = model.end_use_good_letter
        subplot_dim, summing_func, name_str = self._get_regional_vs_global_params(regional)

        consumption = summing_func(
            model.future_mfa.stocks["in_use"].inflow.sum_to(("t", "r", end_use_good_letter))
        )
        sector_splits = consumption.get_shares_over(end_use_good_letter)
        sector_splits = sector_splits.cumsum(dim_letter=end_use_good_letter)

        ap_sector_splits = self.plotter_class(
            array=sector_splits,
            intra_line_dim="Time",
            **subplot_dim,
            linecolor_dim=model.dims[end_use_good_letter].name,
            xlabel="Year",
            ylabel="Sector Splits [%]",
            display_names=self.display_names.dct,
            title=f"Product demand sector splits ({name_str})",
            chart_type="area",
        )

        self.plot_and_save_figure(ap_sector_splits, f"sector_splits_{name_str}.png")

    def visualize_fdarr(
        self,
        mfa: fd.MFASystem,
        flow: fd.FlodymArray,
        name: str,
        regional: bool = True,
        per_capita: bool = False,
        linecolor_dim: Optional[str] = None,
        y_unit: str = "t",
        scale: float = 1.0,
    ):
        population = mfa.parameters["population"]
        if per_capita:
            flow = flow / population
        pc_str = "pC" if per_capita else ""
        subplot_dim, summing_func, regional_tag = self._get_regional_vs_global_params(regional)

        linecolor_dim_letter = mfa.dims[linecolor_dim].letter if linecolor_dim is not None else None
        dimlist = [
            "t",
            "r",
        ] + ([linecolor_dim_letter] if linecolor_dim_letter is not None else [])
        flow = summing_func(flow.sum_to(dimlist))
        if scale != 1.0:
            flow = flow * scale

        fig, ap_flow = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=flow,
            **subplot_dim,
            x_array=None,
            linecolor_dim=linecolor_dim,
            x_label="Year",
            y_label=f"{name} [{y_unit}]",
            title=f"{name} {pc_str} {regional_tag}",
            line_label=name if linecolor_dim is None else None,
        )

        self.plot_and_save_figure(ap_flow, f"{name}_{pc_str}_{regional_tag}.png", do_plot=False)

    def visualize_fdarr_stacked(
        self,
        mfa: fd.MFASystem,
        flow: fd.FlodymArray,
        name: str,
        linecolor_dim: str,
        regional: bool = True,
        per_capita: bool = False,
    ):

        population = mfa.parameters["population"]
        if per_capita:
            flow = flow / population
        pc_str = "pC" if per_capita else ""
        subplot_dim, summing_func, regional_tag = self._get_regional_vs_global_params(regional)

        linecolor_dim_letter = mfa.dims[linecolor_dim].letter
        dimlist = [
            "t",
            "r",
        ] + [linecolor_dim_letter]
        flow = summing_func(flow.sum_to(dimlist))
        flow_stacked = flow.cumsum(dim_letter=linecolor_dim_letter)

        ap = self.plotter_class(
            array=flow_stacked,
            intra_line_dim="Time",
            **subplot_dim,
            linecolor_dim=linecolor_dim,
            chart_type="area",
            display_names=self.display_names.dct,
            xlabel="Year",
            ylabel=f"{name} [t]",
            title=f"{name} {pc_str} {regional_tag}",
        )
        fig = ap.plot()
        self.plot_and_save_figure(ap, f"{name}_stacked_{pc_str}_{regional_tag}.png", do_plot=False)

    def visualize_extrapolation(
        self,
        model: "CommonModel",
        subplot_dim: str = "Region",
        linecolor_dim: Optional[str] = None,
        show_extrapolation: bool = True,
        show_future: bool = True,
    ):
        mfa = model.future_mfa
        per_capita = self.cfg.use_stock.per_capita
        population = model.parameters["population"]
        stock = model.stock_handler.stocks * model.sector_specific_sat_level
        extrapolation = model.stock_handler.fitted_regression * model.sector_specific_sat_level
        x_array = None

        pc_str = "pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Stock{pc_str} [t]"
        title = f"Stock Extrapolation: Historic and Projected vs Pure Prediction"
        if self.cfg.use_stock.over_gdp:
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = model.parameters["gdppc"]
            if not per_capita:
                x_array = x_array * population

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
        stock = stock.sum_to(dimlist)
        extrapolation = extrapolation.sum_to(dimlist)

        if per_capita:
            stock_to_plot = stock / population
            extrapolation_to_plot = extrapolation
        else:
            stock_to_plot = stock
            extrapolation_to_plot = extrapolation * population

        fig, ap = self.plot_history_and_future(
            mfa=mfa,
            data_to_plot=stock_to_plot,
            subplot_dim=subplot_dim,
            linecolor_dim=linecolor_dim,
            x_array=x_array,
            x_label=x_label,
            y_label=y_label,
            title=title,
            line_label="Historic + Modelled Future" if linecolor_dim is None else None,
            future_stock=show_future,
        )

        if show_extrapolation:
            ap = self.plotter_class(
                array=extrapolation_to_plot,
                intra_line_dim="Time",
                subplot_dim=subplot_dim,
                linecolor_dim=linecolor_dim,
                x_array=x_array,
                title=title,
                fig=fig,
                line_type="dot",
                line_label="Pure Extrapolation" if linecolor_dim is None else None,
                color_map=(
                    ap.color_map * 2
                    if linecolor_dim is not None
                    else ["red"] * len(ap.color_map) * 2
                ),
                suppress_legend=True if linecolor_dim is not None else False,
            )
            fig = ap.plot()

        if self.cfg.plotting_engine == "plotly" and self.cfg.use_stock.over_gdp:
            fig.update_xaxes(title=x_label, type="log")
        elif self.cfg.plotting_engine == "pyplot" and self.cfg.use_stock.over_gdp:
            for ax in fig.get_axes():
                ax.set_xscale("log")
                ax.set_xlabel(x_label)

        extrapolation_name = "_extrapolation" if show_extrapolation else ""
        future_name = "_projection" if show_future else "_historic"
        linecolor_str = f"_by_{linecolor_dim}" if linecolor_dim is not None else ""
        subplot_str = f"_by_{subplot_dim}" if subplot_dim is not None else ""
        over_str = "_overGDP" if self.cfg.use_stock.over_gdp else "_overTime"
        self.plot_and_save_figure(
            ap,
            f"stocks{extrapolation_name}{future_name}{subplot_str}{linecolor_str}{over_str}.png",
            do_plot=False,
        )

    def visualize_gdppc(self, mfa: fd.MFASystem, change=False, per_capita=False):
        gdppc = mfa.parameters["gdppc"]
        if not per_capita:
            gdppc = gdppc * mfa.parameters["population"]
        if change:
            gdppc = gdppc.apply(np.diff, kwargs={"axis": 0, "prepend": 0})
            gdppc[1900] = gdppc[1901]
        ap = self.plotter_class(
            array=gdppc,
            intra_line_dim="Time",
            linecolor_dim="Region",
            display_names=self.display_names.dct,
            title=f"GDP{' per capita' if per_capita else ''}{' growth rate' if change else ''}",
        )
        fig = ap.plot()
        if change:
            self.plot_and_save_figure(ap, "gdppc_change.png", do_plot=False)
        else:
            fig.update_yaxes(type="log")
            self.plot_and_save_figure(ap, "gdppc.png", do_plot=False)
