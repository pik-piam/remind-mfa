from typing import List
import flodym as fd

from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.helper import RemindMFAParameterDefinition, RemindMFADefinition
from remind_mfa.common.trade import TradeDefinition


class PlasticsMFADefinition(RemindMFADefinition):
    trades: List[TradeDefinition]


def get_definition(cfg: PlasticsCfg, historic: bool) -> PlasticsMFADefinition:

    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Element", dim_letter="e", dtype=str),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
    ]

    if historic:
        processes = [
            "sysenv",
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
            "processing",
            "fabrication",
            "primary_market",
            "intermediate_market",
            "waste_market",
            "good_market",
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

    if historic:
        flows = []
    else:
        # fmt: off
        # names are auto-generated, see Flow class documetation
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="virginfoss", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="virginbio", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="virgindaccu", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="virginccu", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="atmosphere", to_process="virginbio", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="atmosphere", to_process="virgindaccu", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="virginfoss", to_process="virgin", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="virginbio", to_process="virgin", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="virgindaccu", to_process="virgin", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="virginccu", to_process="virgin", dim_letters=("t","e","r","m")),
            # primary stages
            fd.FlowDefinition(from_process="virgin", to_process="processing", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="virgin", to_process="primary_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="primary_market", to_process="processing", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="primary_market", to_process="sysenv", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="primary_market", dim_letters=("t","e","r","m")),
            # processing stages
            fd.FlowDefinition(from_process="processing", to_process="fabrication", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="processing", to_process="intermediate_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="intermediate_market", to_process="fabrication", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="intermediate_market", to_process="sysenv", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="intermediate_market", dim_letters=("t","e","r","m")),
            # fabrication stages
            fd.FlowDefinition(from_process="fabrication", to_process="good_market", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="good_market", to_process="use", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="fabrication", to_process="use", dim_letters=("t","e","r","m","g")),
            fd.FlowDefinition(from_process="good_market", to_process="sysenv", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="good_market", dim_letters=("t","e","r","m")),
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
            fd.FlowDefinition(from_process="reclmech", to_process="processing", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclchem", to_process="virgin", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="uncontrolled", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="reclmech", to_process="incineration", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="incineration", to_process="emission", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="captured", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="emission", to_process="atmosphere", dim_letters=("t","e","r")),
            fd.FlowDefinition(from_process="captured", to_process="virginccu", dim_letters=("t","e","r")),

            fd.FlowDefinition(from_process="sysenv", to_process="good_market", dim_letters=("t","r")),

            # waste trade
            fd.FlowDefinition(from_process="waste_market", to_process="collected", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="collected", to_process="waste_market", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="waste_market", to_process="sysenv", dim_letters=("t","e","r","m")),
            fd.FlowDefinition(from_process="sysenv", to_process="waste_market", dim_letters=("t","e","r","m")),

        ]
        # fmt: on

    if historic:
        stocks = [
            fd.StockDefinition(
                name="in_use_historic",
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

    parameters = [
        # EOL rates
        RemindMFAParameterDefinition(
            name="collection_rate",
            dim_letters=("t", "r", "m"),
            description="Collection rate of plastic waste",
        ),
        RemindMFAParameterDefinition(
            name="mechanical_recycling_rate",
            dim_letters=("t", "r", "m"),
            description="Mechanical recycling rate of collected waste",
        ),
        RemindMFAParameterDefinition(
            name="chemical_recycling_rate",
            dim_letters=("t", "r", "m"),
            description="Chemical recycling rate of collected waste",
        ),
        RemindMFAParameterDefinition(
            name="incineration_rate",
            dim_letters=("t", "r", "m"),
            description="Incineration rate of collected waste",
        ),
        # trade
        RemindMFAParameterDefinition(
            name="primary_his_imports",
            dim_letters=("h", "r"),
            description="Historic primary plastics imports",
        ),
        RemindMFAParameterDefinition(
            name="primary_his_exports",
            dim_letters=("h", "r"),
            description="Historic primary plastics exports",
        ),
        RemindMFAParameterDefinition(
            name="intermediate_his_imports",
            dim_letters=("h", "r"),
            description="Historic intermediate plastics imports",
        ),
        RemindMFAParameterDefinition(
            name="intermediate_his_exports",
            dim_letters=("h", "r"),
            description="Historic intermediate plastics exports",
        ),
        RemindMFAParameterDefinition(
            name="manufactured_his_imports",
            dim_letters=("h", "r"),
            description="Historic manufactured plastics imports",
        ),
        RemindMFAParameterDefinition(
            name="manufactured_his_exports",
            dim_letters=("h", "r"),
            description="Historic manufactured plastics exports",
        ),
        RemindMFAParameterDefinition(
            name="final_his_imports",
            dim_letters=("h", "r"),
            description="Historic final goods imports",
        ),
        RemindMFAParameterDefinition(
            name="final_his_exports",
            dim_letters=("h", "r"),
            description="Historic final goods exports",
        ),
        RemindMFAParameterDefinition(
            name="waste_imports",
            dim_letters=("t", "r"),
            description="Plastic waste imports (historic and future assumption)",
        ),
        RemindMFAParameterDefinition(
            name="waste_exports",
            dim_letters=("t", "r"),
            description="Plastic waste exports (historic and future assumption)",
        ),
        # virgin production rates
        RemindMFAParameterDefinition(
            name="bio_production_rate",
            dim_letters=("t", "r", "m"),
            description="Share of bio-based plastics in virgin production",
        ),
        RemindMFAParameterDefinition(
            name="daccu_production_rate",
            dim_letters=("t", "r", "m"),
            description="Share of DACCU plastics in virgin production",
        ),
        # recycling losses
        RemindMFAParameterDefinition(
            name="mechanical_recycling_yield",
            dim_letters=("t", "r", "m"),
            description="Yield of mechanical recycling",
        ),
        RemindMFAParameterDefinition(
            name="reclmech_loss_uncontrolled_rate",
            dim_letters=("t", "r", "m"),
            description="Rate of mechanical recycling losses to uncontrolled disposal",
        ),
        # other
        RemindMFAParameterDefinition(
            name="material_shares_in_goods",
            dim_letters=("r", "m", "g"),
            description="Share of materials in goods",
        ),
        RemindMFAParameterDefinition(
            name="emission_capture_rate",
            dim_letters=("t",),
            description="Carbon capture rate from emissions",
        ),
        RemindMFAParameterDefinition(
            name="carbon_content_materials",
            dim_letters=("e", "m"),
            description="Carbon content of materials",
        ),
        # for in-use stock
        RemindMFAParameterDefinition(
            name="consumption", dim_letters=("h", "r", "g"), description="Historic production"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_mean", dim_letters=("g",), description="Mean lifetime of goods"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_std",
            dim_letters=("g",),
            description="Standard deviation of lifetime",
        ),
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r"), description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r"), description="GDP per capita"
        ),
    ]

    if historic:
        trades = [
            TradeDefinition(name="primary_his", dim_letters=("h", "r")),
            TradeDefinition(name="intermediate_his", dim_letters=("h", "r")),
            TradeDefinition(name="manufactured_his", dim_letters=("h", "r")),
            TradeDefinition(name="final_his", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="primary", dim_letters=("t", "r", "m", "e")),
            TradeDefinition(name="intermediate", dim_letters=("t", "r", "m", "e")),
            TradeDefinition(name="manufactured", dim_letters=("t", "r", "m", "e")),
            TradeDefinition(name="final", dim_letters=("t", "r", "m", "e", "g")),
            TradeDefinition(name="waste", dim_letters=("t", "r", "m", "e", "g")),
        ]

    return PlasticsMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
        trades=trades,
    )


scenario_parameters = []
