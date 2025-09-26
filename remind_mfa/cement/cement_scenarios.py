from typing import Optional, Dict, Callable
from dataclasses import dataclass
import flodym as fd
from abc import ABC, abstractmethod

from remind_mfa.common.assumptions_doc import add_assumption_doc

class ScenarioStrategy(ABC):
    """Abstract base class for scenario strategies."""

    @abstractmethod
    def apply(self, parameter: fd.Parameter) -> fd.Parameter:
        """Apply the scenario to the parameter."""
        pass

    @abstractmethod
    @property
    def description(self) -> str:
        """Return a description of the scenario."""
        pass


class ConstantScenario(ScenarioStrategy):
    """Keep parameter constant at last observed value."""
    
    def apply(self, parameter: fd.Parameter) -> None:
        add_assumption_doc(
            type="scenario",
            name=f"Keep {parameter.name} constant",
            description=self.get_description(),
        )
        # Actual implementation here
        pass
    
    def get_description(self) -> str:
        return "Parameter is kept constant into the future at last observed value."
    

class PercentDeclineScenario(ScenarioStrategy):
    """Apply percentage decline with an optional floor value."""
    
    def __init__(self, decline_rate: float, floor_type: Optional[str] = None):
        self.decline_rate = decline_rate
        self.floor_type = floor_type
    
    def apply(self, parameter: fd.Parameter) -> None:
        add_assumption_doc(
            type="scenario",
            name=f"Decline {parameter.name} by {self.decline_rate*100}%",
            description=self.get_description(),
        )
        # Actual implementation here
        pass
    
    def get_description(self) -> str:
        floor_desc = ""
        if self.floor_type:
            floor_desc = f" with a {self.floor_type} floor"
        return f"Parameter declines by {self.decline_rate*100}% annually{floor_desc}."


class ZeroScenario(ScenarioStrategy):
    """Set parameter to zero."""
    
    def apply(self, parameter: fd.Parameter) -> None:
        add_assumption_doc(
            type="scenario",
            name=f"Set {parameter.name} to zero",
            description=self.description(),
        )
        # Actual implementation here
        pass
    
    def description(self) -> str:
        return "Parameter is set to zero for future values."


class ScenarioRegistry:
    """Registry of named scenarios."""
    
    def __init__(self):
        self._scenarios = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default scenarios."""
        self.register("constant", ConstantScenario())
        self.register("1percent_decline_with_current_floor", 
                     PercentDeclineScenario(0.01, "current"))
        self.register("zero", ZeroScenario())
    
    def register(self, name: str, scenario: ScenarioStrategy) -> None:
        """Register a new scenario."""
        self._scenarios[name] = scenario

    def get(self, name: str) -> Optional[ScenarioStrategy]:
        """Get a scenario by name."""
        return self._scenarios.get(name)


class ScenarioManager:
    """Manager for applying parameter scenarios in cement models."""

    STANDARD_SCENARIOS = {
        "clinker_ratio": "constant",
        "use_lifetime": "constant",
        "cement_trade": "zero",
    }
    
    def __init__(self,
                 registry: Optional[ScenarioRegistry] = None,
                 scenarios: Optional[Dict[str, str]] = None):
        self.registry = registry or ScenarioRegistry()
        self.scenarios = scenarios or self.STANDARD_SCENARIOS
    
    def apply_scenarios(self, parameters: Dict[str, fd.Parameter], 
                        ) -> Dict[str, fd.Parameter]:
        """Apply parameter scenarios to parameters."""
        
        modified_parameters = parameters.copy()
        
        for param_name, scenario_name in self.scenarios.items():
            if param_name not in modified_parameters:
                print(f"Warning: Parameter '{param_name}' not found")
                continue
                
            scenario = self.registry.get(scenario_name)
            if not scenario:
                print(f"Warning: Unknown scenario '{scenario_name}'")
                continue
                
            scenario.apply(modified_parameters[param_name])
        
        return modified_parameters