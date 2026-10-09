import flodym as fd

from remind_mfa.common.common_definition import ExtrapolationDefinition, RemindMFADefinition
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition


def get_plastics_definition(cfg: PlasticsCfg, historical: bool) -> RemindMFADefinition:

    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Element", dim_letter="e", dtype=str),
        fd.DimensionDefinition(name="Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Type", dim_letter="p", dtype=str),
        fd.DimensionDefinition(name="End Use", dim_letter="u", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
    ]

    if historical:
        processes = [
            "sysenv",
            "polymerization",
            "primary_market",
            "manufacturing",
            "manufactured_products_market",
            "use",
        ]
    else:
        processes = [
            "sysenv",
            "feedfoss",
            "feedbio",
            "feeddaccu",
            "feedccu",
            "HVC_input",
            "C4_input",
            "polymerization",
            "primary_market",
            "manufacturing",
            "manufactured_products_market",
            "use",
            "eol",
            "waste_market",
            "reclmech",
            "reclchem",
            "incineration",
            "landfill",
            "collected",
            "mismanaged",
            "uncontrolled",
            "emission",
            "captured",
            "atmosphere",
            "other_reactants",
            "losses",
            "aux_recyclate",
            "aux_recl_feedstock",
            "imports",
            "exports",
        ]

    # fmt: off
    if historical:
        # names are auto-generated, see Flow class documentation
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="polymerization", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="polymerization", to_process="primary_market", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="primary_market", to_process="manufacturing", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="primary_market", to_process="sysenv", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="sysenv", to_process="primary_market", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="manufacturing", to_process="manufactured_products_market", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="use", dim_letters=("h", "r", "p", "m", "u")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="sysenv", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="sysenv", to_process="manufactured_products_market", dim_letters=("h", "r", "p")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "u")),
        ]
    else:
        flows = [
            # sysenv
            fd.FlowDefinition(from_process="sysenv", to_process="feedfoss", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="feedccu", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="C4_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="sysenv", to_process="other_reactants", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="losses", to_process="sysenv", dim_letters=("t","e","r")),
            # monomer stages
            fd.FlowDefinition(from_process="atmosphere", to_process="feedbio", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="atmosphere", to_process="feeddaccu", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="feedfoss", to_process="HVC_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="feedbio", to_process="HVC_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="feeddaccu", to_process="HVC_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="feedccu", to_process="HVC_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="HVC_input", to_process="polymerization", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="C4_input", to_process="polymerization", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="other_reactants", to_process="polymerization", dim_letters=("t","e","r")),
            # primary stages
            fd.FlowDefinition(from_process="polymerization", to_process="primary_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="polymerization", to_process="losses", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="primary_market", to_process="manufacturing", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="primary_market", to_process="exports", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="imports", to_process="primary_market", dim_letters=("t","e","r","m")),
            # manufacturing stages
            fd.FlowDefinition(from_process="manufacturing", to_process="manufactured_products_market", dim_letters=("t","e","r","m","u")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="use", dim_letters=("t","e","r","m","u")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="exports", dim_letters=("t","e","r","m","u")),
            fd.FlowDefinition(from_process="imports", to_process="manufactured_products_market", dim_letters=("t","e","r","m","u")),
            # use stage
            fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("t","e","r","m","u")),
            # end-of-life stages
            fd.FlowDefinition(from_process="eol", to_process="collected", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="eol", to_process="mismanaged", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="reclmech", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="reclchem", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="landfill", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="incineration", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="mismanaged", to_process="uncontrolled", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="aux_recyclate", dim_letters=("t","e","r", "m")),
            fd.FlowDefinition(from_process="aux_recyclate", to_process="primary_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclchem", to_process="aux_recl_feedstock", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="aux_recl_feedstock", to_process="HVC_input", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="reclchem", to_process="emission", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="reclmech", to_process="uncontrolled", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="incineration", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="incineration", to_process="emission", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="captured", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="atmosphere", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="captured", to_process="feedccu", dim_letters=("t","e","r")),
            # waste trade
            fd.FlowDefinition(from_process="waste_market", to_process="collected", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="waste_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="waste_market", to_process="exports", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="imports", to_process="waste_market", dim_letters=("t","e","r","m")),
            # recyclate trade (redistributes mechanical-recycling surplus between regions)
            fd.FlowDefinition(from_process="aux_recyclate", to_process="exports", dim_letters=("t","e","r", "m")),
            fd.FlowDefinition(from_process="imports", to_process="aux_recyclate", dim_letters=("t","e","r","m")),
            # recycled-feedstock trade (redistributes chemical-recycling surplus between regions)
            fd.FlowDefinition(from_process="aux_recl_feedstock", to_process="exports", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="imports", to_process="aux_recl_feedstock", dim_letters=("t","e","r")),

        ]
    # fmt: on

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
                name="use_dsm",
                dim_letters=("t", "r", "u"),
                subclass=fd.StockDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="use",
                process="use",
                dim_letters=("t", "e", "r", "m", "u"),
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
        RemindMFAParameterDefinition(name="chemical_recycling_rate", dim_letters=(),
                                     description="Chemical recycling rate of collected waste",),
        RemindMFAParameterDefinition(name="incineration_rate", dim_letters=("h", "r"),
                                     description="Incineration rate of collected waste",),
        # trade
        RemindMFAParameterDefinition(name="primary_imports", dim_letters=("h", "r", "p", "m"),
                                     description="Historical primary plastics imports",),
        RemindMFAParameterDefinition(name="primary_exports", dim_letters=("h", "r", "p", "m"),
                                     description="Historical primary plastics exports",),
        RemindMFAParameterDefinition(name="manufactured_products_imports", dim_letters=("h", "r", "p", "m", "u"),
                                     description="Historical manufactured products imports",),
        RemindMFAParameterDefinition(name="manufactured_products_exports", dim_letters=("h", "r", "p", "m", "u"),
                                     description="Historical manufactured products exports",),
        RemindMFAParameterDefinition(name="waste_imports", dim_letters=("h", "r", "p", "m"),
                                     description="Historical plastic waste imports",),
        RemindMFAParameterDefinition(name="waste_exports", dim_letters=("h", "r", "p", "m"),
                                     description="Historical plastic waste exports",),
        # renewable production rates
        RemindMFAParameterDefinition(name="bio_production_rate", dim_letters=(),
                                     description="Share of bio-based HVC production",),
        RemindMFAParameterDefinition(name="daccu_production_rate", dim_letters=(),
                                     description="Share of DACCU HVC production",),
        # HVC input
        RemindMFAParameterDefinition(name="HVC_input_ratio", dim_letters=("m", "e"),
                                     description="Ratio of HVC inputs to polymerization",),
        RemindMFAParameterDefinition(name="C4_input_ratio", dim_letters=("m", "e"),
                                     description="Ratio of C4 inputs to polymerization",),
        RemindMFAParameterDefinition(name="polymerization_yield", dim_letters=("m",),
                                     description="Polymerization yield",),
        # recycling losses
        RemindMFAParameterDefinition(name="mechanical_recycling_yield", dim_letters=(),
                                     description="Yield of mechanical recycling",),
        RemindMFAParameterDefinition(name="reclmech_loss_uncontrolled_rate", dim_letters=(),
                                     description="Rate of mechanical recycling losses to uncontrolled disposal",),
        RemindMFAParameterDefinition(name="chemical_recycling_yield", dim_letters=(),
                                     description="Yield of chemical recycling",),
        # other
        RemindMFAParameterDefinition(name="emission_capture_rate", dim_letters=(),
                                     description="Carbon capture rate for emissions of incinerated plastics",),
        RemindMFAParameterDefinition(name="carbon_content_materials", dim_letters=("e", "m"),
                                     description="Carbon content of materials",),
        # for in-use stock
        RemindMFAParameterDefinition(name="production", dim_letters=("h", "r", "p"),
                                     description="Historical plastic production, differentiated by polymer type (Fibre/Rubber/Plastics)",),
        RemindMFAParameterDefinition(name="sector_polymer_split", dim_letters=("h", "r", "p", "m", "u"),
                                     description="Share of each polymer and end-use sector within total Fibre/Rubber/Plastics apparent consumption per region",),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("u",),
                                     description="Mean lifetime of final products",),
        RemindMFAParameterDefinition(name="lifetime_std", dim_letters=("u",),
                                     description="Standard deviation of lifetime",),
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r", "S"),
                                     description="Population",),
        RemindMFAParameterDefinition(name="gdppc", dim_letters=("t", "r", "S"),
                                     description="GDP per capita",),
    ]
    # fmt: on

    if historical:
        trades = [
            TradeDefinition(name="primary", dim_letters=("h", "r", "p", "m")),
            TradeDefinition(name="manufactured_products", dim_letters=("h", "r", "p", "m", "u")),
        ]
    else:
        trades = [
            TradeDefinition(name="primary", dim_letters=("t", "r", "m")),
            TradeDefinition(name="manufactured_products", dim_letters=("t", "r", "m", "u")),
            TradeDefinition(name="waste", dim_letters=("t", "e", "r", "m")),
            TradeDefinition(name="aux_recyclate", dim_letters=("t", "e", "r", "m")),
            TradeDefinition(name="aux_recl_feedstock", dim_letters=("t", "e", "r")),
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
    ExtrapolationDefinition(name="waste_imports", dim_letters=("r",)),
    ExtrapolationDefinition(name="waste_exports", dim_letters=("r",)),
    ExtrapolationDefinition(name="collection_rate", dim_letters=("r",), blending_function="converge_quadratic"),
    ExtrapolationDefinition(name="landfill_rate", dim_letters=("r",), blending_function="converge_quadratic"),
    ExtrapolationDefinition(name="mechanical_recycling_rate", dim_letters=("r",), blending_function="converge_quadratic"),
    ExtrapolationDefinition(name="chemical_recycling_rate", dim_letters=("r",), blending_function="hermite"),
    ExtrapolationDefinition(name="bio_production_rate", dim_letters=("r",), blending_function="hermite"),
    ExtrapolationDefinition(name="daccu_production_rate", dim_letters=("r",), blending_function="hermite"),
    ExtrapolationDefinition(name="emission_capture_rate", dim_letters=("r",)),
    ExtrapolationDefinition(name="material_shares_use_inflow"),
]
# fmt: on
