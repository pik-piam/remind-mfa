import flodym as fd
from typing import Optional

from remind_mfa.common.scenarios import ScenarioRegistry, ConstantScenario, ScenarioManager
from remind_mfa.common.common_cfg import GeneralCfg

class CementScenarioRegistry(ScenarioRegistry):

    def _register_defaults(self):
        self.register("constant", ConstantScenario())

class CementScenarioManager(ScenarioManager):

    def __init__(self,
                 cfg: GeneralCfg,
                 extended_time: fd.Dimension,
                 registry: Optional[ScenarioRegistry] = None,
                 ):
        return super().__init__(cfg, extended_time, registry or CementScenarioRegistry())




