import flodym as fd

from remind_mfa.common.helper import RemindMFAParameterDefinition, PlainDataPointDefinition, RemindMFADefinition
from remind_mfa.common.common_cfg import GeneralCfg

def get_definition():
    return RemindMFADefinition(
    dimensions=[],
    processes=[],
    flows=[],
    stocks=[],
    parameters=[],
    trades=[]
)

scenario_parameters = [
    RemindMFAParameterDefinition(
        name="lifetime_factor",
        dim_letters=("r",),
    ),
    PlainDataPointDefinition(
        name="lifetime_factor_blending_year",
    ),
]
