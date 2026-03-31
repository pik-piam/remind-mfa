import flodym as fd

from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition


def get_plastics_definition(cfg: PlasticsCfg, historic: bool) -> RemindMFADefinition:

    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Element", dim_letter="e", dtype=str),
        fd.DimensionDefinition(name="Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
    ]

    if historic:
        processes = [
            "sysenv",
            "fabrication",
            "good_market",
            "use",
        ]
    else:
        processes = [
            "sysenv",
            "virginfoss",
            "virginbio",
            "virgindaccu",
            "virginccu",
            "virgin",
            "fabrication",
            "primary_market",
            "waste_market",
            "good_market",
            "imports",
            "exports",
            "reclmech",
            "reclchem",
            "use",
            "eol",
            "incineration",
            "landfill",
            "collected",
            "mismanaged",
            "uncontrolled",
            "emission",
            "captured",
            "atmosphere",
        ]

    # fmt: off
    if historic:
        # names are auto-generated, see Flow class documentation
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="fabrication", dim_letters=("h", "r", "m", "g")),
            fd.FlowDefinition(from_process="fabrication", to_process="good_market", dim_letters=("h", "r", "m", "g")),
            fd.FlowDefinition(from_process="good_market", to_process="use", dim_letters=("h", "r", "m", "g")),
            fd.FlowDefinition(from_process="good_market", to_process="sysenv", dim_letters=("h", "r", "m", "g")),
            fd.FlowDefinition(from_process="sysenv", to_process="good_market", dim_letters=("h", "r", "m", "g")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "g")),
        ]
    else:
        flows = [
            # sysenv
            fd.FlowDefinition(from_process="sysenv", to_process="virginfoss", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="virginccu", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t","e","r")),
            # monomer stages
            fd.FlowDefinition(from_process="atmosphere", to_process="virginbio", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="atmosphere", to_process="virgindaccu", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="virginfoss", to_process="virgin", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="virginbio", to_process="virgin", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="virgindaccu", to_process="virgin", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="virginccu", to_process="virgin", dim_letters=("t","e","r")),
            # primary stages
            fd.FlowDefinition(from_process="virgin", to_process="primary_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="primary_market", to_process="fabrication", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="primary_market", to_process="exports", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="imports", to_process="primary_market", dim_letters=("t","e","r","m")),
            # fabrication stages
            fd.FlowDefinition(from_process="fabrication", to_process="good_market", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="good_market", to_process="use", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="good_market", to_process="exports", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="imports", to_process="good_market", dim_letters=("t","e","r","m","g")),
            # use stage
            fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("t","e","r","m","g")),
            # end-of-life stages
            fd.FlowDefinition(from_process="eol", to_process="collected", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="eol", to_process="mismanaged", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="reclmech", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="reclchem", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="landfill", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="incineration", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="mismanaged", to_process="uncontrolled", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="fabrication", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclchem", to_process="virgin", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclchem", to_process="emission", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="reclmech", to_process="uncontrolled", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="incineration", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="incineration", to_process="emission", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="captured", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="atmosphere", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="captured", to_process="virginccu", dim_letters=("t","e","r")),
            # waste trade
            fd.FlowDefinition(from_process="waste_market", to_process="collected", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="waste_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="waste_market", to_process="exports", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="imports", to_process="waste_market", dim_letters=("t","e","r","m")),

        ]
    # fmt: on

    if historic:
        stocks = [
            fd.StockDefinition(
                name="in_use_historic",
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
                name="in_use_dsm",
                dim_letters=("t", "r", "g"),
                subclass=fd.StockDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("t", "e", "r", "m", "g"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="atmospheric",
                process="atmosphere",
                dim_letters=("t", "e", "r"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="landfill",
                process="landfill",
                dim_letters=("t", "e", "r", "m"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="uncontrolled",
                process="uncontrolled",
                dim_letters=("t", "e", "r", "m"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
        ]

    # fmt: off
    parameters = [
        # EOL rates
        RemindMFAParameterDefinition(name="collection_rate", dim_letters=("h", "r"),
                                     description="Collection rate of plastic waste",),
        RemindMFAParameterDefinition(name="mechanical_recycling_rate", dim_letters=("h", "r"),
                                     description="Mechanical recycling rate of collected waste",),
        RemindMFAParameterDefinition(name="chemical_recycling_rate", dim_letters=("h", "r"),
                                     description="Chemical recycling rate of collected waste",),
        RemindMFAParameterDefinition(name="incineration_rate", dim_letters=("h", "r"),
                                     description="Incineration rate of collected waste",),
        # trade
        RemindMFAParameterDefinition(name="primary_his_imports", dim_letters=("h", "r", "m"),
                                     description="Historic primary plastics imports",),
        RemindMFAParameterDefinition(name="primary_his_exports", dim_letters=("h", "r", "m"),
                                     description="Historic primary plastics exports",),
        RemindMFAParameterDefinition(name="final_his_imports", dim_letters=("h", "r", "m", "g"),
                                     description="Historic final goods imports",),
        RemindMFAParameterDefinition(name="final_his_exports", dim_letters=("h", "r", "m", "g"),
                                     description="Historic final goods exports",),
        RemindMFAParameterDefinition(name="waste_his_imports", dim_letters=("h", "r", "m"),
                                     description="Historic plastic waste imports",),
        RemindMFAParameterDefinition(name="waste_his_exports", dim_letters=("h", "r", "m"),
                                     description="Historic plastic waste exports",),
        # virgin production rates
        RemindMFAParameterDefinition(name="bio_production_rate", dim_letters=("h", "r"),
                                     description="Share of bio-based plastics in virgin production",),
        RemindMFAParameterDefinition(name="daccu_production_rate", dim_letters=("h", "r"),
                                     description="Share of DACCU plastics in virgin production",),
        # recycling losses
        RemindMFAParameterDefinition(name="mechanical_recycling_yield", dim_letters=("t", "r", "m"),
                                     description="Yield of mechanical recycling",),
        RemindMFAParameterDefinition(name="reclmech_loss_uncontrolled_rate", dim_letters=("t", "r", "m"),
                                     description="Rate of mechanical recycling losses to uncontrolled disposal",),
        RemindMFAParameterDefinition(name="chemical_recycling_yield", dim_letters=(),
                                     description="Yield of chemical recycling",),
        # other
        RemindMFAParameterDefinition(name="material_shares_in_goods", dim_letters=("r", "m", "g"),
                                     description="Share of materials in goods",),
        RemindMFAParameterDefinition(name="emission_capture_rate", dim_letters=("h", "r"),
                                     description="Carbon capture rate for emissions of incinerated plastics",),
        RemindMFAParameterDefinition(name="carbon_content_materials", dim_letters=("e", "m"),
                                     description="Carbon content of materials",),
        # for in-use stock
        RemindMFAParameterDefinition(name="consumption", dim_letters=("h", "r", "g"),
                                     description="Historic plastic use by industries such as converters for the fabrication of plastic products",),
        RemindMFAParameterDefinition(name="sector_split", dim_letters=("g",),
                                     description="Global sector split of plastic use",),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("g",),
                                     description="Mean lifetime of goods",),
        RemindMFAParameterDefinition(name="lifetime_std", dim_letters=("g",),
                                     description="Standard deviation of lifetime",),
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r", "S"),
                                     description="Population",),
        RemindMFAParameterDefinition(name="gdppc", dim_letters=("t", "r", "S"),
                                     description="GDP per capita",),
    ]
    # fmt: on

    if historic:
        trades = [
            TradeDefinition(name="primary_his", dim_letters=("h", "r", "m")),
            TradeDefinition(name="final_his", dim_letters=("h", "r", "m", "g")),
        ]
    else:
        trades = [
            TradeDefinition(name="primary", dim_letters=("t", "r", "m")),
            TradeDefinition(name="final", dim_letters=("t", "r", "m", "g")),
            TradeDefinition(name="waste", dim_letters=("t", "e", "r", "m")),
        ]

    return RemindMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
        trades=trades,
    )


# fmt: off
scenario_parameters = [
    RemindMFAParameterDefinition(name="waste_his_imports", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="waste_his_imports_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="waste_his_exports", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="waste_his_exports_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="collection_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="collection_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="incineration_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="incineration_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="mechanical_recycling_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="mechanical_recycling_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="chemical_recycling_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="chemical_recycling_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="bio_production_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="bio_production_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="daccu_production_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="daccu_production_rate_year", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="emission_capture_rate", dim_letters=("r",),),
    RemindMFAParameterDefinition(name="emission_capture_rate_year", dim_letters=("r",),),
]
# fmt: on
