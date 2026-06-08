import numpy as np
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
        new_param: fd.Parameter,
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


class ScenarioExtrapolation(ParameterExtrapolation):
    """Base class for extrapolation methods that require scenario parameters in their constructor."""

    pass


class LinearToTargetExtrapolation(ScenarioExtrapolation):
    """Linearly interpolate to a future target value according to scenario settings."""

    def __init__(self, scenario_parameters: Dict[str, Number]):
        self.scenario_parameters = scenario_parameters

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.Parameter,
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


class SmoothScalingExtrapolation(ScenarioExtrapolation):
    """Future values are scaled by a factor that changes linearly to a target factor."""

    def __init__(self, scenario_parameters: Dict[str, Number]):
        self.scenario_parameters = scenario_parameters

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.Parameter,
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
        scenario_parameters: Dict[str, fd.Parameter | Number] = None,
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

        for param_name, cls in self.parameter_extrapolation_classes.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")

            extrapolation_instance = self._create_extrapolation_instance(cls, scenario_parameters)

            modified_parameters[param_name] = extrapolation_instance.transform(
                modified_parameters[param_name], self.historic_time, self.extended_time
            )

        return modified_parameters

    def _create_extrapolation_instance(
        self,
        cls: type,
        scenario_parameters: Dict[str, Number],
    ) -> ParameterExtrapolation:
        """Create an instance of the extrapolation class with appropriate constructor arguments.

        ScenarioExtrapolation subclasses receive scenario_parameters; others are instantiated with no arguments.
        """
        if issubclass(cls, ScenarioExtrapolation):
            if scenario_parameters is None:
                raise ValueError(f"scenario_parameters required for {cls.__name__}")
            return cls(scenario_parameters)
        else:
            return cls()


