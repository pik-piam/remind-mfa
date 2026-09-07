import warnings

from dotenv import load_dotenv

from _constants import MATERIAL_ORDER, MFA_REGION_MAPPINGS
from fig1_fig7_regions import main as render_regions
from fig8_demand import main as render_demand
from fig10_trade import main as render_trade
from fig11_scenarios import main as render_scenarios


def main(show: bool = False):

    load_dotenv()

    render_regions(aggregate_regions=False, show=show)
    render_regions(aggregate_regions=True, show=show)

    for mfa_regions in MFA_REGION_MAPPINGS:
        for use_h12 in (False, True):
            render_demand(use_h12=use_h12, mfa_regions=mfa_regions, show=show)

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
