import flodym as fd
from abc import ABC, abstractmethod
from typing import Dict, TYPE_CHECKING
from numbers import Number

if TYPE_CHECKING:
    from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.data_blending import blend


class ParameterExtrapolation(ABC):
    """Base class for parameter transformations including extrapolation and scenario application.
    
    Handles three cases:
    1. Parameters with 'h' dimension → extend to 't' dimension
    2. Parameters with 't' dimension → modify future values
    3. Parameters with no time dimension → add time dimension and apply transformation to future values
    
    Important: fill_values() always receives a prepared parameter with 't' dimension.
    Historic values are automatically preserved by the transform() method.
    """

    @abstractmethod
    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.Parameter,
    ) -> fd.Parameter:
        """Sets values of new_param based on transformation method.
        
        Args:
            prepared_param: Parameter with 't' dimension (converted from 'h' if necessary)
            new_param: New parameter with 't' dimension to fill
            
        Returns:
            Parameter with filled values
            
        Note:
            Historic values will be overwritten with original data after this method returns.
            Focus on computing the desired future values.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the transformation."""
        raise NotImplementedError

    def transform(
        self,
        parameter: fd.Parameter,
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ) -> fd.Parameter:
        """Transform parameter to extended time dimension, applying the transformation method.
        
        Handles all three cases: h→t extrapolation, t→t modification, and static→t expansion.
        Historic values are always preserved from the original parameter.
        """
        self.historic_time = historic_time
        self.extended_time = extended_time
        
        # Prepare parameter: convert h→t or add t dimension if needed
        prepared_param = self._prepare_parameter(parameter)
        
        # Initialize new parameter with extended time dimension
        new_param = fd.Parameter(dims=prepared_param.dims, name=prepared_param.name)
        
        # Fill values using the specific transformation method
        new_param = self.fill_values(prepared_param, new_param)
        
        # Preserve original historic values
        new_param[{"t": self.historic_time}] = prepared_param[{"t": self.historic_time}]

        return new_param

    def _prepare_parameter(
        self,
        parameter: fd.Parameter,
    ) -> fd.Parameter:
        """Prepare parameter to have 't' dimension.
        
        - h→t: Expand historic parameter to full time dimension
        - static→t: Add time dimension
        - t→t: Return as-is
        """
        if "t" in parameter.dims.letters:
            return parameter
        
        if "h" in parameter.dims.letters:
            # Convert h to t: expand historic data to extended time
            new_dims = parameter.dims.replace("h", self.extended_time)
            new_param = fd.Parameter(dims=new_dims, name=parameter.name)
            new_param[{"t": self.historic_time}] = parameter
            return new_param
        
        # Static parameter: add time dimension
        new_dims = parameter.dims.prepend(self.extended_time)
        new_param = parameter.cast_to(new_dims)
        return new_param
    
    @property
    def _last_historic_time(self) -> Number:
        """Get the last historic year from the historic time dimension."""
        return self.historic_time.items[-1]
    
    def _get_last_historic_value(self, prepared_param: fd.Parameter) -> fd.FlodymArray:
        """Get the value at the last historic year from a prepared (t-dimension) parameter."""
        return prepared_param[{"t": self._last_historic_time}]

class ConstantExtrapolation(ParameterExtrapolation):
    """Keep parameter constant at last observed value.
    
    Special case of BlendExtrapolation where start and end values are the same.
    """

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.Parameter,
    ) -> fd.Parameter:
        
        add_assumption_doc(
            type="model switch",
            name=f"Keep {prepared_param.name} constant",
            description=self.description,
        )

        # get last historic value
        last_value = self._get_last_historic_value(prepared_param)

        # set values to last historic value
        new_param[...] = last_value.cast_to(new_param.dims)

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is kept constant into the future at last observed value."


class ZeroExtrapolation(ParameterExtrapolation):
    """Set parameter to zero in future."""

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.FlodymArray,
    ) -> fd.Parameter:
        
        add_assumption_doc(
            type="model switch",
            name=f"Set {prepared_param.name} to zero",
            description=self.description,
        )

        new_param[...] = 0

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is set to zero in the future."


