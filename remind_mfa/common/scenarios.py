import flodym as fd
from abc import ABC, abstractmethod
from typing import Optional, Dict

from .common_cfg import GeneralCfg
from remind_mfa.common.assumptions_doc import add_assumption_doc

class ScenarioStrategy(ABC):
    """Base class for scenario strategies. Based on this class, new scenarios can be implemented."""

    @abstractmethod
    def apply(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        """Apply the scenario to the parameter."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the scenario."""
        pass

    def initialize_new_param(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        """Initialize a new parameter with extended time dimension."""
        if not "h" in parameter.dims.letters:
            raise ValueError(f"Parameter {parameter.name} does not have historic time dimension 'h'")
        if not "t" == extended_time.letter:
            raise ValueError(f"New time dimension does not have letter 't'")

        # copy values from historic paramter and save in new parameter with extended time dimension
        new_dims = parameter.dims.replace("h", extended_time)
        new_param = fd.Parameter(dims=new_dims, name=parameter.name)
        new_param[{"t": parameter.dims["h"]}] = parameter

        return new_param
        

class ConstantScenario(ScenarioStrategy):
    """Keep parameter constant at last observed value."""
    
    def apply(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        add_assumption_doc(
            type="scenario",
            name=f"Keep {parameter.name} constant",
            description=self.description,
        )
        new_param = self.initialize_new_param(parameter, extended_time)

        # set values to last historic value
        last_historic_year = parameter.dims["h"].items[-1]
        last_value = parameter[{"h": last_historic_year}]
        new_param[...] = last_value.cast_to(new_param.dims)

        # overwrite historic values with original paramter values
        new_param[{"t": parameter.dims["h"]}] = parameter

        return new_param
    
    @property
    def description(self) -> str:
        return "Parameter is kept constant into the future at last observed value."
    

class ScenarioRegistry:
    """Registry of named scenarios. Used to look up scenarios by name and connect them to their scenario implementation."""
    
    def __init__(self):
        self._scenarios = {}
        self._register_defaults()
    
    @abstractmethod
    def _register_defaults(self):
        """Register default scenarios."""
        pass
    
    def register(self, name: str, scenario: ScenarioStrategy) -> None:
        """Register a new scenario."""
        self._scenarios[name] = scenario

    def get(self, name: str) -> Optional[ScenarioStrategy]:
        """Get a scenario by name."""
        return self._scenarios.get(name)


class ScenarioManager:
    """Manager for applying parameter scenarios in cement models."""
        
    def __init__(self,
                 cfg: GeneralCfg,
                 extended_time: fd.Dimension,
                 registry: Optional[ScenarioRegistry] = None,
                ):
        self.scenarios = cfg.scenario
        self.extended_time = extended_time
        self.registry = registry or ScenarioRegistry()
    
    def apply_scenarios(self, parameters: Dict[str, fd.Parameter],) -> Dict[str, fd.Parameter]:
        """Apply parameter scenarios to parameters. Only those registed in with a scenario in scenario registry are modified."""
        
        modified_parameters = parameters.copy()
        
        for param_name, scenario_name in self.scenarios.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")
                
            scenario = self.registry.get(scenario_name)
            if not scenario:
                raise ValueError(f"Scenario '{scenario_name}' not found in registry.")
                
            modified_parameters[param_name] = scenario.apply(modified_parameters[param_name], self.extended_time)
        
        return modified_parameters