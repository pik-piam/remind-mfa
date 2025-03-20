import os
from matplotlib import pyplot as plt
from simson.common.base_model import SimsonBaseModel
import plotly.graph_objects as go
import flodym as fd
import flodym.export as fde
from plotly import colors as plc

from simson.common.common_cfg import VisualizationCfg


class CommonDataExporter(SimsonBaseModel):
    output_path: str
    do_export: dict = {"pickle": True, "csv": True}
    cfg: VisualizationCfg
    _display_names: dict = {}

    def export_mfa(self, mfa: fd.MFASystem):
        if self.do_export["pickle"]:
            fde.export_mfa_to_pickle(mfa=mfa, export_path=self.export_path("mfa.pickle"))
        if self.do_export["csv"]:
            dir_out = os.path.join(self.export_path(), "flows")
            fde.export_mfa_flows_to_csv(mfa=mfa, export_directory=dir_out)
            fde.export_mfa_stocks_to_csv(mfa=mfa, export_directory=dir_out)

    def export_path(self, filename: str = None):
        path_tuple = (self.output_path, "export")
        if filename is not None:
            path_tuple += (filename,)
        return os.path.join(*path_tuple)

    def figure_path(self, filename: str):
        return os.path.join(self.output_path, "figures", filename)

    def _show_and_save_plotly(self, fig: go.Figure, name):
        if self.cfg.do_save_figs:
            fig.write_image(self.figure_path(f"{name}.png"))
        if self.cfg.do_show_figs:
            fig.show()

    def visualize_sankey(self, mfa: fd.MFASystem):
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=self._display_names, **self.cfg.sankey
        )
        fig = plotter.plot()

        fig.update_layout(
            # title_text=f"Steel Flows ({', '.join([str(v) for v in self.sankey['slice_dict'].values()])})",
            font_size=20,
        )

        self._show_and_save_plotly(fig, name="sankey")

    def figure_path(self, filename: str) -> str:
        return os.path.join(self.output_path, "figures", filename)

    def plot_and_save_figure(self, plotter: fde.ArrayPlotter, filename: str, do_plot: bool = True):
        if do_plot:
            plotter.plot()
        if self.cfg.do_show_figs:
            plotter.show()
        if self.cfg.do_save_figs:
            plotter.save(self.figure_path(filename), width=2200, height=1300)

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
        
    def plot_history_and_future(
        self,
        mfa: fd.MFASystem,
        data_to_plot: fd.FlodymArray,
        subplot_dim: dict = {},
        x_array: fd.FlodymArray = None,
        linecolor_dim: str = None,
        x_label: str = None,
        y_label: str = None,
        title: str = None,
        ):
        
        colors = plc.qualitative.Dark24
        colors = (
            colors[: data_to_plot.dims["r"].len]
            + colors[: data_to_plot.dims["r"].len]
            + ["black" for _ in range(data_to_plot.dims["r"].len)]
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
        fig = ap.plot()

        # Historic stock (solid)
        ap_hist = self.plotter_class(
            array=hist,
            intra_line_dim="Historic Time",
            linecolor_dim=linecolor_dim,
            **subplot_dim,
            display_names=self._display_names,
            x_array=hist_x_array,
            fig=fig,
            color_map=colors,
        )
        fig = ap_hist.plot()

        # Last historic year (black dot)
        ap_scatter = self.plotter_class(
            array=scatter,
            intra_line_dim="Last Historic Year",
            linecolor_dim=linecolor_dim,
            **subplot_dim,
            display_names=self._display_names,
            x_array=scatter_x_array,
            fig=fig,
            chart_type="scatter",
            color_map=colors,
            suppress_legend=True,
        )
        fig = ap_scatter.plot()
        
        return fig, ap_scatter