class ConstrainedSplitExtrapolation(ScenarioExtrapolation):
    """Extrapolate a split parameter (values sum to 1 over a dimension) while preserving the constraint.

    Entries with explicit targets interpolate linearly to their target by their target year.
    The remaining budget is distributed in one of two modes, determined per context slice
    (each combination of non-split, non-time index values):

    - **Proportional** (no receiver specified): unspecified entries scale proportionally to their
      historic relative shares so that the sum stays 1.
    - **Receiver** (receiver entries flagged): receiver entries absorb the cumulative delta from
      targeted entries; all other unspecified entries remain at their historic values.

    Scenario parameters required (same dims as the main parameter, 0 where not applicable):
      - ``{param_name}_target``       – target value per entry (0 target_year = not specified)
      - ``{param_name}_target_year``  – year to reach the target (0 = not specified)
      - ``{param_name}_receiver``     – non-zero flags an entry as a receiver

    Use a named subclass that encodes the full dimension name as a suffix, e.g.::

        some_split_param: ConstrainedSplitExtrapolation_Function
    """

    split_dim_name: str = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        prefix = "ConstrainedSplitExtrapolation_"
        if cls.__name__.startswith(prefix):
            cls.split_dim_name = cls.__name__[len(prefix):]

    def __init__(self, scenario_parameters: Dict[str, fd.Parameter]):
        self.scenario_parameters = scenario_parameters

    def fill_values(
        self,
        prepared_param: fd.Parameter,
        new_param: fd.Parameter,
    ) -> fd.Parameter:

        if self.split_dim_name is None:
            raise ValueError(
                "Use a named subclass (e.g. ConstrainedSplitExtrapolation_Function), not the base class directly."
            )

        add_assumption_doc(
            type="model switch",
            name=f"Constrained split extrapolation of {prepared_param.name} over '{self.split_dim_name}' dimension.",
            description=self.description,
        )

        split_letter = prepared_param.dims[self.split_dim_name].letter
        param_name = prepared_param.name
        last_hist = self._get_last_historic_value(prepared_param)
        last_year = float(self._last_historic_time)

        target = self.scenario_parameters[f"{param_name}_target"]
        target_year = self.scenario_parameters[f"{param_name}_target_year"]
        receiver = self.scenario_parameters.get(f"{param_name}_receiver")

        # Masks: target_year == 0 (flodym default) signals "no target specified"
        is_targeted = target_year.apply(lambda x: (x > 0).astype(float))
        is_receiver = (
            receiver.apply(lambda x: (x > 0).astype(float))
            if receiver is not None
            else fd.Parameter.full_like(last_hist, 0.0)
        )
        unspec = (1 - is_targeted) * (1 - is_receiver)

        # For non-targeted entries, safe fallbacks keep progress = 0, so they interpolate to last_hist
        safe_target = is_targeted * target + (1 - is_targeted) * last_hist
        safe_year = is_targeted * target_year + (1 - is_targeted) * (last_year + 1.0)

        # Per-entry linear interpolation progress, clamped to [0, 1]
        t_arr = fd.Parameter(
            dims=new_param.dims.get_subset(("t",)),
            values=np.array(self.extended_time.items, dtype=float),
        )
        progress = ((t_arr - last_year) / (safe_year - last_year).maximum(1.0)).apply(
            lambda x: np.clip(x, 0.0, 1.0)
        )
        interp_vals = last_hist.cast_to(new_param.dims) + progress * (safe_target - last_hist)

        # Dimension letter tuples for summing over the split dimension
        non_split = tuple(d for d in new_param.dims.letters if d != split_letter)
        non_t_non_split = tuple(d for d in last_hist.dims.letters if d != split_letter)

        # Budget accounting
        targeted_sum = (interp_vals * is_targeted).sum_to(non_split)
        remaining = 1.0 - targeted_sum
        unspec_hist_sum = (last_hist * unspec).sum_to(non_t_non_split)
        recv_hist_sum = (last_hist * is_receiver).sum_to(non_t_non_split)

        # Determine mode per slice: receiver mode where any receiver exists, else proportional
        has_recv = recv_hist_sum.apply(lambda x: (x > 1e-9).astype(float)).cast_to(remaining.dims)

        # Receiver mode: receivers absorb (remaining - unspec_hist_sum); unspecified stay at historic (scale = 1)
        recv_budget = remaining - unspec_hist_sum.cast_to(remaining.dims)
        recv_scale = has_recv * recv_budget / recv_hist_sum.cast_to(remaining.dims).maximum(1e-9)

        # Proportional mode: all unspecified entries scale to fill remaining (scale = remaining / unspec_hist_sum)
        prop_scale = (1 - has_recv) * remaining / unspec_hist_sum.cast_to(remaining.dims).maximum(1e-9)

        # Combined unspecified scale: 1 in receiver mode, prop_scale in proportional mode
        unspec_scale = has_recv + prop_scale

        # Assemble: each group fills its budget exactly, so the sum over the split dim stays 1
        new_param[...] = (
            interp_vals * is_targeted  # targeted entries interpolate to target
            + recv_scale * last_hist * is_receiver  # receivers absorb the delta
            + unspec_scale * last_hist * unspec  # unspecified: constant or proportional
        ).cast_to(new_param.dims)

        # Sanity check: new_param should sum to 1 over the split dimension for all slices
        sums = new_param.sum_over((split_letter,))
        assert np.allclose(sums.values, 1.0, atol=1e-6), (
            f"'{param_name}' does not sum to 1 over '{self.split_dim_name}' after extrapolation. "
            f"Max deviation: {np.abs(sums.values - 1.0).max():.2e}"
        )

        return new_param

    @property
    def description(self) -> str:
        return (
            f"Split parameter extrapolated over '{self.split_dim_name}' dimension with sum=1 constraint. "
            "Specified entries interpolate linearly to their targets; receiver entries absorb the "
            "cumulative delta; remaining entries either scale proportionally or stay constant."
        )


class ConstrainedSplitExtrapolation_Function(ConstrainedSplitExtrapolation):
    pass


class ConstrainedSplitExtrapolation_Structure(ConstrainedSplitExtrapolation):
    pass
