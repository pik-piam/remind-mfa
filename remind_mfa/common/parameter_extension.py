import flodym as fd
from abc import ABC, abstractmethod
from typing import Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.assumptions_doc import add_assumption_doc

class ParameterExtension(ABC):
    """Base class from which new parameter extensions can be implemented."""

    @abstractmethod
    def apply(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        """Apply the extensions to the parameter."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the extension."""
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
        

class ConstantExtension(ParameterExtension):
    """Keep parameter constant at last observed value."""
    
    def apply(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        add_assumption_doc(
            type="model switch",
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


class ParameterExtensionManager:
    """Manager for applying parameter extensions in cement models."""
        
    def __init__(self,
                 cfg: "GeneralCfg",
                 extended_time: fd.Dimension,
                ):
        self.parameter_extension_classes = cfg.model_switches.parameter_extension_classes
        self.extended_time = extended_time
    
    def apply_prm_extensions(self, parameters: Dict[str, fd.Parameter],) -> Dict[str, fd.Parameter]:
        """Apply parameter extensions to parameters. Only those listed in parameter_extension in config model switches are adjusted."""
        
        modified_parameters = parameters.copy()

        if self.parameter_extension_classes is None:
            return modified_parameters
        
        for param_name, extension_class in self.parameter_extension_classes.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")
                
            modified_parameters[param_name] = extension_class().apply(modified_parameters[param_name], self.extended_time)
        
        return modified_parameters