from typing import List
import flodym as fd

from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.steel.steel_config import SteelCfg
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition


def get_steel_definition(cfg: SteelCfg, historic: bool) -> RemindMFADefinition:
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
    ]

    if historic:
        processes = [
            "sysenv",
            "forming",
            "ip_market",
            "good_market",
            "fabrication",
            "use",
        ]
    else:
        processes = [
            "sysenv",
            "bof_production",
            "eaf_production",
            "forming",
            "ip_market",
            "fabrication",
            "good_market",
            "use",
            "obsolete",
            "eol_market",
            "recycling",
            "scrap_market",
            "excess_scrap",
            "imports",
            "exports",
            "losses",
            "extraction",
        ]

    # fmt: off
    if historic:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="forming", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="forming", to_process="ip_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="forming", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="ip_market", to_process="fabrication", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="ip_market", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="ip_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="fabrication", to_process="good_market", dim_letters=("h", "r", "g")),
            fd.FlowDefinition(from_process="fabrication", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="good_market", to_process="sysenv", dim_letters=("h", "r", "g")),
            fd.FlowDefinition(from_process="sysenv", to_process="good_market", dim_letters=("h", "r", "g")),
            fd.FlowDefinition(from_process="good_market", to_process="use", dim_letters=("h", "r", "g")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "g")),
        ]
    else:
        flows = [
            fd.FlowDefinition(from_process="extraction", to_process="bof_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="scrap_market", to_process="bof_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="bof_production", to_process="forming", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="bof_production", to_process="losses", dim_letters=("t", "r",)),
            fd.FlowDefinition(from_process="scrap_market", to_process="eaf_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="eaf_production", to_process="forming", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="eaf_production", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="ip_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="scrap_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="fabrication", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="ip_market", to_process="fabrication", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="ip_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="ip_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="fabrication", to_process="good_market", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="fabrication", to_process="scrap_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="good_market", to_process="exports", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="imports", to_process="good_market", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="good_market", to_process="use", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="use", to_process="obsolete", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="use", to_process="eol_market", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="eol_market", to_process="recycling", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="eol_market", to_process="exports", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="imports", to_process="eol_market", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="recycling", to_process="scrap_market", dim_letters=("t", "r", "g")),
            fd.FlowDefinition(from_process="scrap_market", to_process="excess_scrap", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="losses", to_process="sysenv", dim_letters=("t", "r",)),
            fd.FlowDefinition(from_process="sysenv", to_process="extraction", dim_letters=("t", "r")),
        ]
    # fmt: on

    if historic:
        stocks = [
            fd.StockDefinition(
                name="historic_in_use",
                process="use",
                dim_letters=("h", "r", "g"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
                time_letter="h",
            ),
        ]
    else:
        use_stock_class = fd.StockDrivenDSM
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("t", "r", "g"),
                subclass=use_stock_class,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="obsolete",
                process="obsolete",
                dim_letters=("t", "r", "g"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="excess_scrap",
                process="excess_scrap",
                dim_letters=("t", "r"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
        ]

    # fmt: off
    parameters = [
        RemindMFAParameterDefinition(
            name="forming_yield", dim_letters=(),
            description="Yield of steel forming process"
        ),
        RemindMFAParameterDefinition(
            name="fabrication_yield", dim_letters=("g",),
            description="Yield during fabrication of steel-containing final goods"
        ),
        RemindMFAParameterDefinition(
            name="recovery_rate", dim_letters=("g",),
            description="Combined collection and recovery rate at end-of-life - share of all end-of life material that is recycled"
        ),
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r"),
            description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r"),
            description="GDP per capita"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_mean", dim_letters=("g",),
            description="Mean lifetime of goods"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_std", dim_letters=("g",),
            description="Absolute standard deviation of good lifetime",
        ),
        RemindMFAParameterDefinition(
            name="sector_split_low", dim_letters=("g",),
            description="Final good category shares in consumption for low gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="sector_split_medium", dim_letters=("g",),
            description="Final good category shares in consumption for medium gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="sector_split_high", dim_letters=("g",),
            description="Final good category shares in consumption for high gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="secsplit_gdppc_low", dim_letters=(),
            description="Upper GDP per capita threshold for sector_split_low",
        ),
        RemindMFAParameterDefinition(
            name="secsplit_gdppc_high", dim_letters=(),
            description="Lower GDP per capita threshold for sector_split_high",
        ),
        RemindMFAParameterDefinition(
            name="scrap_in_bof_rate", dim_letters=(),
            description="Share of scrap-based steel from BF-BOF production"
        ),
        RemindMFAParameterDefinition(
            name="forming_loss_rate", dim_letters=(),
            description="Loss rate in forming process. Contrary to (1-forming_yield), this material is completely lost and not recycled as home scrap"
        ),
        RemindMFAParameterDefinition(
            name="fabrication_losses", dim_letters=(),
            description="Loss rate during fabrication of final goods. Contrary to (1-fabrication_yield), this material is completely lost and not recycled as new scrap",
        ),
        RemindMFAParameterDefinition(
            name="production_loss_rate", dim_letters=(),
            description="Yield of raw steel production, accounting for losses in BF-BOF and (DRI-)EAF processes",
        ),
        RemindMFAParameterDefinition(
            name="saturation_level_factor", dim_letters=("r",),
            description="Regional multiplicative adjustment factor for the saturation level of the in-use steel stock based on expert judgement",
        ),
        RemindMFAParameterDefinition(
            name="stock_growth_speed_factor", dim_letters=("r",),
            description="Regional adjustment factor for the growth speed of the in-use steel stock based on expert judgement",
        ),
        RemindMFAParameterDefinition(
            name="scrap_consumption", dim_letters=("h", "r"),
            description="Historic scrap consumption",
        ),
        # RemindMFAParameterDefinition(
        #     name="scrap_consumption_no_assumptions", dim_letters=("h", "r"),
        #     description="Historic scrap consumption",
        # ),
        # WSA
        RemindMFAParameterDefinition(
            name="production", dim_letters=("h", "r"),
            description="Historic steel production",
        ),
        RemindMFAParameterDefinition(
            name="steel_imports", dim_letters=("h", "r"),
            description="Historic steel imports",
        ),
        RemindMFAParameterDefinition(
            name="steel_exports", dim_letters=("h", "r"),
            description="Historic steel exports",
        ),
        RemindMFAParameterDefinition(
            name="indirect_imports", dim_letters=("h", "r", "g"),
            description="Historic indirect trade imports, i.e. contained in final goods",
        ),
        RemindMFAParameterDefinition(
            name="indirect_exports", dim_letters=("h", "r", "g"),
            description="Historic indirect trade exports, i.e. contained in final goods",
        ),
        RemindMFAParameterDefinition(
            name="scrap_imports", dim_letters=("h", "r"),
            description="Historic combined eol product and scrap imports"
        ),
        RemindMFAParameterDefinition(
            name="scrap_exports", dim_letters=("h", "r"),
            description="Historic combined eol product and scrap exports"
        ),
    ]
    # fmt: on

    if historic:
        trades = [
            TradeDefinition(name="steel", dim_letters=("h", "r")),
            TradeDefinition(name="indirect", dim_letters=("h", "r", "g")),
            TradeDefinition(name="scrap", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="steel", dim_letters=("t", "r")),
            TradeDefinition(name="indirect", dim_letters=("t", "r", "g")),
            TradeDefinition(name="scrap", dim_letters=("t", "r", "g")),
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
    RemindMFAParameterDefinition(
        name="saturation_level_factor",
        dim_letters=("r",),
    ),
]
