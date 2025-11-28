from remind_mfa.common.helper import RemindMFAParameterDefinition, PlainDataPointDefinition


scenario_parameters = [
    RemindMFAParameterDefinition(
        name="lifetime_factor",
        dim_letters=("r",),
    ),
    PlainDataPointDefinition(
        name="lifetime_factor_blending_year",
    ),
]
