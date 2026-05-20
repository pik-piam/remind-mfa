import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition


def get_cement_definition(cfg: CementCfg, historic: bool) -> RemindMFADefinition:

    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Stock Type", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Product Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Material Constituent", dim_letter="k", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
        # carbonation dimensions
        fd.DimensionDefinition(name="Product Application", dim_letter="a", dtype=str),
        fd.DimensionDefinition(name="Waste Type", dim_letter="w", dtype=str),
        fd.DimensionDefinition(name="Waste Size", dim_letter="p", dtype=str),
        fd.DimensionDefinition(name="Carbonation Location", dim_letter="c", dtype=str),
        # service demand
        fd.DimensionDefinition(name="Structure", dim_letter="b", dtype=str),  # b for building
        fd.DimensionDefinition(name="Function", dim_letter="f", dtype=str),
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
            "eol",
            "atmosphere",
            "carbonation",
            "imports",
            "exports",
        ]

    # fmt: off
    # 3) Flows
    if historic:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="market_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="sysenv", dim_letters=("h", "r")),  # cement losses
            fd.FlowDefinition(from_process="market_cement", to_process="exports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_cement", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="market_cement", to_process="use", dim_letters=("h", "r", "s")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "s")),
        ]
    else:
        flows = [
            # clinker production
            fd.FlowDefinition(from_process="sysenv", to_process="prod_clinker", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="market_clinker", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="sysenv", dim_letters=("t", "r")),  # CKD production
            # clinker trade
            fd.FlowDefinition(from_process="market_clinker", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_clinker", dim_letters=("t", "r")),
            # cement production
            fd.FlowDefinition(from_process="market_clinker", to_process="prod_cement", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="market_cement", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="prod_cement", to_process="sysenv", dim_letters=("t", "r")),  # cement losses
            # cement trade
            fd.FlowDefinition(from_process="market_cement", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="market_cement", dim_letters=("t", "r")),
            # product production
            fd.FlowDefinition(from_process="market_cement", to_process="prod_product", dim_letters=("t", "r", "s", "m")),
            fd.FlowDefinition(from_process="sysenv", to_process="prod_product", dim_letters=("t", "r", "s", "m")),
            fd.FlowDefinition(from_process="prod_product", to_process="use", dim_letters=("t", "r", "s", "m", "k")),
            # use and end-of-life
            fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("t", "r", "s", "m", "k")),
            fd.FlowDefinition(from_process="eol", to_process="sysenv", dim_letters=("t", "r", "s", "m", "k")),
            # general trade
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
            # atmosphere
            fd.FlowDefinition(from_process="prod_clinker", to_process="atmosphere", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="atmosphere", to_process="carbonation", dim_letters=("t", "r", "c")),
        ]

    # fmt: on
    # 4) Stocks
    if historic:
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("h", "r", "s"),
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
                dim_letters=("t", "r", "s", "m", "k"),
                subclass=fd.StockDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="eol",
                process="eol",
                dim_letters=("t", "r", "s", "m", "k"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=fd.FixedLifetime,
            ),
            fd.StockDefinition(
                name="atmosphere",
                process="atmosphere",
                dim_letters=("t", "r"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="carbonated_co2",
                process="carbonation",
                dim_letters=("t", "r", "c"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=fd.FixedLifetime,
            ),
        ]

    # fmt: off
    # 5) Parameters
    parameters = [
        # historic + future parameters: if time-dependent (h), they will have to be projected to (t)
        RemindMFAParameterDefinition(name="stock_type_split", dim_letters=("r", "s",),
                                     description="Split of cement production into different stock types."),
        RemindMFAParameterDefinition(name="cement_production", dim_letters=("h", "r"),
                                     description="Historic cement production volume for each region and year."),
        RemindMFAParameterDefinition(name="clinker_ratio", dim_letters=("h", "r"),
                                     description="Historic clinker-to-cement ratio for each region."),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("h", "r", "s"),
                                     description="Mean lifetime of historic cement stocks by region and stock type."),
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
                                     description="Share of cement lost during cement production."),
        RemindMFAParameterDefinition(name="clinker_losses", dim_letters=(),
                                     description="Share of clinker lost during clinker production."),
        RemindMFAParameterDefinition(name="cement_ratio", dim_letters=("r", "m",),
                                     description="Share of product mass that is cement for each product material."),
        RemindMFAParameterDefinition(name="product_material_split", dim_letters=("r", "m"),
                                     description="Share of product output allocated to each material by region."),
        RemindMFAParameterDefinition(name="industrialized_regions", dim_letters=("r",),
                                     description="List of regions considered industrialized for stock extrapolation."),
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
        RemindMFAParameterDefinition(name="concrete_building_mi", dim_letters=("r", "f", "b"),
                                     description="Material intensity of concrete (t/m2) differentiated by building function and structure."),
        RemindMFAParameterDefinition(name="function_buildings_split", dim_letters=("r", "s", "f"),
                                     description="Split of building stock types into different functions per region."),
        RemindMFAParameterDefinition(name="structure_buildings_split", dim_letters=("r", "f", "b"),
                                     description="Split of building functions into different structure types per region."),
        RemindMFAParameterDefinition(name="floorspace", dim_letters=("t", "r", "s"),
                                     description="Historic and projected total buildings floorspace per region and stock type."),
        RemindMFAParameterDefinition(name="hibernating_stock_share", dim_letters=("r",),
                                     description="Share of building stock that is hibernating (built but unused and not demolished)."),
    ]
    # fmt: on

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


scenario_parameters = []
