import flodym as fd

from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.steel.steel_config import SteelCfg
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.trade import TradeDefinition


def get_steel_definition(cfg: SteelCfg, historical: bool) -> RemindMFADefinition:
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="End Use", dim_letter="u", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
    ]

    if historical:
        processes = [
            "sysenv",
            "forming",
            "steel_market",
            "manufactured_products_market",
            "manufacturing",
            "use",
        ]
    else:
        processes = [
            "sysenv",
            "steel_production_ore_based",
            "steel_production_scrap_based",
            "forming",
            "steel_market",
            "manufacturing",
            "manufactured_products_market",
            "use",
            "obsolete",
            "scrap_market",
            "recycling",
            "scrap_pool",
            "excess_scrap",
            "imports",
            "exports",
            "losses",
            "extraction",
        ]

    # fmt: off
    if historical:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="forming", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="forming", to_process="steel_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="forming", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="steel_market", to_process="manufacturing", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="steel_market", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="steel_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="manufacturing", to_process="manufactured_products_market", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="manufacturing", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="sysenv", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="sysenv", to_process="manufactured_products_market", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="use", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "u")),
        ]
    else:
        flows = [
            fd.FlowDefinition(from_process="extraction", to_process="steel_production_ore_based", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_production_ore_based", to_process="forming", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_production_ore_based", to_process="losses", dim_letters=("t", "r",)),
            fd.FlowDefinition(from_process="scrap_pool", to_process="steel_production_scrap_based", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_production_scrap_based", to_process="forming", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_production_scrap_based", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="steel_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="scrap_pool", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="forming", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="manufacturing", to_process="losses", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_market", to_process="manufacturing", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="steel_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="steel_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="manufacturing", to_process="manufactured_products_market", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="manufacturing", to_process="scrap_pool", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="exports", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="imports", to_process="manufactured_products_market", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="manufactured_products_market", to_process="use", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="obsolete", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="scrap_market", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="scrap_market", to_process="recycling", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="scrap_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="scrap_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="recycling", to_process="scrap_pool", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="scrap_pool", to_process="excess_scrap", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="losses", to_process="sysenv", dim_letters=("t", "r",)),
            fd.FlowDefinition(from_process="sysenv", to_process="extraction", dim_letters=("t", "r")),
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
        use_stock_class = fd.StockDrivenDSM
        stocks = [
            fd.StockDefinition(
                name="use",
                process="use",
                dim_letters=("t", "r", "u"),
                subclass=use_stock_class,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="obsolete",
                process="obsolete",
                dim_letters=("t", "r", "u"),
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
            name="manufacturing_yield", dim_letters=("u",),
            description="Yield during manufacturing of steel-containing final products"
        ),
        RemindMFAParameterDefinition(
            name="recovery_rate", dim_letters=("u",),
            description="Combined collection and recovery rate at end-of-life - share of all end-of life material that is recycled"
        ),
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r", "S"),
            description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r", "S"),
            description="GDP per capita"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_mean", dim_letters=("u",),
            description="Mean lifetime of Products"
        ),
        RemindMFAParameterDefinition(
            name="lifetime_std", dim_letters=("u",),
            description="Absolute standard deviation of final product lifetime",
        ),
        RemindMFAParameterDefinition(
            name="sector_split_low", dim_letters=("u",),
            description="End use shares in consumption for low gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="sector_split_medium", dim_letters=("u",),
            description="End use shares in consumption for medium gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="sector_split_high", dim_letters=("u",),
            description="End use shares in consumption for high gdp per capita"
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
            name="forming_loss_rate", dim_letters=(),
            description="Loss rate in forming process. Contrary to (1-forming_yield), this material is completely lost and not recycled as home scrap"
        ),
        RemindMFAParameterDefinition(
            name="manufacturing_losses", dim_letters=(),
            description="Loss rate during manufacturing of final products. Contrary to (1-manufacturing_yield), this material is completely lost and not recycled as new scrap",
        ),
        RemindMFAParameterDefinition(
            name="steel_production_loss_rate", dim_letters=(),
            description="Loss rate of iron and raw steel production in BF-BOF and (DRI-)EAF processes",
        ),
        RemindMFAParameterDefinition(
            name="scrap_consumption", dim_letters=("h", "r"),
            description="Historical scrap consumption",
        ),
        RemindMFAParameterDefinition(
            name="scrap_consumption_no_assumptions", dim_letters=("h", "r"),
            description="Historical scrap consumption",
        ),
        # WSA
        RemindMFAParameterDefinition(
            name="steel_production", dim_letters=("h", "r"),
            description="Historical steel production",
        ),
        RemindMFAParameterDefinition(
            name="steel_imports", dim_letters=("h", "r"),
            description="Historical steel imports",
        ),
        RemindMFAParameterDefinition(
            name="steel_exports", dim_letters=("h", "r"),
            description="Historical steel exports",
        ),
        RemindMFAParameterDefinition(
            name="manufactured_products_imports", dim_letters=("h", "r", "u"),
            description="Historical imports of steel contained in manufactured products",
        ),
        RemindMFAParameterDefinition(
            name="manufactured_products_exports", dim_letters=("h", "r", "u"),
            description="Historical exports of steel contained in manufactured products",
        ),
        RemindMFAParameterDefinition(
            name="scrap_imports", dim_letters=("h", "r"),
            description="Historical combined eol product and scrap imports"
        ),
        RemindMFAParameterDefinition(
            name="scrap_exports", dim_letters=("h", "r"),
            description="Historical combined eol product and scrap exports"
        ),
    ]
    # fmt: on

    if historical:
        trades = [
            TradeDefinition(name="steel", dim_letters=("h", "r")),
            TradeDefinition(name="manufactured_products", dim_letters=("h", "r", "u")),
            TradeDefinition(name="scrap", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="steel", dim_letters=("t", "r")),
            TradeDefinition(name="manufactured_products", dim_letters=("t", "r", "u")),
            TradeDefinition(name="scrap", dim_letters=("t", "r")),
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
