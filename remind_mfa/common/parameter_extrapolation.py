import numpy as np
import flodym as fd
from typing import Dict, Optional
from numbers import Number

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.data_blending import blend
from remind_mfa.common.scenarios import ExtrapolationScenarioParameter


class ParameterExtrapolation:
    """Extrapolate a parameter into the future, blending to pre-defined scenarios.

    Handles three input cases:

    1. Parameters with 'h' dimension: extended to 't', future filled with the last
       historic value (constant continuation) as baseline
    2. Parameters with 't' dimension: existing future values serve as baseline
    3. Parameters with no time dimension: 't' dimension is added, values constant in time

        On top of the baseline, scenario instructions modify individual
        entries. Its type determines the anchor:

        - **Target** (``type="target"``): the entry blends from the
      *last historic value* to the absolute target by the target year. The anchor is
      always the last historic value, independent of the baseline shape — so for a
      't' parameter this ignores any pre-existing future trajectory.
        - **Factor** (``type="factor"``): the entry keeps its *baseline*
      and is multiplied by a factor blending from 1 to the given value by the factor year.
      The anchor is the baseline itself — so for a 't' parameter it scales the pre-existing
      future trajectory, and for an 'h'/static one it scales the (constant) last historic value.

    All other entries keep the baseline. Historic values are always preserved.
    """

    def __init__(
        self,
        scenario_parameter: ExtrapolationScenarioParameter,
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ):
        self.scenario_parameter = scenario_parameter
        self.definition = scenario_parameter.definition
        self.historic_time = historic_time
        self.extended_time = extended_time

    def extrapolate(self, parameter: fd.Parameter, name: str) -> fd.Parameter:
        """Return the extrapolated parameter with full 't' dimension."""
        prepared = self._prepare_parameter(parameter, name)
        last_hist = prepared[{"t": self._last_historic_time}]

        endpoint = self.scenario_parameter.value
        endpoint_year = self.scenario_parameter.extras.get("year")
        is_specified = self._specified_mask(endpoint_year, last_hist.dims)
        unspec = 1 - is_specified

        # keep the baseline where no scenario is specified; targeted entries start at zero
        new_values = prepared * unspec

        if endpoint_year is not None:
            if self.definition.type is None:
                raise ValueError(f"'{name}' has scenario data but no extrapolation type.")
            if self.definition.type == "target":
                new_values = new_values + is_specified * self._absolute_values(
                    last_hist, endpoint, endpoint_year, prepared.dims
                )
            else:
                new_values = new_values + is_specified * prepared * self._relative_factors(
                    endpoint, endpoint_year, prepared.dims
                )

        if self.definition.split_dimension_letter is not None:
            new_values = self._renormalize_split(
                new_values,
                prepared,
                is_specified,
                self.scenario_parameter.extras.get("receiver"),
                name,
            )

        add_assumption_doc(
            type="model switch",
            name=f"Extrapolation of {name}",
            description=self._description(name, is_specified, unspec, endpoint, endpoint_year),
        )

        # preserve historical values
        new_param = fd.Parameter(values=new_values.values, dims=prepared.dims, name=name)
        new_param[{"t": self.historic_time}] = prepared[{"t": self.historic_time}]
        return new_param

    def _prepare_parameter(self, parameter: fd.Parameter, name: str) -> fd.Parameter:
        """Return the baseline parameter with 't' dimension.

        - h -> t: historic values kept, future filled with the last historic value
        - static -> t: values constant in time
        - t -> t: returned as-is
        """
        if "t" in parameter.dims.letters:
            # no changes needed
            return parameter

        if "h" in parameter.dims.letters:
            # replace h with t, fill future with last historic value
            new_dims = parameter.dims.replace("h", self.extended_time)
            new_param = fd.Parameter(dims=new_dims, name=name)
            new_param[...] = parameter[{"h": self._last_historic_time}].cast_to(new_dims)
            new_param[{"t": self.historic_time}] = parameter
            return new_param

        # static parameter: add time dimension, but keep values constant in time
        new_dims = parameter.dims.prepend(self.extended_time)
        return parameter.cast_to(new_dims)

    @property
    def _last_historic_time(self) -> Number:
        return self.historic_time.items[-1]

    def _specified_mask(
        self, year: Optional[fd.FlodymArray], dims: fd.DimensionSet
    ) -> fd.FlodymArray:
        """1.0 where a target/factor year is set (> 0), 0.0 elsewhere."""
        if year is None:
            return fd.Parameter(dims=dims)
        return year.apply(lambda x: (x > 0).astype(float))

    def _absolute_values(
        self,
        last_hist: fd.FlodymArray,
        target: fd.FlodymArray,
        target_year: fd.FlodymArray,
        target_dims: fd.DimensionSet,
    ) -> fd.FlodymArray:
        """Blend from the last historic value to the absolute target by the target year."""
        return blend(
            target_dims=target_dims,
            y_lower=last_hist,
            y_upper=target,
            x="t",
            x_lower=self._last_historic_time,
            x_upper=target_year,
            type=self.definition.blending_function,
        )

    def _relative_factors(
        self,
        factor: fd.FlodymArray,
        factor_year: fd.FlodymArray,
        target_dims: fd.DimensionSet,
    ) -> fd.FlodymArray:
        """Scaling factors blending from 1 to the scenario factor by the factor year."""
        return blend(
            target_dims=target_dims,
            y_lower=1.0,
            y_upper=factor,
            x="t",
            x_lower=self._last_historic_time,
            x_upper=factor_year,
            type=self.definition.blending_function,
        )

    def _renormalize_split(
        self,
        values: fd.FlodymArray,
        prepared: fd.FlodymArray,
        is_targeted: fd.FlodymArray,
        receiver: Optional[fd.FlodymArray],
        name: str,
    ) -> fd.FlodymArray:
        """Preserve the sum=1 constraint over the split dimension.

        Targeted entries keep their blended values. The remaining budget is distributed
        in one of two modes, determined per context slice (each combination of non-split,
        non-time index values):

        - **Proportional** (no receiver specified): unspecified entries scale
          proportionally to their baseline shares so that the sum stays 1.
        - **Receiver** (at most one receiver entry flagged via ``extra:receiver``):
          unspecified entries keep their baseline; the single receiver absorbs whatever
          share is left so the sum stays 1.
        """
        split_letter = self.definition.split_dimension_letter

        # Classify entries into three groups: targeted, receiver, and unspecified
        is_receiver = self._specified_mask(receiver, prepared.dims.drop("t"))
        is_unspecified = (1 - is_targeted) * (1 - is_receiver)

        # How much share remains after targeted entries have claimed their blended values
        targeted_sum = (values * is_targeted).sum_over(split_letter)
        remaining_share = 1.0 - targeted_sum

        # Unspecified entries keep their baseline in receiver mode, so their share is already claimed
        unspecified_baseline_sum = (prepared * is_unspecified).sum_over(split_letter)

        # 1 where a receiver exists in this slice, 0 elsewhere (at most one receiver per slice).
        # Cast to the slice dims: flodym addition reduces to the common dims by summing,
        # so combining arrays of unequal dims without casting corrupts the result.
        is_receiver_mode = is_receiver.sum_over(split_letter).cast_to(remaining_share.dims)

        # Proportional mode: by how much do unspecified entries scale to fill remaining_share?
        proportional_scale = remaining_share / unspecified_baseline_sum.maximum(1e-9)
        # Receiver mode: unspecified stay at baseline (scale=1); else scale proportionally
        unspecified_scale = is_receiver_mode + (1 - is_receiver_mode) * proportional_scale

        # Assemble: each group fills its budget exactly, so the sum over the split dim stays 1
        new_values = (
            values * is_targeted  # targeted entries keep their blended values
            + (remaining_share - unspecified_baseline_sum)
            * is_receiver  # receiver absorbs the freed share
            + unspecified_scale * prepared * is_unspecified  # baseline or proportionally scaled
        )

        self._assert_sums_to_one(new_values, prepared, split_letter, name)

        return new_values

    def _assert_sums_to_one(
        self,
        values: fd.FlodymArray,
        prepared: fd.FlodymArray,
        split_letter: str,
        name: str,
    ):
        """Check that values sum to 1 over the split dimension wherever the baseline does."""
        sums = values.sum_over(split_letter)
        baseline_sums = prepared.sum_over(split_letter)
        applicable = baseline_sums.apply(lambda x: x > 1e-9)
        deviation = ((sums - 1.0) * applicable).values
        if not np.allclose(deviation, 0.0, atol=1e-6):
            raise ValueError(
                f"'{name}' does not sum to 1 over '{self.definition.split_dimension_letter}' after "
                f"extrapolation. Max deviation on applicable slices: {np.abs(deviation).max():.2e}"
            )

    def _description(
        self,
        name: str,
        is_specified: fd.FlodymArray,
        unspec: fd.FlodymArray,
        endpoint: fd.FlodymArray,
        endpoint_year: Optional[fd.FlodymArray],
    ) -> str:
        """Describe the extrapolation actually applied to this parameter's entries.

        Reports only the modes that occur, with the scope (named dimension items where
        few, otherwise a count) and the actual target/factor values and years.
        """
        parts = [
            f"Parameter '{name}' is extended into the future using blend "
            f"'{self.definition.blending_function}'."
        ]

        scope = self._mask_scope(is_specified)
        if scope is not None and endpoint_year is not None:
            endpoint_value = self._value_range(endpoint, is_specified, self._fmt_value)
            year = self._value_range(endpoint_year, is_specified, self._fmt_year)
            if self.definition.type == "target":
                parts.append(
                    f" Absolute targets are set for {scope}, blending from the last historic "
                    f"value to {endpoint_value} by {year}."
                )
            else:
                parts.append(
                    f" Relative factors are applied to {scope}, scaling the baseline by "
                    f"{endpoint_value} by {year}."
                )

        const_scope = self._mask_scope(unspec)
        if const_scope == "all entries":
            parts.append(" All entries keep their baseline (constant continuation).")
        elif const_scope is not None:
            parts.append(" The remaining entries keep their baseline.")

        if self.definition.split_dimension_letter is not None:
            parts.append(
                f" The sum=1 constraint over the '{self.definition.split_dimension_letter}' dimension "
                "is preserved: receiver entries absorb the freed share; the rest scale "
                "proportionally or stay constant."
            )
        return "".join(parts)

    @staticmethod
    def _fmt_value(x: Number) -> str:
        x = float(x)
        return str(int(x)) if x == int(x) else f"{x:g}"

    @staticmethod
    def _fmt_year(x: Number) -> str:
        return str(int(round(float(x))))

    def _mask_scope(self, mask: fd.FlodymArray) -> Optional[str]:
        """Human-readable scope of a boolean mask: named items if few, else a count.

        Returns None when no entry is selected.
        """
        selected = mask.values.astype(bool)
        n = int(selected.sum())
        total = int(selected.size)
        if n == 0:
            return None
        if n == total:
            return "all entries"
        letters = mask.dims.letters
        if len(letters) == 1:
            items = [i for i, m in zip(mask.dims[letters[0]].items, selected) if m]
            if len(items) <= 6:
                return ", ".join(map(str, items))
            return f"{', '.join(map(str, items[:6]))} and {len(items) - 6} more"
        return f"{n} of {total} entries"

    @staticmethod
    def _value_range(values: fd.FlodymArray, mask: fd.FlodymArray, fmt) -> str:
        """Formatted single value if uniform across the mask, else a 'lo–hi' range."""
        selected = values.values[mask.values.astype(bool)]
        lo, hi = fmt(selected.min()), fmt(selected.max())
        return lo if lo == hi else f"{lo}–{hi}"


