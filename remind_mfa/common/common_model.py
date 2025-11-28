from typing import List

from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.scenarios import ScenarioReader
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.helper import RemindMFAParameterDefinition


class CommonModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg

    def read_scenario_parameters(self, model_specific_prm_def: List[RemindMFAParameterDefinition]):
        parameter_definitions = common_scn_prm_def + model_specific_prm_def
        scenario_reader = ScenarioReader(
            name=self.cfg.customization.scenario,
            base_path=self.cfg.scenarios_path,
            model=self.cfg.model,
            dims=self.dims,
            parameter_definitions=parameter_definitions,
        )
        self.scenario_parameters = scenario_reader.get_parameters()