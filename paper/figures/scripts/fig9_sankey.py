import argparse

from remind_mfa.cement.cement_mappings import CementDisplayNames
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.common_config import (
    BaseVisualizationCfg,
    ConsumptionVisualizationCfg,
    GDPVisualizationCfg,
    SankeyVisualizationCfg,
    StockVisualizationCfg,
)
from remind_mfa.plastics.plastics_mappings import PlasticsDisplayNames
from remind_mfa.plastics.plastics_config import PlasticsVisualizationCfg
from remind_mfa.plastics.plastics_visualization import PlasticsVisualizer
from remind_mfa.steel.steel_mappings import SteelDisplayNames
from remind_mfa.steel.steel_config import SteelVisualizationCfg
from remind_mfa.steel.steel_visualization import SteelVisualizer
from remind_mfa.cement.cement_config import CementVisualizationCfg
from _constants import get_material_config
from _utils import load_future_mfa


def _exclude_processes(material: str) -> list[str]:
    base = ["sysenv", "imports", "exports"]
    if material == "plastics":
        return base + ["c4_production", "other_reactants"]
    return base


def _base_visualization_kwargs(
    material: str,
    do_show_figs: bool,
    slice_dict: dict,
) -> dict:
    return {
        "do_show_figs": do_show_figs,
        "do_save_figs": False,
        "plotting_engine": "plotly",
        "plotly_renderer": "browser",
        "use_stock": StockVisualizationCfg(do_visualize=False),
        "end_use_split": BaseVisualizationCfg(do_visualize=False),
        "gdp": GDPVisualizationCfg(do_visualize=False),
        "production": BaseVisualizationCfg(do_visualize=False),
        "trade": BaseVisualizationCfg(do_visualize=False),
        "consumption": ConsumptionVisualizationCfg(do_visualize=False),
        "extrapolation": BaseVisualizationCfg(do_visualize=False),
        "sankey": SankeyVisualizationCfg(
            do_visualize=True,
            plotter_args={
                "slice_dict": slice_dict,
                "exclude_processes": _exclude_processes(material),
                "exclude_flows": [],
            },
        ),
    }


def _build_visualizer(material: str, do_show_figs: bool):
    config = get_material_config(material)
    kwargs = _base_visualization_kwargs(
        material=config.material,
        do_show_figs=do_show_figs,
        slice_dict=config.sankey_slice_dict or {"t": 2050},
    )
    if config.material == "plastics":
        cfg = PlasticsVisualizationCfg(
            **kwargs,
            flows=BaseVisualizationCfg(do_visualize=False),
            polymer_splits=BaseVisualizationCfg(do_visualize=False),
        )
        return PlasticsVisualizer(cfg=cfg, display_names=PlasticsDisplayNames())
    if config.material == "steel":
        cfg = SteelVisualizationCfg(
            **kwargs,
            scrap_demand_supply=BaseVisualizationCfg(do_visualize=False),
        )
        return SteelVisualizer(cfg=cfg, display_names=SteelDisplayNames())
    cfg = CementVisualizationCfg(
        **kwargs,
        clinker_production=BaseVisualizationCfg(do_visualize=False),
        cement_production=BaseVisualizationCfg(do_visualize=False),
        construction=BaseVisualizationCfg(do_visualize=False),
        eol_stock=StockVisualizationCfg(do_visualize=False),
        carbonation=BaseVisualizationCfg(do_visualize=False),
    )
    return CementVisualizer(cfg=cfg, display_names=CementDisplayNames())


def main(material: str = "plastics", show: bool = True):
    config = get_material_config(material)
    mfa = load_future_mfa(config.material)
    visualizer = _build_visualizer(material, do_show_figs=False)
    visualizer.visualize_sankey(mfa)
    fig = visualizer.figures["sankey"]
    # do not save, as process positions need to be manually adjusted in the browser
    if show:
        fig.show(renderer="browser")
    return fig


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", choices=["plastics", "steel", "cement"], default="plastics")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    main(material=args.material, show=not args.no_show)