class LinearToTargetExtrapolation(ParameterExtrapolation):
    """Linearly interpolate to a future target value according to scenario settings."""

    def __init__(self, scenario_parameters: Dict[str, Number]):
        self.scenario_parameters = scenario_parameters

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.FlodymArray,
    ) -> fd.Parameter:
        
        add_assumption_doc(
            type="model switch",
            name=f"Linear interpolation of {prepared_param.name} to target value by target year.",
            description=self.description,
        )

        new_param[...] = blend(
            target_dims=new_param.dims,
            y_lower=self._get_last_historic_value(prepared_param),
            y_upper=self.scenario_parameters[prepared_param.name],
            x="t",
            x_lower=self._last_historic_time,
            x_upper=self.scenario_parameters[prepared_param.name + "_year"],
            type="linear",
        )

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is linearly interpolated to a future target value by a target year according to scenario settings."


class SmoothScalingExtrapolation(ParameterExtrapolation):
    """Future values are scaled by a factor that changes linearly to a target factor."""

    def __init__(self, scenario_parameters: Dict[str, Number]):
        self.scenario_parameters = scenario_parameters

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.FlodymArray,   
    ) -> fd.Parameter:
        
        add_assumption_doc(
            type="model switch",
            name=f"Scaling of {prepared_param.name} by factor that increases linearly to target value by target year.",
            description=self.description,
        )

        scaling_factors = blend(
            target_dims=new_param.dims,
            y_lower=1.0,
            y_upper=self.scenario_parameters[prepared_param.name],
            x="t",
            x_lower=self._last_historic_time,
            x_upper=self.scenario_parameters[prepared_param.name + "_year"],
            type="quintic",
        )

        new_param[...] = prepared_param * scaling_factors

        return new_param
    
    @property
    def description(self) -> str:
        return "Parameter values are scaled by a factor that changes linearly to a target factor by a target year according to scenario settings."

class ParameterExtrapolationManager:
    """Manager for applying parameter transformations (extrapolation and scenario application).
    
    Handles transformation of parameters from:
    - Historic ('h') to extended time ('t') 
    - Already-future ('t') parameters with scenario modifications
    - Static (no time dim) parameters with scenario application
    """

    def __init__(
        self,
        cfg: "CommonCfg",
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ):
        self.parameter_extrapolation_classes = cfg.model_switches.parameter_extrapolation_classes
        self.historic_time = historic_time
        self.extended_time = extended_time

        if "h" != self.historic_time.letter:
            raise ValueError(f"Historic time dimension does not have letter 'h'")
        if "t" != self.extended_time.letter:
            raise ValueError(f"New time dimension does not have letter 't'")

    def apply_prm_extrapolation(
        self,
        parameters: Dict[str, fd.Parameter],
        scenario_parameters: Dict[str, Number] = None,
    ) -> Dict[str, fd.Parameter]:
        """Apply transformation to parameters.
        
        Only parameters listed in parameter_extrapolation in config model switches are adjusted.
        
        Args:
            parameters: Dictionary of parameters to potentially transform
            scenario_parameters: Dictionary of scenario-specific values (required for some transformations)
            
        Returns:
            Dictionary of parameters with transformations applied where configured
        """
        modified_parameters = parameters.copy()

        if self.parameter_extrapolation_classes is None:
            return modified_parameters

        for param_name, extrapolation_class in self.parameter_extrapolation_classes.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")

            # Instantiate the extrapolation class with appropriate arguments
            extrapolation_instance = self._create_extrapolation_instance(
                extrapolation_class, scenario_parameters
            )

            modified_parameters[param_name] = extrapolation_instance.transform(
                modified_parameters[param_name], self.historic_time, self.extended_time
            )

        return modified_parameters

    def _create_extrapolation_instance(
        self,
        extrapolation_class: type,
        scenario_parameters: Dict[str, Number],
    ) -> ParameterExtrapolation:
        """Create an instance of the extrapolation class with appropriate constructor arguments.
        
        Classes that require scenario_parameters in their constructor will receive them.
        Other classes are instantiated with no arguments.
        """
        # Classes that require scenario_parameters
        classes_requiring_scenario_params = (
            LinearToTargetExtrapolation,
            SmoothScalingExtrapolation,
        )
        
        if issubclass(extrapolation_class, classes_requiring_scenario_params):
            if scenario_parameters is None:
                raise ValueError(
                    f"scenario_parameters required for {extrapolation_class.__name__}"
                )
            return extrapolation_class(scenario_parameters)
        else:
            return extrapolation_class()
