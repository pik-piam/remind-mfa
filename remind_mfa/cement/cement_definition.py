import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg


def get_definition(cfg: GeneralCfg):
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Stock Type", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        # fd.DimensionDefinition(name="Cementious Material", dim_letter="c", dtype=str),
    ]

    processes = [
        "sysenv",
        "prod_clinker",
        "prod_cement",
        "prod_concrete",
        "use",
        "eol",
    ]

    flows = [
        # historic flows
        fd.FlowDefinition(from_process="sysenv", to_process="use", dim_letters=("h", "r", "s")),
        fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "s")),
        # future flows
        fd.FlowDefinition(from_process="sysenv", to_process="prod_clinker", dim_letters=("t", "r")),
        fd.FlowDefinition(from_process="prod_clinker", to_process="prod_cement", dim_letters=("t", "r")),
        fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("t", "r")),
        fd.FlowDefinition(from_process="prod_cement", to_process="prod_concrete", dim_letters=("t", "r")),
        fd.FlowDefinition(from_process="sysenv", to_process="prod_concrete", dim_letters=("t", "r")),
        fd.FlowDefinition(from_process="prod_concrete", to_process="use", dim_letters=("t", "r", "s")),
        fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("t", "r", "s")),
        fd.FlowDefinition(from_process="eol", to_process="sysenv", dim_letters=("t", "r", "s")),
    ]

    stocks = [
        fd.StockDefinition(
            name="historic_cement_in_use",
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
        fd.ParameterDefinition(name="cement_production", dim_letters=("h", "r")),
        fd.ParameterDefinition(name="cement_trade", dim_letters=("h", "r")),
        fd.ParameterDefinition(name="clinker_ratio", dim_letters=("t", "r")),
        fd.ParameterDefinition(name="cement_ratio", dim_letters=()),
        fd.ParameterDefinition(name="use_split", dim_letters=("s",)),
        fd.ParameterDefinition(name="historic_use_lifetime_mean", dim_letters=("h", "r", "s")),
        fd.ParameterDefinition(name="future_use_lifetime_mean", dim_letters=("t", "r", "s")),
        fd.ParameterDefinition(name="population", dim_letters=("t", "r")),
        fd.ParameterDefinition(name="gdppc", dim_letters=("t", "r")),
    ]

    return fd.MFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
    )
