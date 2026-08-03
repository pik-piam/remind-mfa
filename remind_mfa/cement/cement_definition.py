import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.common_definition import ExtrapolationDefinition
from remind_mfa.common.common_definition import PlainDataPointDefinition
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition

# fmt: off

def get_cement_definition(
    cfg: CementCfg, historic: bool, bottom_up: bool = False
) -> RemindMFADefinition:

    if historic and bottom_up:
        raise ValueError(
            "Historical Bottom-up not implemented. Please set historic=False or bottom_up=False."
        )
    

    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
        fd.DimensionDefinition(name="Product Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Material Constituent", dim_letter="k", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
        # carbonation dimensions
        fd.DimensionDefinition(name="Product Application", dim_letter="a", dtype=str),
        fd.DimensionDefinition(name="Waste Type", dim_letter="w", dtype=str),
        fd.DimensionDefinition(name="Waste Size", dim_letter="p", dtype=str),
        fd.DimensionDefinition(name="Carbonation Location", dim_letter="c", dtype=str),
        # service demand
        fd.DimensionDefinition(name="Structure", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Common Good", dim_letter="u", dtype=str),  # Res/Com
        fd.DimensionDefinition(name="Bottom-up Good", dim_letter="b", dtype=str),  # RS/RM/Com
        fd.DimensionDefinition(name="Dwelling Type", dim_letter="d", dtype=str),  # RS/RM
        fd.DimensionDefinition(name="Extended Good", dim_letter="e", dtype=str),  # RS/RM/Com/Ind/Civ
    ]

    # 2) Processes
    if historic:
        processes = [
            "sysenv",
            "prod_cement",
            "market_cement",
            "use",
            "imports",
            "exports",
        ]
    else:
        processes = [
            "sysenv",
            "prod_clinker",
            "market_clinker",
            "prod_cement",
            "market_cement",
            "prod_product",
            "use",
            "imports",
            "exports",
        ]

    # 3) Flows
    if historic:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="market_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="market_cement", to_process="exports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="market_cement", to_process="use", dim_letters=("h", "r", "g")),
            fd.FlowDefinition(from_process="market_cement", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "g")),
        ]
    else:
        # the combined (bottom-up) MFA runs at the extended good resolution and keeps
        # the structure resolution through to the final flows and stocks
        good_letter = "e" if bottom_up else "g"
        full_flow_letters = ("t", "r", good_letter, "m")
        if bottom_up:
            full_flow_letters += ("s",)
        flows = [
            # clinker production
            fd.FlowDefinition(from_process="sysenv", to_process="prod_clinker", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="market_clinker", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="sysenv", dim_letters=("t", "r")),
            # clinker trade
            fd.FlowDefinition(from_process="market_clinker", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_clinker", dim_letters=("t", "r")),
            # cement production
            fd.FlowDefinition(from_process="market_clinker", to_process="prod_cement", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="market_cement", dim_letters=("t", "r")),
            # cement trade
            fd.FlowDefinition(from_process="market_cement", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_cement", dim_letters=("t", "r")),
            # cement losses during construction
            fd.FlowDefinition(from_process="market_cement", to_process="sysenv", dim_letters=("t", "r")),
            # product production
            fd.FlowDefinition(from_process="market_cement", to_process="prod_product", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="sysenv", to_process="prod_product", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="prod_product", to_process="use", dim_letters=full_flow_letters + ("k",)),
            # use phase: the in-use outflow leaves the system boundary. When the carbonation model
            # is active it reroutes this outflow through the eol stock (which it injects at runtime).
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=full_flow_letters + ("k",)),
            # general trade
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
        ]

    # 4) Stocks
    if historic:
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("h", "r", "g"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
                time_letter="h",
            ),
        ]
    else:
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.StockDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
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
                        dim_letters=("t", "r", "u"),
                        subclass=fd.StockDrivenDSM,
                        lifetime_model_class=cfg.model_switches.lifetime_model,
                    ),
                    fd.StockDefinition(
                        name="bu_in_use",
                        process=None,  # no associated process
                        dim_letters=("t", "r", "b", "s"),
                        subclass=fd.InflowDrivenDSM,
                        lifetime_model_class=cfg.model_switches.lifetime_model,
                    ),
                    fd.StockDefinition(
                        name="td_in_use",
                        process=None,  # no associated process
                        dim_letters=full_flow_letters,
                        subclass=fd.InflowDrivenDSM,
                        lifetime_model_class=cfg.model_switches.lifetime_model,
                    ),
                ]
            )

    # 5) Parameters
    parameters = [
        # historic + future parameters: if time-dependent (h), they will have to be projected to (t)
        RemindMFAParameterDefinition(name="good_split", dim_letters=("r", "g",),
                                     description="Split of cement production into different goods."),
        RemindMFAParameterDefinition(name="cement_production", dim_letters=("h", "r"),
                                     description="Historic cement production volume for each region and year."),
        RemindMFAParameterDefinition(name="clinker_ratio", dim_letters=("h", "r"),
                                     description="Historic clinker-to-cement ratio for each region."),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("h", "r", "g"),
                                     description="Mean lifetime of historic cement stocks by region and good."),
        RemindMFAParameterDefinition(name="lifetime_rel_std", dim_letters=(),
                                     description="Relative standard deviation of lifetime of cement in buildings and infrastructure."),
        # trade parameters
        RemindMFAParameterDefinition(name="clinker_imports", dim_letters=("h", "r"),
                                     description="Historic clinker imports for each region and year."),
        RemindMFAParameterDefinition(name="clinker_exports", dim_letters=("h", "r"),
                                     description="Historic clinker exports for each region and year."),
        RemindMFAParameterDefinition(name="cement_imports", dim_letters=("h", "r"),
                                     description="Historic cement imports for each region and year."),
        RemindMFAParameterDefinition(name="cement_exports", dim_letters=("h", "r"),
                                     description="Historic cement exports for each region and year."),
        # future parameters
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r", "S"),
                                     description="Historic and projected population for each region and model year."),
        RemindMFAParameterDefinition(name="gdppc", dim_letters=("t", "r", "S"),
                                     description="Historic and projected GDP per capita for each region and model year."),
        RemindMFAParameterDefinition(name="cement_losses", dim_letters=(),
                                     description="Share of cement lost during construction."),
        RemindMFAParameterDefinition(name="clinker_losses", dim_letters=(),
                                     description="Share of clinker lost during clinker production."),
        RemindMFAParameterDefinition(name="cement_ratio", dim_letters=("r", "m",),
                                     description="Share of product mass that is cement for each product material."),
        RemindMFAParameterDefinition(name="product_material_split", dim_letters=("r", "m"),
                                     description="Share of product output allocated to each material by region."),
        # carbonation parameters
        RemindMFAParameterDefinition(name="clinker_cao_ratio", dim_letters=(),
                                     description="Mass fraction of CaO contained in clinker."),
        RemindMFAParameterDefinition(name="cao_carbonation_share", dim_letters=("m",),
                                     description="Share of CaO that is available for carbonation per material."),
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
                                     description="Share of each product material distributed across product applications, by region."),
        RemindMFAParameterDefinition(name="waste_type_split", dim_letters=("r", "w"),
                                     description="Share of end-of-life cement flows by waste type and region."),
        RemindMFAParameterDefinition(name="waste_size_share", dim_letters=("r", "w", "p"),
                                     description="Share of waste distributed across size classes per region and type."),
        RemindMFAParameterDefinition(name="waste_size_min", dim_letters=("w", "p"),
                                     description="Minimum particle size represented for each waste type and class."),
        RemindMFAParameterDefinition(name="waste_size_max", dim_letters=("w", "p"),
                                     description="Maximum particle size represented for each waste type and class."),
        # bottom-up parameters
        RemindMFAParameterDefinition(name="floorspace", dim_letters=("t", "r", "S", "u"),
                                     description="Historic and projected total buildings floorspace per region and common good (Res/Com)."),
        RemindMFAParameterDefinition(name="dwelling_split", dim_letters=("r", "d"),
                                     description="Split of residential floor area into single- (RS) and multi-family (RM) homes."),
        RemindMFAParameterDefinition(name="structure_split", dim_letters=("r", "b", "s"),
                                     description="Split of building goods into different structure types per region."),
        RemindMFAParameterDefinition(name="concrete_building_mi", dim_letters=("r", "b", "s"),
                                     description="Material intensity of concrete (t/m2) differentiated by building good and structure."),
        RemindMFAParameterDefinition(name="hibernating_stock_share", dim_letters=("r",),
                                     description="Share of building stock that is hibernating (built but unused and not demolished)."),
    ]

    # 6) Trades
    if historic:
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
        name="hibernating_stock_share",
        dim_letters=("r",),
    ),
    ExtrapolationDefinition(
        name="dwelling_split",
        dim_letters=("r", "d"),
        blending_function="poly_mix",
        split_dimension_letter="d",
        split_balancing_item="RM",
    ),
    ExtrapolationDefinition(
        name="structure_split",
        dim_letters=("r", "b", "s"),
        blending_function="poly_mix",
        split_dimension_letter="s",
        split_balancing_item="C",
    ),
]

# fmt: on
