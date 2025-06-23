from typing import List
import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.trade import TradeDefinition


class SteelMFADefinition(fd.MFADefinition):
    trades: List[TradeDefinition]


def get_definition(cfg: GeneralCfg, historic: bool, stock_driven: bool) -> SteelMFADefinition:
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Intermediate", dim_letter="i", dtype=str),
        fd.DimensionDefinition(name="Good", dim_letter="g", dtype=str),
        fd.DimensionDefinition(name="Scenario", dim_letter="s", dtype=str),
    ]
    if historic or stock_driven:
        dimensions += [
            fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
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
        if stock_driven:
            raise ValueError("Historic MFASystem must be inflow driven")
        stocks = [
            fd.StockDefinition(
                name="historic_in_use",
                process="use",
                dim_letters=("h", "r", "g"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.customization.lifetime_model,
                time_letter="h",
            ),
        ]
    else:
        use_stock_class = fd.StockDrivenDSM if stock_driven else fd.InflowDrivenDSM
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("t", "r", "g"),
                subclass=use_stock_class,
                lifetime_model_class=cfg.customization.lifetime_model,
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
        fd.ParameterDefinition(name="forming_yield", dim_letters=("i",)),
        fd.ParameterDefinition(name="fabrication_yield", dim_letters=("g",)),
        fd.ParameterDefinition(name="recovery_rate", dim_letters=("g",)),
        fd.ParameterDefinition(name="good_to_intermediate_distribution", dim_letters=("g", "i")),
        fd.ParameterDefinition(name="population", dim_letters=("t", "r")),
        fd.ParameterDefinition(name="gdppc", dim_letters=("t", "r")),
        fd.ParameterDefinition(name="lifetime_mean", dim_letters=("r", "g")),
        fd.ParameterDefinition(name="lifetime_std", dim_letters=("r", "g")),
        fd.ParameterDefinition(name="sector_split_low", dim_letters=("g",)),
        fd.ParameterDefinition(name="sector_split_medium", dim_letters=("g",)),
        fd.ParameterDefinition(name="sector_split_high", dim_letters=("g",)),
        fd.ParameterDefinition(name="secsplit_gdppc_low", dim_letters=()),
        fd.ParameterDefinition(name="secsplit_gdppc_high", dim_letters=()),
        fd.ParameterDefinition(name="max_scrap_share_base_model", dim_letters=()),
        fd.ParameterDefinition(name="scrap_in_bof_rate", dim_letters=()),
        fd.ParameterDefinition(name="forming_losses", dim_letters=()),
        fd.ParameterDefinition(name="fabrication_losses", dim_letters=()),
        fd.ParameterDefinition(name="production_yield", dim_letters=()),
        fd.ParameterDefinition(name="saturation_level_factor", dim_letters=("r",)),
        fd.ParameterDefinition(name="stock_growth_speed_factor", dim_letters=("r",)),
    ]
    if historic or stock_driven:
        parameters += [
            fd.ParameterDefinition(name="scrap_consumption", dim_letters=("h", "r")),
            # WSA
            fd.ParameterDefinition(name="production_by_intermediate", dim_letters=("h", "r", "i")),
            fd.ParameterDefinition(name="intermediate_imports", dim_letters=("h", "r", "i")),
            fd.ParameterDefinition(name="intermediate_exports", dim_letters=("h", "r", "i")),
            fd.ParameterDefinition(name="indirect_imports", dim_letters=("h", "r", "g")),
            fd.ParameterDefinition(name="indirect_exports", dim_letters=("h", "r", "g")),
            fd.ParameterDefinition(name="scrap_imports", dim_letters=("h", "r")),
            fd.ParameterDefinition(name="scrap_exports", dim_letters=("h", "r")),
        ]
    else:
        parameters += [
            fd.ParameterDefinition(name="in_use_inflow", dim_letters=("t", "r", "g")),
            fd.ParameterDefinition(name="intermediate_imports", dim_letters=("t", "r")),
            fd.ParameterDefinition(name="intermediate_exports", dim_letters=("t", "r")),
            fd.ParameterDefinition(name="indirect_imports", dim_letters=("t", "r", "g")),
            fd.ParameterDefinition(name="indirect_exports", dim_letters=("t", "r", "g")),
            fd.ParameterDefinition(name="scrap_imports", dim_letters=("t", "r", "g")),
            fd.ParameterDefinition(name="scrap_exports", dim_letters=("t", "r", "g")),
            fd.ParameterDefinition(name="fixed_in_use_outflow", dim_letters=("t", "r", "g")),
        ]

    # currently unused
    # fd.ParameterDefinition(name="external_copper_rate", dim_letters=("g",)),
    # fd.ParameterDefinition(name="cu_tolerances", dim_letters=("i",)),
    # fd.ParameterDefinition(name="production", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="pigiron_production", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="pigiron_imports", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="pigiron_exports", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="pigiron_to_cast", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="dri_production", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="dri_imports", dim_letters=("h", "r")),
    # fd.ParameterDefinition(name="dri_exports", dim_letters=("h", "r")),

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
