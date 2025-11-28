import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.helper import RemindMFAParameterDefinition, RemindMFADefinition


def get_definition(cfg: GeneralCfg):
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Stock Type", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
    ]

    processes = [
        "sysenv",
        "raw_meal_preparation",
        "clinker_production",
        "cement_grinding",
        "concrete_production",
        "use",
        "eol",
    ]

    flows = [
        # historic flows
        fd.FlowDefinition(from_process="sysenv", to_process="use", dim_letters=("h", "r", "s")),
        fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "s")),
        # future flows
        fd.FlowDefinition(
            from_process="sysenv", to_process="raw_meal_preparation", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="raw_meal_preparation",
            to_process="clinker_production",
            dim_letters=("t", "r"),
        ),
        fd.FlowDefinition(
            from_process="sysenv", to_process="clinker_production", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="clinker_production", to_process="cement_grinding", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="sysenv", to_process="cement_grinding", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="cement_grinding", to_process="concrete_production", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="sysenv", to_process="concrete_production", dim_letters=("t", "r")
        ),
        fd.FlowDefinition(
            from_process="concrete_production", to_process="use", dim_letters=("t", "r", "s")
        ),
        fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("t", "r", "s")),
        fd.FlowDefinition(from_process="eol", to_process="sysenv", dim_letters=("t", "r", "s")),
    ]

    stocks = [
        fd.StockDefinition(
            name="historic_in_use",
            process="use",
            dim_letters=("h", "r", "s"),
            subclass=fd.InflowDrivenDSM,
            lifetime_model_class=cfg.customization.lifetime_model,
            time_letter="h",
        ),
        fd.StockDefinition(
            name="in_use",
            process="use",
            dim_letters=("t", "r", "s"),
            subclass=fd.StockDrivenDSM,
            lifetime_model_class=cfg.customization.lifetime_model,
        ),
        fd.StockDefinition(
            name="eol",
            process="eol",
            dim_letters=("t", "r", "s"),
            subclass=fd.SimpleFlowDrivenStock,
        ),
    ]

    parameters = [
        RemindMFAParameterDefinition(
            name="cement_production",
            dim_letters=("h", "r"),
            description="Historic cement production",
        ),
        RemindMFAParameterDefinition(
            name="cement_trade", dim_letters=("h", "r"), description="Historic cement trade flows"
        ),
        RemindMFAParameterDefinition(
            name="clinker_ratio", dim_letters=("t", "r"), description="Clinker to cement ratio"
        ),
        RemindMFAParameterDefinition(
            name="cement_ratio", dim_letters=(), description="Cement content ratio in concrete"
        ),
        RemindMFAParameterDefinition(
            name="use_split",
            dim_letters=("s",),
            description="Distribution of cement use across stock types",
        ),
        RemindMFAParameterDefinition(
            name="historic_use_lifetime_mean",
            dim_letters=("h", "r", "s"),
            description="Mean lifetime of historic cement stocks",
        ),
        RemindMFAParameterDefinition(
            name="future_use_lifetime_mean",
            dim_letters=("t", "r", "s"),
            description="Mean lifetime of future cement stocks",
        ),
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r"), description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r"), description="GDP per capita"
        ),
    ]

    return RemindMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
    )


scenario_parameters = []
