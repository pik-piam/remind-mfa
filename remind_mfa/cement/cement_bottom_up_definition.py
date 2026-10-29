import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.common_definition import ExtrapolationDefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.common_definition import RemindMFAPartialDefinition

# fmt: off

def get_bottom_up_data_definition() -> RemindMFAPartialDefinition:
    """Dimensions and parameters of the bottom-up (service demand) module. Needed whenever
    the bottom-up module is active, also for the top-down MFAs of the reconciliation."""

    dimensions = [
        fd.DimensionDefinition(name="Structure", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Common End Use", dim_letter="c", dtype=str),  # Residential/Commercial
        fd.DimensionDefinition(name="Bottom-up End Use", dim_letter="b", dtype=str),  # Residential Single-/Multi-Family, Commercial
        fd.DimensionDefinition(name="Residential Type", dim_letter="d", dtype=str),  # Residential Single-/Multi-Family
        fd.DimensionDefinition(name="Extended End Use", dim_letter="e", dtype=str),  # Bottom-up End Use + Industrial, Civil Engineering
    ]

    parameters = [
        RemindMFAParameterDefinition(name="floorspace", dim_letters=("t", "r", "S", "c"),
                                     description="Historical and projected total buildings floorspace per region and common end use (Residential/Commercial)."),
        RemindMFAParameterDefinition(name="residential_type_split", dim_letters=("r", "d"),
                                     description="Split of residential floor area into single-family and multi-family homes."),
        RemindMFAParameterDefinition(name="structure_split", dim_letters=("r", "b", "s"),
                                     description="Split of building end uses into different structure types per region."),
        RemindMFAParameterDefinition(name="concrete_building_mi", dim_letters=("r", "b", "s"),
                                     description="Material intensity of concrete (t/m2) differentiated by building end use and structure."),
        RemindMFAParameterDefinition(name="unoccupied_residential_stock_share", dim_letters=("r",),
                                     description="Share of residential stock that is not permanently occupied (vacant dwellings and second homes)."),
    ]

    return RemindMFAPartialDefinition(dimensions=dimensions, parameters=parameters)


def get_bottom_up_system_definition(
    cfg: CementCfg, full_flow_letters: tuple[str, ...]
) -> RemindMFAPartialDefinition:
    """Stocks of the bottom-up MFA system, which are not part of the top-down MFAs.

    Args:
        cfg: Cement model configuration.
        full_flow_letters: Dimension letters of the end-use-resolved flows of the bottom-up MFA.
    """
    stocks = [
        fd.StockDefinition(
            name="floorspace",
            process=None,  # no associated process
            dim_letters=("t", "r", "c"),
            subclass=fd.StockDrivenDSM,
            lifetime_model_class=cfg.model_switches.lifetime_model,
        ),
        fd.StockDefinition(
            name="bu_use",
            process=None,  # no associated process
            dim_letters=("t", "r", "b", "s"),
            subclass=fd.InflowDrivenDSM,
            lifetime_model_class=cfg.model_switches.lifetime_model,
        ),
        fd.StockDefinition(
            name="td_use",
            process=None,  # no associated process
            dim_letters=full_flow_letters,
            subclass=fd.InflowDrivenDSM,
            lifetime_model_class=cfg.model_switches.lifetime_model,
        ),
    ]
    return RemindMFAPartialDefinition(stocks=stocks)


bottom_up_scenario_parameters = [
    ExtrapolationDefinition(
        name="unoccupied_residential_stock_share",
        dim_letters=("r",),
    ),
    ExtrapolationDefinition(
        name="residential_type_split",
        dim_letters=("r", "d"),
        blending_function="poly_mix",
        split_dimension_letter="d",
        split_balancing_item="Residential Multi-Family",
    ),
    ExtrapolationDefinition(
        name="structure_split",
        dim_letters=("r", "b", "s"),
        blending_function="poly_mix",
        split_dimension_letter="s",
        split_balancing_item="Reinforced Concrete Structure",
    ),
    RemindMFAParameterDefinition(
        name="min_timber_share",
        dim_letters=("r",),
        description="Minimum share of timber buildings the structure split converges to.",
    ),
    ExtrapolationDefinition(
        name="concrete_building_mi",
        dim_letters=("r", "b", "s"),
    ),
]

# fmt: on
