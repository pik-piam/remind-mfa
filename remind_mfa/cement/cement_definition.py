import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.common_definition import ExtrapolationDefinition
from remind_mfa.common.common_definition import PlainDataPointDefinition
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition

# fmt: off

def get_cement_definition(
    cfg: CementCfg, historical: bool, bottom_up: bool = False
) -> RemindMFADefinition:

    if historical and bottom_up:
        raise ValueError(
            "Historical Bottom-up not implemented. Please set historical=False or bottom_up=False."
        )


    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="End Use", dim_letter="u", dtype=str),
        fd.DimensionDefinition(name="Construction Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Construction Material Constituent", dim_letter="k", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
        # carbonation dimensions
        fd.DimensionDefinition(name="Product Application", dim_letter="a", dtype=str),
        fd.DimensionDefinition(name="Waste Type", dim_letter="w", dtype=str),
        fd.DimensionDefinition(name="Waste Size", dim_letter="p", dtype=str),
        fd.DimensionDefinition(name="Carbonation Location", dim_letter="l", dtype=str),
        # service demand
        fd.DimensionDefinition(name="Structure", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Common End Use", dim_letter="c", dtype=str),  # Residential/Commercial
        fd.DimensionDefinition(name="Bottom-up End Use", dim_letter="b", dtype=str),  # Residential Single-/Multi-Family, Commercial
        fd.DimensionDefinition(name="Residential Type", dim_letter="d", dtype=str),  # Residential Single-/Multi-Family
        fd.DimensionDefinition(name="Extended End Use", dim_letter="e", dtype=str),  # Bottom-up End Use + Industrial, Civil Engineering
    ]

    # 2) Processes
    if historical:
        processes = [
            "sysenv",
            "cement_production",
            "cement_market",
            "construction",
            "use",
            "imports",
            "exports",
        ]
    else:
        processes = [
            "sysenv",
            "clinker_production",
            "clinker_market",
            "cement_production",
            "cement_market",
            "construction",
            "use",
            "hibernating",
            "reuse",
            "imports",
            "exports",
        ]

    # 3) Flows
    if historical:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="cement_production", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_production", to_process="cement_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="exports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="imports", to_process="cement_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="construction", dim_letters=("h", "r", "u", "m")),
            fd.FlowDefinition(from_process="sysenv", to_process="construction", dim_letters=("h", "r", "u", "m")),
            fd.FlowDefinition(from_process="construction", to_process="use", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "u")),
        ]
    else:
        # the combined (bottom-up) MFA runs at the extended end-use resolution and keeps
        # the structure resolution through to the final flows and stocks
        end_use_letter = "e" if bottom_up else "u"
        full_flow_letters = ("t", "r", end_use_letter, "m")
        if bottom_up:
            full_flow_letters += ("s",)
        flows = [
            # clinker production
            fd.FlowDefinition(from_process="sysenv", to_process="clinker_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="clinker_production", to_process="clinker_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="clinker_production", to_process="sysenv", dim_letters=("t", "r")),
            # clinker trade
            fd.FlowDefinition(from_process="clinker_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="clinker_market", dim_letters=("t", "r")),
            # cement production
            fd.FlowDefinition(from_process="clinker_market", to_process="cement_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="cement_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="cement_production", to_process="cement_market", dim_letters=("t", "r")),
            # cement trade
            fd.FlowDefinition(from_process="cement_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="cement_market", dim_letters=("t", "r")),
            # cement losses during construction
            fd.FlowDefinition(from_process="cement_market", to_process="sysenv", dim_letters=("t", "r")),
            # construction
            fd.FlowDefinition(from_process="cement_market", to_process="construction", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="sysenv", to_process="construction", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="construction", to_process="use", dim_letters=full_flow_letters + ("k",)),
            # use phase: the in-use outflow leaves the system boundary. When the carbonation model
            # is active it reroutes this outflow through the eol stock (which it injects at runtime).
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=full_flow_letters + ("k",)),
            # hibernation: part of the in-use outflow remains in place, without outflow
            fd.FlowDefinition(from_process="use", to_process="hibernating", dim_letters=full_flow_letters + ("k",)),
            # reuse: part of the in-use outflow re-enters the in-use stock
            fd.FlowDefinition(from_process="use", to_process="reuse", dim_letters=full_flow_letters + ("k",)),
            fd.FlowDefinition(from_process="reuse", to_process="use", dim_letters=full_flow_letters + ("k",)),
            # general trade
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
        ]

    # 4) Stocks
    if historical:
        stocks = [
            fd.StockDefinition(
                name="use",
                process="use",
                dim_letters=("h", "r", "u"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
                time_letter="h",
            ),
        ]
    else:
        stocks = [
            fd.StockDefinition(
                name="use",
                process="use",
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="hibernating",
                process="hibernating",
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            # The eol, atmosphere and carbonated_co2 stocks are injected at runtime by
            # CementCarbonUptakeModel when carbonation is active (see cement_carbon_uptake_model.py).
        ]
        if bottom_up:
            stocks.extend(
                [
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
            )

    # 5) Parameters
    parameters = [
        # historical + future parameters: if time-dependent (h), they will have to be projected to (t)
        RemindMFAParameterDefinition(name="end_use_split", dim_letters=("r", "u",),
                                     description="Split of cement production into different end uses."),
        RemindMFAParameterDefinition(name="cement_production", dim_letters=("h", "r"),
                                     description="Historical cement production volume for each region and year."),
        RemindMFAParameterDefinition(name="clinker_ratio", dim_letters=("h", "r"),
                                     description="Historical clinker-to-cement ratio for each region."),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("h", "r", "u"),
                                     description="Mean lifetime of historical cement stocks by region and end use."),
        RemindMFAParameterDefinition(name="lifetime_rel_std", dim_letters=(),
                                     description="Relative standard deviation of lifetime of cement in buildings and infrastructure."),
        # trade parameters
        RemindMFAParameterDefinition(name="clinker_imports", dim_letters=("h", "r"),
                                     description="Historical clinker imports for each region and year."),
        RemindMFAParameterDefinition(name="clinker_exports", dim_letters=("h", "r"),
                                     description="Historical clinker exports for each region and year."),
        RemindMFAParameterDefinition(name="cement_imports", dim_letters=("h", "r"),
                                     description="Historical cement imports for each region and year."),
        RemindMFAParameterDefinition(name="cement_exports", dim_letters=("h", "r"),
                                     description="Historical cement exports for each region and year."),
        # future parameters
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r", "S"),
                                     description="Historical and projected population for each region and model year."),
        RemindMFAParameterDefinition(name="gdppc", dim_letters=("t", "r", "S"),
                                     description="Historical and projected GDP per capita for each region and model year."),
        RemindMFAParameterDefinition(name="cement_losses", dim_letters=(),
                                     description="Share of cement lost during construction."),
        RemindMFAParameterDefinition(name="clinker_losses", dim_letters=(),
                                     description="Share of clinker lost during clinker production."),
        RemindMFAParameterDefinition(name="cement_ratio", dim_letters=("r", "m",),
                                     description="Mass share of cement in each newly produced construction material."),
        RemindMFAParameterDefinition(name="construction_material_split", dim_letters=("r", "m"),
                                     description="Share of cement used in each construction material by region."),
        # carbonation parameters
        RemindMFAParameterDefinition(name="clinker_cao_ratio", dim_letters=(),
                                     description="Mass fraction of CaO contained in clinker."),
        RemindMFAParameterDefinition(name="cao_carbonation_share", dim_letters=("m",),
                                     description="Share of CaO that is available for carbonation per construction material."),
        RemindMFAParameterDefinition(name="cao_emission_factor", dim_letters=(),
                                     description="Process CO2 emission factor from producing CaO."),
        RemindMFAParameterDefinition(name="ckd_cao_ratio", dim_letters=(),
                                     description="CaO content ratio present in cement kiln dust."),
        RemindMFAParameterDefinition(name="ckd_landfill_share", dim_letters=(),
                                     description="Share of cement kiln dust disposed to landfill."),
        RemindMFAParameterDefinition(name="carbonation_rate", dim_letters=("r", "a"),
                                     description="Carbonation rate for exposed stocks by region and application."),
        RemindMFAParameterDefinition(name="carbonation_rate_buried", dim_letters=("r", "a"),
                                     description="Carbonation rate for buried stocks by region and application."),
        RemindMFAParameterDefinition(name="carbonation_rate_coating", dim_letters=(),
                                     description="Carbonation rate modifier factoring in coated cement products."),
        RemindMFAParameterDefinition(name="carbonation_rate_co2", dim_letters=(),
                                     description="Carbonation rate modifier factoring in increased atmospheric CO2 concentrations."),
        RemindMFAParameterDefinition(name="carbonation_rate_additives", dim_letters=(),
                                     description="Carbonation rate modifier factoring in cement additives."),
        RemindMFAParameterDefinition(name="product_thickness", dim_letters=("a",),
                                     description="Average thickness assumed for each product application."),
        RemindMFAParameterDefinition(name="material_application_split", dim_letters=("r", "m", "a"),
                                     description="Share of each construction material distributed across product applications, by region."),
        RemindMFAParameterDefinition(name="waste_type_split", dim_letters=("r", "w"),
                                     description="Share of end-of-life cement flows by waste type and region."),
        RemindMFAParameterDefinition(name="waste_size_share", dim_letters=("r", "w", "p"),
                                     description="Share of waste distributed across size classes per region and type."),
        RemindMFAParameterDefinition(name="waste_size_min", dim_letters=("w", "p"),
                                     description="Minimum particle size represented for each waste type and class."),
        RemindMFAParameterDefinition(name="waste_size_max", dim_letters=("w", "p"),
                                     description="Maximum particle size represented for each waste type and class."),
        # bottom-up parameters
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

    # 6) Trades
    if historical:
        trades = [
            TradeDefinition(name="clinker", dim_letters=("h", "r")),
            TradeDefinition(name="cement", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="clinker", dim_letters=("t", "r")),
            TradeDefinition(name="cement", dim_letters=("t", "r")),
        ]

    return RemindMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
        trades=trades,
    )


scenario_parameters = [
    PlainDataPointDefinition(
        name="development_gdppc_low",
        description="GDP per capita (PPP) below which splits fully converge to their global means.",
    ),
    PlainDataPointDefinition(
        name="development_gdppc_high",
        description="GDP per capita (PPP) above which regions keep their own splits. ",
    ),
    ExtrapolationDefinition(
        name="clinker_ratio",
        dim_letters=("r",),
    ),
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
    ExtrapolationDefinition(
        name="concrete_reuse_share",
        create_new=True,
    ),
]

# fmt: on
