import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.helper import RemindMFAParameterDefinition, RemindMFADefinition


def get_definition(cfg: CementCfg, historic: bool):

    # 1) Dimensions
    dimensions = [
        fd.DimensionDefinition(name="Time", dim_letter="t", dtype=int),
        fd.DimensionDefinition(name="Region", dim_letter="r", dtype=str),
        fd.DimensionDefinition(name="Stock Type", dim_letter="s", dtype=str),
        fd.DimensionDefinition(name="Historic Time", dim_letter="h", dtype=int),
        fd.DimensionDefinition(name="Product Material", dim_letter="m", dtype=str),
        fd.DimensionDefinition(name="Product Application", dim_letter="a", dtype=str),
        # carbonation dimensions
        fd.DimensionDefinition(name="Waste Type", dim_letter="w", dtype=str),
        fd.DimensionDefinition(name="Waste Size", dim_letter="p", dtype=str),
        fd.DimensionDefinition(name="Carbonation Location", dim_letter="c", dtype=str),
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
            "eol",
            "atmosphere",
            "carbonation",
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
            fd.FlowDefinition(
                from_process="sysenv", to_process="prod_clinker", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="prod_clinker", to_process="prod_cement", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="prod_clinker", to_process="sysenv", dim_letters=("t", "r", "m")
            ),  # CKD production
            fd.FlowDefinition(
                from_process="sysenv", to_process="prod_cement", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="prod_cement", to_process="prod_product", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="prod_cement", to_process="sysenv", dim_letters=("t", "r", "m")
            ),  # cement losses
            fd.FlowDefinition(
                from_process="sysenv", to_process="prod_product", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="prod_product", to_process="use", dim_letters=("t", "r", "s", "m", "a")
            ),
            fd.FlowDefinition(
                from_process="use", to_process="eol", dim_letters=("t", "r", "m", "a")
            ),
            fd.FlowDefinition(
                from_process="eol", to_process="sysenv", dim_letters=("t", "r", "m", "a")
            ),
            # atmosphere
            fd.FlowDefinition(
                from_process="prod_clinker", to_process="atmosphere", dim_letters=("t", "r", "m")
            ),
            fd.FlowDefinition(
                from_process="atmosphere",
                to_process="carbonation",
                dim_letters=("t", "r", "m", "c"),
            ),
        ]

    # TODO remove historic_in_use stock, just use in_use, later change from h to t dimension
    # 4) Stocks
    if historic:
        stocks = [
            fd.StockDefinition(
                name="historic_cement_in_use",
                process="use",
                dim_letters=("h", "r", "s"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=cfg.model_switches.lifetime_model,
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
                lifetime_model_class=cfg.model_switches.lifetime_model,
            ),
            fd.StockDefinition(
                name="eol",
                process="eol",
                dim_letters=("t", "r", "m", "a"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=fd.FixedLifetime,
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
                dim_letters=("t", "r", "m", "c"),
                subclass=fd.InflowDrivenDSM,
                lifetime_model_class=fd.FixedLifetime,
            ),
        ]

    # 5) Parameters
    parameters = [
        # common parameters
        RemindMFAParameterDefinition(
            name="stock_type_split",
            dim_letters=(
                "r",
                "s",
            ),
        ),  # manual (guess)
        # historic parameters
        RemindMFAParameterDefinition(
            name="cement_production",
            dim_letters=("h", "r"),
            description="Historic cement production",
        ),
        RemindMFAParameterDefinition(
            name="cement_trade", dim_letters=("h", "r"), description="Historic cement trade flows"
        ),
        RemindMFAParameterDefinition(
            name="clinker_ratio", dim_letters=("h", "r"), description="Clinker to cement ratio"
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
            name="use_lifetime_mean",
            dim_letters=("h", "r", "s"),
            description="Mean lifetime of historic cement stocks",
        ),
        # future parameters
        RemindMFAParameterDefinition(
            name="clinker_ratio", dim_letters=("t", "r")
        ),  # manual (extrapolated)
        RemindMFAParameterDefinition(
            name="population", dim_letters=("t", "r"), description="Population"
        ),
        RemindMFAParameterDefinition(
            name="gdppc", dim_letters=("t", "r"), description="GDP per capita"
        ),
        # carbonation parameters
        RemindMFAParameterDefinition(name="clinker_cao_ratio", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="ckd_cao_ratio", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="ckd_landfill_share", dim_letters=("r",)),
        RemindMFAParameterDefinition(
            name="cao_emission_factor", dim_letters=()
        ),  # manual (calculated)
        RemindMFAParameterDefinition(name="product_density", dim_letters=("m",)),  # manual (guess)
        RemindMFAParameterDefinition(name="carbonation_rate", dim_letters=("r", "a")),
        RemindMFAParameterDefinition(name="carbonation_rate_buried", dim_letters=("r", "a")),
        RemindMFAParameterDefinition(name="carbonation_rate_coating", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="carbonation_rate_co2", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="carbonation_rate_additives", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="product_thickness", dim_letters=("r", "a")),
        RemindMFAParameterDefinition(name="cao_carbonation_share", dim_letters=("r", "m")),
        RemindMFAParameterDefinition(name="product_cement_content", dim_letters=("r", "a")),
        RemindMFAParameterDefinition(name="product_application_split", dim_letters=("r", "a")),
        RemindMFAParameterDefinition(
            name="product_material_split",
            dim_letters=(
                "r",
                "m",
            ),
        ),
        RemindMFAParameterDefinition(
            name="product_material_application_transform", dim_letters=("m", "a")
        ),
        RemindMFAParameterDefinition(name="cement_losses", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="clinker_losses", dim_letters=("r",)),
        RemindMFAParameterDefinition(name="waste_type_split", dim_letters=("r", "w")),
        RemindMFAParameterDefinition(name="waste_size_share", dim_letters=("r", "w", "p")),
        RemindMFAParameterDefinition(
            name="waste_size_min", dim_letters=("w", "p")
        ),  # manual (from Xi2016 categories)
        RemindMFAParameterDefinition(
            name="waste_size_max",
            dim_letters=("w", "p"),
        ),  # manual (from Xi2016 categories)
    ]

    return RemindMFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
    )


scenario_parameters = []
