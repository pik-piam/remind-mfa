import flodym as fd

from remind_mfa.common.common_definition import (
    ExtrapolationDefinition,
    RemindMFADefinition,
    RemindMFAParameterDefinition,
    trade_parameters_read_from_data,
)
from remind_mfa.common.trade import TradeDefinition
from remind_mfa.steel.steel_config import SteelCfg


def get_steel_definition(cfg: SteelCfg, historical: bool) -> RemindMFADefinition:
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="End Use", dim_letter="u", dtype=str),
        fd.DimensionDefinition(name="EU-MFA_Good", dim_letter="f", dtype=str),
        fd.DimensionDefinition(name="EU-MFA_Time", dim_letter="v", dtype=int),
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
            "hibernating",
            "eol_management",
            "reuse",
            "eol_waste",
            "scrap_market",
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
            fd.FlowDefinition(from_process="use", to_process="hibernating", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="eol_management", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="eol_management", to_process="reuse", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="reuse", to_process="use", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="eol_management", to_process="scrap_market", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="eol_management", to_process="eol_waste", dim_letters=("t", "r", "u")),
            fd.FlowDefinition(from_process="scrap_market", to_process="scrap_pool", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="scrap_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="scrap_market", dim_letters=("t", "r")),
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
        stocks = [
            fd.StockDefinition(
                name="use",
                process="use",
                dim_letters=("t", "r", "u"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="hibernating",
                process="hibernating",
                dim_letters=("t", "r", "u"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="eol_waste",
                process="eol_waste",
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
            name="end_use_split_low_inco", dim_letters=("u",),
            description="End use shares in consumption for low gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="end_use_split_medium_inco", dim_letters=("u",),
            description="End use shares in consumption for medium gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="end_use_split_high_inco", dim_letters=("u",),
            description="End use shares in consumption for high gdp per capita"
        ),
        RemindMFAParameterDefinition(
            name="end_use_split_gdppc_low", dim_letters=(),
            description="Upper GDP per capita threshold for end_use_split_low_inco",
        ),
        RemindMFAParameterDefinition(
            name="end_use_split_gdppc_high", dim_letters=(),
            description="Lower GDP per capita threshold for end_use_split_high_inco",
        ),
        RemindMFAParameterDefinition(
            name="forming_loss_rate", dim_letters=(),
            description="Loss rate in forming process. Contrary to (1-forming_yield), this material is completely lost and not recycled as home scrap"
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
        # for TRANSIENCE: output parameters from other MIC3 models
        RemindMFAParameterDefinition(
            name="stock_inflow_EU-MFA", dim_letters=("v", "r", "f"),
            description="Stock inflow for EU28",
            scenario_folder="transience",
        ),
        RemindMFAParameterDefinition(
            name="collected_eol_EU-MFA", dim_letters=("v", "r", "f"),
            description="Collected EOL steel goods for EU28",
            scenario_folder="transience",
        ),
        RemindMFAParameterDefinition(
            name="lost_eol_EU-MFA", dim_letters=("v", "r", "f"),
            description="Lost EOL steel goods for EU28",
            scenario_folder="transience",
        ),
        RemindMFAParameterDefinition(
            name="available_scrap_EU-MFA", dim_letters=("v", "r"),
            description="Available scrap for EU28",
            scenario_folder="transience",
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
        parameters += trade_parameters_read_from_data(cfg, trades)

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
        name="max_scrap_share",
        dim_letters=("r",),
        description="Maximum share of scrap in the metallic input to steel production",
    ),
    ExtrapolationDefinition(
        name="reuse_share",
        dim_letters=("r", "u"),
        create_new=True,
    ),
]
