import warnings

from scripts_paper._constants import MATERIAL_ORDER
from scripts_paper.fig1_fig7_regions import main as render_regions
from scripts_paper.fig8_demand import main as render_demand
from scripts_paper.fig9_sankey import main as render_sankey
from scripts_paper.fig10_trade import main as render_trade
from scripts_paper.fig11_scenarios import main as render_scenarios


def main(show: bool = False):
    render_regions(aggregate_regions=False, show=show)
    render_regions(aggregate_regions=True, show=show)

    for use_h12 in (False, True):
        render_demand(use_h12=use_h12, show=show)

    for material in MATERIAL_ORDER:
        for use_h12 in (False, True):
            render_trade(material=material, use_h12=use_h12, show=show)

    for material in MATERIAL_ORDER:
        for use_h12 in (False, True):
            with warnings.catch_warnings():
                warnings.simplefilter("default")
                render_scenarios(material=material, use_h12=use_h12, show=show)


if __name__ == "__main__":
    main(show=False)