import os
import numpy as np
from matplotlib import pyplot as plt
import plotly.graph_objects as go
import plotly.colors as plc
import plotly.io as pio
from typing import Optional, TYPE_CHECKING
from pydantic import model_validator
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

    @model_validator(mode="after")
    def set_plotly_renderer(self):
        if self.cfg.plotting_engine == "plotly":
            pio.renderers.default = self.cfg.plotly_renderer
        return self

    def visualize(self, model: "CommonModel"):
        if not self.cfg.do_visualize:
            return
        self.visualize_common(model=model)
        self.visualize_custom(model=model)
        self.stop_and_show()

    def visualize_common(self, model: "CommonModel"):
        if self.cfg.use_stock.do_visualize:
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_good=True)
            self.visualize_use_stock(mfa=model.future_mfa, subplots_by_good=False)
        if self.cfg.sankey.do_visualize:
            self.visualize_sankey(model.future_mfa)
        # self.visualize_extrapolation_functions(model=model, stock_handler=model.stock_handler_common)
        # self.visualize_extrapolation_functions(model=model, stock_handler=model.stock_handler)

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
        return os.path.join(self.cfg.figures_path, filename)

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
                fig.update_xaxes(type="log", range=[3, 5])
            elif self.cfg.plotting_engine == "pyplot":
                for ax in fig.get_axes():
                    ax.set_xscale("log")
                    ax.set_xlim(1e3, 1e5)

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
            extrapolation.normalize_predictor(predictor)
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
