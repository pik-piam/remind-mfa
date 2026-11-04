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
from remind_mfa.common.common_visualization import CommonVisualizer, bypass_flows


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
        end_use_split=BaseVisualizationCfg(),
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


def make_chain_mfa() -> fd.MFASystem:
    """MFA system with the flow chain a => via => b and a separate flow a => c."""
    processes = fd.make_processes(["sysenv", "a", "via", "b", "c"])
    dims = fd.DimensionSet(dim_list=[fd.Dimension(name="Time", letter="t", items=[2020])])

    def flow(from_name: str, to_name: str, value: float) -> fd.Flow:
        return fd.Flow(
            from_process=processes[from_name],
            to_process=processes[to_name],
            dims=dims,
            values=np.array([value]),
            name=f"{from_name} => {to_name}",
        )

    flows = [flow("a", "via", 1.0), flow("via", "b", 1.0), flow("a", "c", 2.0)]
    return fd.MFASystem(
        dims=dims, parameters={}, processes=processes, flows={f.name: f for f in flows}
    )


def test_bypass_flows_replaces_the_chain_by_a_direct_flow():
    mfa = make_chain_mfa()

    bypassed = bypass_flows(mfa, [("a", "via", "b")])

    assert list(bypassed.flows) == ["a => c", "a => b"]
    direct = bypassed.flows["a => b"]
    assert direct.name == "a => b"
    assert direct.from_process.name == "a"
    assert direct.to_process.name == "b"
    np.testing.assert_array_equal(direct.values, [1.0])


def test_bypass_flows_leaves_the_original_mfa_unchanged():
    mfa = make_chain_mfa()
    first_flow = mfa.flows["a => via"]

    bypass_flows(mfa, [("a", "via", "b")])

    assert list(mfa.flows) == ["a => via", "via => b", "a => c"]
    assert mfa.flows["a => via"] is first_flow
    assert first_flow.name == "a => via"
    assert first_flow.to_process.name == "via"
