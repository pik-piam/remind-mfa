"""Tests for the figure collector of `CommonVisualizer`."""

import flodym as fd
import flodym.export as fde
import numpy as np
import plotly.graph_objects as go

from remind_mfa.common.common_config import (
    BaseVisualizationCfg,
    ConsumptionVisualizationCfg,
    GDPVisualizationCfg,
    SankeyVisualizationCfg,
    StockVisualizationCfg,
    VisualizationCfg,
)
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.common_visualization import CommonVisualizer


def make_visualization_cfg() -> VisualizationCfg:
    """A complete visualization config that neither shows nor saves anything."""
    return VisualizationCfg(
        do_show_figs=False,
        do_save_figs=False,
        do_save_figs_html=False,
        use_stock=StockVisualizationCfg(),
        gdp=GDPVisualizationCfg(),
        production=BaseVisualizationCfg(),
        trade=BaseVisualizationCfg(),
        consumption=ConsumptionVisualizationCfg(),
        sankey=SankeyVisualizationCfg(),
        extrapolation=BaseVisualizationCfg(),
        sector_splits=BaseVisualizationCfg(),
    )


def make_visualizer() -> CommonVisualizer:
    return CommonVisualizer(cfg=make_visualization_cfg(), display_names=CommonDisplayNames())


def make_plotter() -> fde.PlotlyArrayPlotter:
    time = fd.Dimension(name="Time", letter="t", items=[2020, 2030])
    array = fd.FlodymArray(
        dims=fd.DimensionSet(dim_list=[time]), values=np.array([1.0, 2.0]), name="stock"
    )
    return fde.PlotlyArrayPlotter(array=array, intra_line_dim="Time")


def test_plot_and_save_figure_plots_and_collects_the_figure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    visualizer = make_visualizer()
    plotter = make_plotter()

    visualizer.plot_and_save_figure(plotter, "stocks")

    assert plotter.fig is not None
    assert len(plotter.fig.data) == 1
    assert visualizer.figures == {"stocks": plotter.fig}
    assert not any(tmp_path.iterdir())  # neither shown nor saved


def test_plot_and_save_figure_can_take_an_already_drawn_figure():
    visualizer = make_visualizer()
    plotter = make_plotter()
    plotter.plot()

    visualizer.plot_and_save_figure(plotter, "production", do_plot=False)

    assert plotter.fig is not None
    assert len(plotter.fig.data) == 1  # not drawn a second time
    assert list(visualizer.figures) == ["production"]


def test_plotly_only_figures_are_collected_too():
    visualizer = make_visualizer()
    sankey = go.Figure(go.Sankey())

    visualizer._show_and_save_plotly(sankey, "sankey")

    assert visualizer.figures == {"sankey": sankey}


def test_each_visualizer_has_its_own_collection():
    first, second = make_visualizer(), make_visualizer()
    first._show_and_save_plotly(go.Figure(), "one")
    assert second.figures == {}
