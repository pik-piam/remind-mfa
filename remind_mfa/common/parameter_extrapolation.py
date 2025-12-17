import flodym as fd
from abc import ABC, abstractmethod
from typing import Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.data_blending import blend


class ParameterExtrapolation(ABC):
    """Base class from which new parameter extrapolations can be implemented."""

    @abstractmethod
    def fill_future_values(self, old_param: fd.Parameter, new_param: fd.Parameter) -> fd.Parameter:
        """Sets values of new_param based on extrapolation method."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the extrapopation."""
        raise NotImplementedError

    def extrapolate(self, parameter: fd.Parameter, extended_time: fd.Dimension) -> fd.Parameter:
        """Extrapolate parameter to extended time dimension, fill with future values using extrapolation method."""

        new_param = self.initialize_empty_parameter(parameter, extended_time)
        new_param = self.fill_future_values(parameter, new_param)
        # overwrite historic values with old parameter values
        new_param[{"t": parameter.dims["h"]}] = parameter

        return new_param

    @staticmethod
    def initialize_empty_parameter(
        parameter: fd.Parameter, extended_time: fd.Dimension
    ) -> fd.Parameter:
        """Initialize a new parameter with extended time dimension."""

        if not "h" in parameter.dims.letters:
            raise ValueError(
                f"Parameter {parameter.name} does not have historic time dimension 'h'"
            )
        if not "t" == extended_time.letter:
            raise ValueError(f"New time dimension does not have letter 't'")

        new_dims = parameter.dims.replace("h", extended_time)
        new_param = fd.Parameter(dims=new_dims, name=parameter.name)
        return new_param


class ConstantExtrapolation(ParameterExtrapolation):
    """Keep parameter constant at last observed value."""

    def fill_future_values(
        self, old_param: fd.Parameter, new_param: fd.FlodymArray
    ) -> fd.Parameter:
        add_assumption_doc(
            type="model switch",
            name=f"Keep {old_param.name} constant",
            description=self.description,
        )

        # get last historic value
        last_historic_year = old_param.dims["h"].items[-1]
        last_value = old_param[{"h": last_historic_year}]

        # set values to last historic value
        new_param[...] = last_value.cast_to(new_param.dims)

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is kept constant into the future at last observed value."


class ZeroExtrapolation(ParameterExtrapolation):
    """Set parameter to zero in future."""

    def fill_future_values(
        self, old_param: fd.Parameter, new_param: fd.FlodymArray
    ) -> fd.Parameter:
        add_assumption_doc(
            type="model switch",
            name=f"Set {old_param.name} to zero",
            description=self.description,
        )

        # set all future values to zero
        new_param[...] = 0

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is set to zero in the future."


class LinearToTargetExtrapolation(ParameterExtrapolation):
    """Linearly interpolate to a future target value according to scenario settings."""

    def __init__(self, scenario_parameters: Dict[str, float]):
        self.scenario_parameters = scenario_parameters

    def fill_future_values(
        self, old_param: fd.Parameter, new_param: fd.FlodymArray
    ) -> fd.Parameter:
        add_assumption_doc(
            type="model switch",
            name=f"Linearly interpolate {old_param.name} to target value {self.scenario_parameters[old_param.name + '_target_value']} by year {self.scenario_parameters[old_param.name + '_target_year']}",
            description=self.description,
        )

        # get target from scenario parameters
        parameter_target = self.scenario_parameters[old_param.name + "_target_value"]
        parameter_target_year = self.scenario_parameters[old_param.name + "_target_year"]
        # get last historic value
        last_historic_year = old_param.dims["h"].items[-1]
        last_value = old_param[{"h": last_historic_year}]
        # blend linearly from last historic value to target
        new_param[...] = blend(
            target_dims=new_param.dims,
            y_lower=last_value,
            y_upper=parameter_target,
            x="t",
            x_lower=last_historic_year,
            x_upper=parameter_target_year,
            type="linear",
        )

        return new_param

    @property
    def description(self) -> str:
        return "Parameter is linearly interpolated to target value."


class ParameterExtrapolationManager:
    """Manager for applying parameter extrapolations."""

    def __init__(
        self,
        cfg: "CommonCfg",
        extended_time: fd.Dimension,
    ):
        self.parameter_extrapolation_classes = cfg.model_switches.parameter_extrapolation_classes
        self.extended_time = extended_time

    def apply_prm_extrapolation(
        self,
        parameters: Dict[str, fd.Parameter],
        scenario_parameters: Dict[str, float] = None,
    ) -> Dict[str, fd.Parameter]:
        """Apply extrapolation to parameters. Only those listed in parameter_extrapolation in config model switches are adjusted."""

        modified_parameters = parameters.copy()

        if self.parameter_extrapolation_classes is None:
            return modified_parameters

        for param_name, extrapolation_class in self.parameter_extrapolation_classes.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")

            if extrapolation_class == LinearToTargetExtrapolation:
                if scenario_parameters is None:
                    raise ValueError("scenario_parameters required for LinearToTargetExtrapolation")
                extrapolation_instance = extrapolation_class(scenario_parameters)
            else:
                extrapolation_instance = extrapolation_class()

            modified_parameters[param_name] = extrapolation_instance.extrapolate(
                modified_parameters[param_name], self.extended_time
            )

        return modified_parameters
