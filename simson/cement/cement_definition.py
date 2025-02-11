import flodym as fd

from simson.common.common_cfg import CommonCfg


class CementMFADefinition(fd.MFADefinition):
    pass


def get_definition(cfg: CommonCfg):
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
        fd.FlowDefinition(from_process="sysenv", to_process="raw_meal_preparation", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="raw_meal_preparation", to_process="clinker_production", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="raw_meal_preparation", to_process="sysenv", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="clinker_production", to_process="cement_grinding", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="clinker_production", to_process="sysenv", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="cement_grinding", to_process="concrete_production", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="cement_grinding", to_process="sysenv", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="concrete_production", to_process="use", dim_letters=("h", "r", "s")),
        fd.FlowDefinition(from_process="concrete_production", to_process="sysenv", dim_letters=("h", "r")),
        fd.FlowDefinition(from_process="use", to_process="eol", dim_letters=("h", "r", "s")),

        # future flows
        # TODO
    ]

    stocks = [
        fd.StockDefinition(
            name="historic_in_use",
            process="use",
            dim_letters=("h", "r", "s"),
            subclass=fd.InflowDrivenDSM,
            lifetime_model_class=fd.NormalLifetime,

        ),
        fd.StockDefinition(
            name="historic_eol",
            process="eol",
            dim_letters=("h", "r", "s"),
            subclass=fd.SimpleFlowDrivenStock,
            lifetime_model_class=fd.NormalLifetime, #TODO see if this is necessary if I want to set lifetime to infinity
        ),

    ]

    parameters = [
        fd.ParameterDefinition(name="clinker_ratio", dim_letters=("r")),
        fd.ParameterDefinition(name="cement_ratio", dim_letters=("r")),
        

    ]

    # trades = []

    return CementMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
        # trades=trades,
    )

