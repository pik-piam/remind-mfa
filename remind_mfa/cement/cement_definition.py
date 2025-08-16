import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg


def get_definition(cfg: GeneralCfg, historic: bool):

    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Stock Type", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Product Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Product Application", dim_letter="a", dtype=str),
        fd.DimensionDefinition(name="Waste Type", dim_letter="w", dtype=str),
        fd.DimensionDefinition(name="Waste Size", dim_letter="p", dtype=str),
    ]

    # 2) Processes
    if historic:
        processes = [
            "sysenv",
            "use",
        ]
    else:
        processes = [
            "sysenv",
            "prod_clinker",
            "prod_cement",
            "prod_product",
            "use",
            "demolition",
            "eol",
            "atmosphere",
            "carbonation"
        ]

    # 3) Flows
    if historic:
        flows = [
            fd.FlowDefinition(from_process="sysenv", to_process="use", dim_letters=("h", "r", "s")),
            fd.FlowDefinition(from_process="use", to_process="sysenv", dim_letters=("h", "r", "s")),
        ]
    else:
        flows = [
            # historic flows
            fd.FlowDefinition(from_process="sysenv", to_process="prod_clinker", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="prod_cement", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="prod_clinker", to_process="sysenv", dim_letters=("t", "r", "m")), #CKD production
            fd.FlowDefinition(from_process="sysenv", to_process="prod_cement", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="prod_cement", to_process="prod_product", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="prod_cement", to_process="sysenv", dim_letters=("t", "r", "m")), # cement losses
            fd.FlowDefinition(from_process="sysenv", to_process="prod_product", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="prod_product", to_process="use", dim_letters=("t", "r", "s", "m", "a")),
            fd.FlowDefinition(from_process="use", to_process="demolition", dim_letters=("t", "r", "s", "m", "a", "w")),
            fd.FlowDefinition(from_process="demolition", to_process="eol", dim_letters=("t", "r", "s", "m", "a", "w")),
            fd.FlowDefinition(from_process="eol", to_process="sysenv", dim_letters=("t", "r", "s", "m", "a", "w")),
            # atmosphere
            fd.FlowDefinition(from_process="prod_clinker", to_process="atmosphere", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="atmosphere", to_process="sysenv", dim_letters=("t", "r", "m")),
            fd.FlowDefinition(from_process="atmosphere", to_process="carbonation", dim_letters=("t", "r", "m")),
        ]

    # 4) Stocks
    if historic:
        stocks = [
            fd.StockDefinition(
                name="historic_cement_in_use",
                process="use",
                dim_letters=("h", "r", "s"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.customization.lifetime_model,
                time_letter="h",
            ),
        ]
    else:
        stocks = [
            fd.StockDefinition(
                name="in_use",
                process="use",
                dim_letters=("t", "r", "s", "m", "a"),
                subclass=fd.StockDrivenDSM,
                lifetime_model_class=cfg.customization.lifetime_model,
            ),
            fd.StockDefinition(
                name="demolition",
                process="demolition",
                dim_letters=("t", "r", "s", "m", "a", "w"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=fd.TruncatedWeibullLifetime,
            ),
            fd.StockDefinition(
                name="eol",
                process="eol",
                dim_letters=("t", "r", "s", "m", "a", "w"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="atmosphere",
                process="atmosphere",
                dim_letters=("t", "r", "m"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
            fd.StockDefinition(
                name="carbonated_co2",
                process="carbonation",
                dim_letters=("t", "r", "m"),
                subclass=fd.SimpleFlowDrivenStock,
            ),
        ]

    # 5) Parameters
    parameters = [
        # common parameters
        fd.ParameterDefinition(name="stock_type_split", dim_letters=("r", "s",)), # manual (guess)
        # historic parameters
        fd.ParameterDefinition(name="cement_production", dim_letters=("h", "r")),
        fd.ParameterDefinition(name="cement_trade", dim_letters=("h", "r")),
        fd.ParameterDefinition(name="historic_use_lifetime_mean", dim_letters=("h", "r", "s")),
        # future parameters
        fd.ParameterDefinition(name="clinker_ratio", dim_letters=("t", "r")), # manual (extrapolated)
        fd.ParameterDefinition(name="future_use_lifetime_mean", dim_letters=("t", "r", "s")), # manual (extrapolated)
        fd.ParameterDefinition(name="population", dim_letters=("t", "r")),
        fd.ParameterDefinition(name="gdppc", dim_letters=("t", "r")),
        # carbonation parameters
        fd.ParameterDefinition(name="cao_ratio", dim_letters=()), # manual (guess)
        fd.ParameterDefinition(name="cao_emission_factor", dim_letters=()), # manual (calculated)
        fd.ParameterDefinition(name="product_density", dim_letters=("m",)), # manual (guess)

        fd.ParameterDefinition(name="carbonation_rate", dim_letters=("r", "a")),
        fd.ParameterDefinition(name="carbonation_rate_coating", dim_letters=("r",)),
        fd.ParameterDefinition(name="carbonation_rate_co2", dim_letters=("r",)),
        fd.ParameterDefinition(name="carbonation_rate_additives", dim_letters=("r",)),

        fd.ParameterDefinition(name="product_thickness", dim_letters=("r", "a")),
        fd.ParameterDefinition(name="cao_carbonation_share", dim_letters=("r", "m")),
        fd.ParameterDefinition(name="product_cement_content", dim_letters=("r", "a")), # TODO rename to product_cement_density
        fd.ParameterDefinition(name="product_application_split", dim_letters=("r", "a")),
        fd.ParameterDefinition(name="product_material_split", dim_letters=("r", "m",)),
        fd.ParameterDefinition(name="product_material_application_transform", dim_letters=("m", "a")),
        fd.ParameterDefinition(name="cement_losses", dim_letters=("r",)),
        fd.ParameterDefinition(name="clinker_losses", dim_letters=("r",)),
        fd.ParameterDefinition(name="waste_type_split", dim_letters=("r", "w")),
        fd.ParameterDefinition(name="waste_size_share", dim_letters=("r", "w", "p")),
        fd.ParameterDefinition(name="waste_size_min", dim_letters=("w", "p")),  # manual (from Xi2016 categories)
        fd.ParameterDefinition(name="waste_size_max", dim_letters=("w", "p",)),  # manual (from Xi2016 categories)
    ]
    

    return fd.MFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
    )
