import flodym as fd

from remind_mfa.cement.cement_bottom_up_definition import get_bottom_up_data_definition
from remind_mfa.cement.cement_bottom_up_definition import get_bottom_up_system_definition
from remind_mfa.cement.cement_carbon_uptake_model import get_carbonation_definition
from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.common_definition import ExtrapolationDefinition
from remind_mfa.common.common_definition import PlainDataPointDefinition
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.common_definition import RemindMFAPartialDefinition
from remind_mfa.common.trade import TradeDefinition

# fmt: off

def get_cement_definition(
    cfg: CementCfg, historical: bool, bottom_up: bool = False
) -> RemindMFADefinition:
    """Build the cement MFA definition from the core definition and the active modules.

    The bottom-up module (dimensions and parameters) is active if parameter reconciliation is
    switched on, the carbonation module (future MFA only) if carbonation is switched on.

    Args:
        cfg: Cement model configuration.
        historical: Whether to build the historical or the future MFA definition.
        bottom_up: Whether to build the combined (bottom-up) future MFA definition, which runs at
            the extended end-use resolution and contains the bottom-up stocks.
    """

    if historical and bottom_up:
        raise ValueError(
            "Historical Bottom-up not implemented. Please set historical=False or bottom_up=False."
        )
    bottom_up_active = bottom_up or cfg.model_switches.parameter_reconciliation
    carbonation_active = not historical and cfg.model_switches.carbonation

    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="End Use", dim_letter="u", dtype=str),
        fd.DimensionDefinition(name="Construction Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Construction Material Constituent", dim_letter="k", dtype=str),
        fd.DimensionDefinition(name="Driver Scenario", dim_letter="S", dtype=str),
    ]

    # 2) Processes
    if historical:
        processes = [
            "sysenv",
            "cement_production",
            "cement_market",
            "construction",
            "use",
            "imports",
            "exports",
        ]
    else:
        processes = [
            "sysenv",
            "clinker_production",
            "clinker_market",
            "cement_production",
            "cement_market",
            "construction",
            "use",
            "hibernating",
            "eol_management",
            "eol_waste",
            "reuse",
            "imports",
            "exports",
        ]

    # 3) Flows
    if historical:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="cement_production", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_production", to_process="cement_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="exports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="imports", to_process="cement_market", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="sysenv", dim_letters=("h", "r")),
            fd.FlowDefinition(from_process="cement_market", to_process="construction", dim_letters=("h", "r", "u", "m")),
            fd.FlowDefinition(from_process="sysenv", to_process="construction", dim_letters=("h", "r", "u", "m")),
            fd.FlowDefinition(from_process="construction", to_process="use", dim_letters=("h", "r", "u")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "u")),
        ]
    else:
        # the combined (bottom-up) MFA runs at the extended end-use resolution and keeps
        # the structure resolution through to the final flows and stocks
        end_use_letter = "e" if bottom_up else "u"
        full_flow_letters = ("t", "r", end_use_letter, "m")
        if bottom_up:
            full_flow_letters += ("s",)
        flows = [
            # clinker production
            fd.FlowDefinition(from_process="sysenv", to_process="clinker_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="clinker_production", to_process="clinker_market", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="clinker_production", to_process="sysenv", dim_letters=("t", "r")),
            # clinker trade
            fd.FlowDefinition(from_process="clinker_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="clinker_market", dim_letters=("t", "r")),
            # cement production
            fd.FlowDefinition(from_process="clinker_market", to_process="cement_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="cement_production", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="cement_production", to_process="cement_market", dim_letters=("t", "r")),
            # cement trade
            fd.FlowDefinition(from_process="cement_market", to_process="exports", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="imports", to_process="cement_market", dim_letters=("t", "r")),
            # cement losses during construction
            fd.FlowDefinition(from_process="cement_market", to_process="sysenv", dim_letters=("t", "r")),
            # construction
            fd.FlowDefinition(from_process="cement_market", to_process="construction", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="sysenv", to_process="construction", dim_letters=full_flow_letters),
            fd.FlowDefinition(from_process="construction", to_process="use", dim_letters=full_flow_letters + ("k",)),
            # hibernation: part of the in-use outflow remains in place, without outflow
            fd.FlowDefinition(from_process="use", to_process="hibernating", dim_letters=full_flow_letters + ("k",)),
            # end-of-life management: the demolished in-use outflow (non-hibernating)
            fd.FlowDefinition(from_process="use", to_process="eol_management", dim_letters=full_flow_letters + ("k",)),
            # reuse: part of the demolished material re-enters the in-use stock
            fd.FlowDefinition(from_process="eol_management", to_process="reuse", dim_letters=full_flow_letters + ("k",)),
            fd.FlowDefinition(from_process="reuse", to_process="use", dim_letters=full_flow_letters + ("k",)),
            # disposal: the non-reused material accumulates in the eol waste stock
            fd.FlowDefinition(from_process="eol_management", to_process="eol_waste", dim_letters=full_flow_letters + ("k",)),
            # general trade
            fd.FlowDefinition(from_process="exports", to_process="sysenv", dim_letters=("t", "r")),
            fd.FlowDefinition(from_process="sysenv", to_process="imports", dim_letters=("t", "r")),
        ]

    # 4) Stocks
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
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="hibernating",
                process="hibernating",
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="eol_waste",
                process="eol_waste",
                dim_letters=full_flow_letters + ("k",),
                subclass=fd.SimpleFlowDrivenStock,
            ),
        ]

    # 5) Parameters
    parameters = [
        # historical + future parameters: if time-dependent (h), they will have to be projected to (t)
        RemindMFAParameterDefinition(name="end_use_split", dim_letters=("r", "u",),
                                     description="Split of cement production into different end uses."),
        RemindMFAParameterDefinition(name="cement_production", dim_letters=("h", "r"),
                                     description="Historical cement production volume for each region and year."),
        RemindMFAParameterDefinition(name="clinker_ratio", dim_letters=("h", "r"),
                                     description="Historical clinker-to-cement ratio for each region."),
        RemindMFAParameterDefinition(name="lifetime_mean", dim_letters=("h", "r", "u"),
                                     description="Mean lifetime of historical cement stocks by region and end use."),
        RemindMFAParameterDefinition(name="lifetime_rel_std", dim_letters=(),
                                     description="Relative standard deviation of lifetime of cement in buildings and infrastructure."),
        # trade parameters
        RemindMFAParameterDefinition(name="clinker_imports", dim_letters=("h", "r"),
                                     description="Historical clinker imports for each region and year."),
        RemindMFAParameterDefinition(name="clinker_exports", dim_letters=("h", "r"),
                                     description="Historical clinker exports for each region and year."),
        RemindMFAParameterDefinition(name="cement_imports", dim_letters=("h", "r"),
                                     description="Historical cement imports for each region and year."),
        RemindMFAParameterDefinition(name="cement_exports", dim_letters=("h", "r"),
                                     description="Historical cement exports for each region and year."),
        # future parameters
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r", "S"),
                                     description="Historical and projected population for each region and model year."),
        RemindMFAParameterDefinition(name="gdppc", dim_letters=("t", "r", "S"),
                                     description="Historical and projected GDP per capita for each region and model year."),
        RemindMFAParameterDefinition(name="cement_losses", dim_letters=(),
                                     description="Share of cement lost during construction."),
        RemindMFAParameterDefinition(name="clinker_losses", dim_letters=(),
                                     description="Share of clinker lost during clinker production."),
        RemindMFAParameterDefinition(name="cement_ratio", dim_letters=("r", "m",),
                                     description="Mass share of cement in each newly produced construction material."),
        RemindMFAParameterDefinition(name="construction_material_split", dim_letters=("r", "m"),
                                     description="Share of cement used in each construction material by region."),
    ]

    # 6) Trades
    if historical:
        trades = [
            TradeDefinition(name="clinker", dim_letters=("h", "r")),
            TradeDefinition(name="cement", dim_letters=("h", "r")),
        ]
    else:
        trades = [
            TradeDefinition(name="clinker", dim_letters=("t", "r")),
            TradeDefinition(name="cement", dim_letters=("t", "r")),
        ]

    # 7) Modules
    parts = [
        RemindMFAPartialDefinition(
            dimensions=dimensions,
            processes=processes,
            flows=flows,
            stocks=stocks,
            parameters=parameters,
            trades=trades,
        )
    ]
    if bottom_up_active:
        parts.append(get_bottom_up_data_definition())
    if bottom_up:
        parts.append(get_bottom_up_system_definition(cfg, full_flow_letters))
    if carbonation_active:
        parts.append(get_carbonation_definition())

    return RemindMFADefinition.from_parts(parts)


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
        name="cement_ratio",
        dim_letters=("r", "m"),
    ),
    # cement lifetime is time-dependent and therefore needs (constant) extrapolation first
    ExtrapolationDefinition(
        name="lifetime_mean",
        dim_letters=("r",),
    ),
    ExtrapolationDefinition(
        name="lifetime_std",
        dim_letters=("r",),
    ),
    ExtrapolationDefinition(
        name="reuse_share",
        dim_letters=("r", "m"),
        create_new=True,
    ),
]

# fmt: on
