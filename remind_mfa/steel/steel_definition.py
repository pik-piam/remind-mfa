from typing import List
import flodym as fd

from remind_mfa.steel.steel_config import SteelCfg
from remind_mfa.common.helper import RemindMFAParameterDefinition, RemindMFADefinition
from remind_mfa.common.trade import TradeDefinition


class SteelMFADefinition(RemindMFADefinition):
    trades: List[TradeDefinition]


def get_definition(cfg: SteelCfg, historic: bool) -> SteelMFADefinition:
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Intermediate", dim_letter="i", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
        fd.DimensionDefinition(name="Scenario", dim_letter="s", dtype=str),
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

    parameters = [
        RemindMFAParameterDefinition(
            name="forming_yield", dim_letters=(), description="Yield of forming process"
        ),
        RemindMFAParameterDefinition(
            name="fabrication_yield", dim_letters=("g",), description="Yield of fabrication process"
        ),
        RemindMFAParameterDefinition(
            name="recovery_rate", dim_letters=("g",), description="Recovery rate at end-of-life"
        ),
        RemindMFAParameterDefinition(
            name="good_to_intermediate_distribution",
            dim_letters=("g", "i"),
            description="Distribution of goods to intermediate products",
        ),
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r"), description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r"), description="GDP per capita"
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
            name="sector_split_low", dim_letters=("g",), description="Sector split for low income"
        ),
        RemindMFAParameterDefinition(
            name="sector_split_medium",
            dim_letters=("g",),
            description="Sector split for medium income",
        ),
        RemindMFAParameterDefinition(
            name="sector_split_high", dim_letters=("g",), description="Sector split for high income"
        ),
        RemindMFAParameterDefinition(
            name="secsplit_gdppc_low",
            dim_letters=(),
            description="GDP per capita threshold for low income",
        ),
        RemindMFAParameterDefinition(
            name="secsplit_gdppc_high",
            dim_letters=(),
            description="GDP per capita threshold for high income",
        ),
        RemindMFAParameterDefinition(
            name="max_scrap_share",
            dim_letters=(),
            description="Maximum scrap share in base model",
        ),
        RemindMFAParameterDefinition(
            name="scrap_in_bof_rate", dim_letters=(), description="Scrap share in BOF production"
        ),
        RemindMFAParameterDefinition(
            name="forming_loss_rate", dim_letters=(), description="Loss rate in forming process"
        ),
        RemindMFAParameterDefinition(
            name="fabrication_losses",
            dim_letters=(),
            description="Loss rate in fabrication process",
        ),
        RemindMFAParameterDefinition(
            name="production_yield", dim_letters=(), description="Overall production yield"
        ),
        RemindMFAParameterDefinition(
            name="saturation_level_factor",
            dim_letters=("r",),
            description="Regional saturation level adjustment factor",
        ),
        RemindMFAParameterDefinition(
            name="stock_growth_speed_factor",
            dim_letters=("r",),
            description="Regional stock growth speed adjustment factor",
        ),
        RemindMFAParameterDefinition(
            name="scrap_consumption",
            dim_letters=("h", "r"),
            description="Historic scrap consumption",
        ),
        # WSA
        RemindMFAParameterDefinition(
            name="production_by_intermediate",
            dim_letters=("h", "r", "i"),
            description="Historic production by intermediate product",
        ),
        RemindMFAParameterDefinition(
            name="intermediate_imports",
            dim_letters=("h", "r", "i"),
            description="Historic intermediate product imports",
        ),
        RemindMFAParameterDefinition(
            name="intermediate_exports",
            dim_letters=("h", "r", "i"),
            description="Historic intermediate product exports",
        ),
        RemindMFAParameterDefinition(
            name="indirect_imports",
            dim_letters=("h", "r", "g"),
            description="Historic indirect trade imports",
        ),
        RemindMFAParameterDefinition(
            name="indirect_exports",
            dim_letters=("h", "r", "g"),
            description="Historic indirect trade exports",
        ),
        RemindMFAParameterDefinition(
            name="scrap_imports", dim_letters=("h", "r"), description="Historic scrap imports"
        ),
        RemindMFAParameterDefinition(
            name="scrap_exports", dim_letters=("h", "r"), description="Historic scrap exports"
        ),
    ]

    if historic:
        trades = [
            TradeDefinition(name="intermediate", dim_letters=("h", "r")),
            TradeDefinition(name="indirect", dim_letters=("h", "r", "g")),
            TradeDefinition(name="scrap", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="intermediate", dim_letters=("t", "r")),
            TradeDefinition(name="indirect", dim_letters=("t", "r", "g")),
            TradeDefinition(name="scrap", dim_letters=("t", "r", "g")),
        ]

    return SteelMFADefinition(
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
