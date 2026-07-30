import pathlib
import pickle
from constants import PATH_PLASTICS, RUN_PLASTICS

from remind_mfa.common.common_config import (
    BaseVisualizationCfg,
    ConsumptionVisualizationCfg,
    SankeyVisualizationCfg,
    StockVisualizationCfg,
    VisualizationCfg,
)
from remind_mfa.plastics.plastics_mappings import PlasticsDisplayNames
from remind_mfa.plastics.plastics_visualization import PlasticsVisualizer

DIRECTORY = PATH_PLASTICS
RUN_NAME = RUN_PLASTICS


def make_visualization_cfg() -> VisualizationCfg:
    return VisualizationCfg(
        figures_path="figures",
        do_show_figs=True,
        do_save_figs=False,
        plotting_engine="plotly",
        plotly_renderer="browser",
        use_stock=StockVisualizationCfg(do_visualize=False),
        production=BaseVisualizationCfg(do_visualize=False),
        trade=BaseVisualizationCfg(do_visualize=False),
        consumption=ConsumptionVisualizationCfg(do_visualize=False),
        sankey=SankeyVisualizationCfg(do_visualize=True, plotter_args={}),
        extrapolation=BaseVisualizationCfg(do_visualize=False),
    )


def main():
    pickle_path = DIRECTORY / f"{RUN_NAME}.pickle"
    with pickle_path.open("rb") as file_handle:
        mfa = pickle.load(file_handle).future_mfa

    visualizer = PlasticsVisualizer(
        cfg=make_visualization_cfg(),
        display_names=PlasticsDisplayNames(),
    )
    visualizer.visualize_sankey(mfa)


if __name__ == "__main__":
    main()
