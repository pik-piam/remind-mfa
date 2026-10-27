import argparse
import flodym as fd

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


def _exclude_processes(material: str, carbon_only: bool) -> list[str]:
    base = ["sysenv", "imports", "exports"]
    if material == "plastics":
        excluded = base + ["c4_production", "other_reactants"]
        if not carbon_only:
            excluded.append("atmosphere")
        return excluded
    return base


def _slice_dict(material: str, carbon_only: bool) -> dict:
    config = get_material_config(material)
    slice_dict = dict(config.sankey_slice_dict or {"t": 2050})
    if material == "plastics":
        if carbon_only:
            slice_dict["e"] = "C"
        else:
            slice_dict.pop("e", None)
    return slice_dict


def _base_visualization_kwargs(
    material: str,
    do_show_figs: bool,
    slice_dict: dict,
    carbon_only: bool,
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
                "exclude_processes": _exclude_processes(material, carbon_only),
                "exclude_flows": [],
            },
        ),
    }


def _build_visualizer(material: str, do_show_figs: bool, carbon_only: bool = True):
    config = get_material_config(material)
    kwargs = _base_visualization_kwargs(
        material=config.material,
        do_show_figs=do_show_figs,
        slice_dict=_slice_dict(config.material, carbon_only),
        carbon_only=carbon_only,
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


def bypass_flow(mfa: fd.MFASystem, from_process: str, via_process: str, to_process: str):
    first = mfa.flows.pop(f"{from_process} => {via_process}")
    second = mfa.flows.pop(f"{via_process} => {to_process}")
    mfa.flows[f"{from_process} => {to_process}"] = first
    mfa.flows[f"{from_process} => {to_process}"].to_process = second.to_process
    mfa.flows[f"{from_process} => {to_process}"].name = f"{from_process} => {to_process}"


def modify_mfa_for_sankey(mfa: fd.MFASystem, material):
    if material == "plastics":
        bypass_flow(mfa, "reclmech", "aux_recyclate_market", "primary_market")
        bypass_flow(mfa, "reclchem", "aux_recl_feedstock_market", "hvc_production")


def main(material: str = "plastics", carbon_only: bool = True):
    config = get_material_config(material)
    mfa = load_future_mfa(config.material)
    modify_mfa_for_sankey(mfa, material)
    visualizer = _build_visualizer(material, do_show_figs=False, carbon_only=carbon_only)
    visualizer.visualize_sankey(mfa)
    fig = visualizer.figures["sankey"]
    # do not save, as process positions need to be manually adjusted in the browser
    fig.show(renderer="browser")
    return fig


def main_all():
    """Plastics (carbon only and all elements), steel, and cement."""
    main(material="plastics", carbon_only=True)
    main(material="plastics", carbon_only=False)
    main(material="steel")
    main(material="cement")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", choices=["plastics", "steel", "cement", "all"], default="all")
    parser.add_argument(
        "--carbon-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="plastics only: show carbon flows; otherwise all elements without atmosphere",
    )
    args = parser.parse_args()
    if args.material == "all":
        main_all()
    else:
        main(material=args.material, carbon_only=args.carbon_only)
