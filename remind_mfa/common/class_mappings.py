from remind_mfa.common.helper import ModelNames
from .common_cfg import PlasticsCfg, SteelCfg, CementCfg
from remind_mfa.cement.cement_model import CementModel
from remind_mfa.plastics.plastics_model import PlasticsModel
from remind_mfa.steel.steel_model import SteelModel


models = {
    ModelNames.PLASTICS: PlasticsModel,
    ModelNames.STEEL: SteelModel,
    ModelNames.CEMENT: CementModel,
}

cfgs = {
    ModelNames.PLASTICS: PlasticsCfg,
    ModelNames.STEEL: SteelCfg,
    ModelNames.CEMENT: CementCfg,
}