class ParameterExtrapolationManager:
    """Applies extrapolation instructions defined by structured scenario parameters."""

    def __init__(
        self,
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ):
        self.historic_time = historic_time
        self.extended_time = extended_time

        if "h" != self.historic_time.letter:
            raise ValueError(f"Historic time dimension does not have letter 'h'")
        if "t" != self.extended_time.letter:
            raise ValueError(f"New time dimension does not have letter 't'")

    def apply_prm_extrapolation(
        self,
        parameters: Dict[str, fd.Parameter],
        scenario_parameters: Optional[Dict[str, object]] = None,
    ) -> Dict[str, fd.Parameter]:
        """Extrapolate parameters described by structured scenario instructions.

        Only ``ExtrapolationScenarioParameter`` entries are adjusted; all other scenario
        values and model parameters are returned unchanged.

        Args:
            parameters: Dictionary of parameters to potentially extrapolate
            scenario_parameters: Scenario values, including structured extrapolation inputs.

        Returns:
            Dictionary of parameters with extrapolations applied where configured
        """
        modified_parameters = parameters.copy()

        for scenario_parameter in (scenario_parameters or {}).values():
            if not isinstance(scenario_parameter, ExtrapolationScenarioParameter):
                continue

            param_name = scenario_parameter.definition.name
            if param_name not in modified_parameters:
                if not scenario_parameter.definition.create_new:
                    raise ValueError(f"Parameter '{param_name}' not found in parameters.")
                parameter = scenario_parameter.value
            else:
                parameter = modified_parameters[param_name]

            extrapolation = ParameterExtrapolation(
                scenario_parameter=scenario_parameter,
                historic_time=self.historic_time,
                extended_time=self.extended_time,
            )
            modified_parameters[param_name] = extrapolation.extrapolate(parameter, param_name)

        return modified_parameters
