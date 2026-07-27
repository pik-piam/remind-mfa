import logging
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

        - **Target** (``extra:type="target"``): the entry blends from the
      *last historic value* to the absolute target by the target year. The anchor is
      always the last historic value, independent of the baseline shape — so for a
      't' parameter this ignores any pre-existing future trajectory.
        - **Factor** (``extra:type="factor"``): the entry keeps its *baseline*
      and is multiplied by a factor blending from 1 to the given value by the factor year.
      The anchor is the baseline itself — so for a 't' parameter it scales the pre-existing
      future trajectory, and for an 'h'/static one it scales the (constant) last historic value.

    Scenario values are either numbers or strings naming another model parameter, in which case
    the values of the referenced parameter at the entry's coordinates serve as the target/factor.

    All other entries keep the baseline. Historic values are always preserved.
    """

    def __init__(
        self,
        scenario_parameter: ExtrapolationScenarioParameter,
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
        parameters: Optional[Dict[str, fd.Parameter]] = None,
    ):
        self.scenario_parameter = scenario_parameter
        self.definition = scenario_parameter.definition
        self.historic_time = historic_time
        self.extended_time = extended_time
        self.parameters = parameters or {}

    def extrapolate(self, parameter: fd.Parameter, name: str) -> fd.Parameter:
        """Return the extrapolated parameter with full 't' dimension."""
        prepared = self._prepare_parameter(parameter, name)
        last_hist = prepared[{"t": self._last_historic_time}]

        endpoint_year = self.scenario_parameter.extras.get("year")
        self._warn_values_without_year(endpoint_year, name)
        is_specified = self._specified_mask(endpoint_year, last_hist.dims)
        unspec = 1 - is_specified

        # keep the baseline where no scenario is specified; targeted entries start at zero
        new_values = prepared * unspec

        endpoint = self._resolve_endpoint(prepared, endpoint_year, name)
        ext_type = None
        if endpoint_year is not None:
            ext_type = self.scenario_parameter.resolve_type()
            if ext_type == "target":
                new_values = new_values + is_specified * self._absolute_values(
                    last_hist, endpoint, endpoint_year, prepared.dims
                )
            elif ext_type == "factor":
                new_values = new_values + is_specified * prepared * self._relative_factors(
                    endpoint, endpoint_year, prepared.dims
                )
            else:
                # safety check that should never be reached - resolve_type() fails first.
                raise ValueError(
                    f"Extrapolation type of '{name}' must be 'target' or 'factor', not '{ext_type}'."
                )

        if self.definition.split_dimension_letter is not None:
            new_values = self._renormalize_split(new_values, prepared, is_specified, name)

        add_assumption_doc(
            type="model switch",
            name=f"Extrapolation of {name}",
            description=self._description(name, is_specified, endpoint_year, ext_type),
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

    def _warn_values_without_year(self, endpoint_year: Optional[fd.FlodymArray], name: str):
        """Warn about values set at coordinates without an 'extra:year' entry.

        Such values have no effect: without a year, the entry keeps its baseline.
        """
        is_set = self.scenario_parameter.is_set
        year = endpoint_year.values if endpoint_year is not None else 0
        has_value_no_year = (is_set.values > 0) & (year <= 0)
        if not has_value_no_year.any():
            return
        mask = fd.FlodymArray(dims=is_set.dims, values=has_value_no_year.astype(float))
        slices = list(map(tuple, mask.items_where(lambda x: x > 0.5)))
        coordinates = ", ".join(map(str, slices[:10])) + (" ..." if len(slices) > 10 else "")
        logging.warning(
            f"'{name}' has values set at {len(slices)} coordinate(s) without "
            f"'extra:year'; they will have no effect: {coordinates}. "
            "Set 'extra:year' or remove the value."
        )

    def _resolve_endpoint(
        self,
        prepared: fd.Parameter,
        endpoint_year: Optional[fd.FlodymArray],
        name: str,
    ) -> Optional[fd.FlodymArray]:
        """Resolve the raw scenario values (numbers or parameter names) to a float array.

        The raw scenario value array has dtype object; string entries name a model
        parameter whose values at the entry's coordinates serve as the endpoint. The
        result spans the prepared dims, so a reference with a 't' dimension yields a
        time-dependent endpoint (trajectory-following). Returns None if no endpoint
        year is set (all entries keep their baseline).
        """
        if endpoint_year is None:
            return None

        raw = self.scenario_parameter.value

        values = raw.cast_values_to(prepared.dims)
        for ref_name in self.scenario_parameter.referenced_parameters():
            reference = self._get_reference(ref_name, prepared, name)
            mask = values == ref_name
            values[mask] = reference.cast_values_to(prepared.dims)[mask]
        return fd.Parameter(
            dims=prepared.dims, values=values.astype(float), name=f"{name}_endpoint"
        )

    def _get_reference(self, ref_name: str, prepared: fd.Parameter, name: str) -> fd.Parameter:
        """Look up and validate a model parameter referenced as an endpoint."""
        if ref_name not in self.parameters:
            raise ValueError(
                f"Parameter '{ref_name}', referenced as endpoint of '{name}', not found "
                "in model parameters. It must be read from input data or computed "
                "before extrapolation."
            )
        reference = self.parameters[ref_name]
        if "h" in reference.dims.letters:
            raise ValueError(
                f"Reference '{ref_name}' for '{name}' has historic time dimension 'h'. "
                "Provide it with a full time dimension or declare it as an extrapolated "
                "scenario parameter (it is then extrapolated first automatically)."
            )
        extra_dims = set(reference.dims.letters) - set(prepared.dims.letters)
        if extra_dims:
            raise ValueError(
                f"Reference '{ref_name}' for '{name}' has dimension(s) {sorted(extra_dims)} "
                f"not present in '{name}' {prepared.dims.letters}."
            )
        return reference

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
        name: str,
    ) -> fd.FlodymArray:
        """Preserve the sum=1 constraint over the split dimension.

        Targeted entries keep their blended values. The remaining budget is distributed
        in one of two modes, determined per context slice (each combination of non-split,
        non-time index values):

        - **Proportional** (no ``split_receiver_item`` in the definition): unspecified
          entries scale proportionally to their baseline shares so that the sum stays 1.
        - **Receiver** (definition declares ``split_receiver_item``): in slices with a
          targeted entry, unspecified entries keep their baseline; the receiver item
          absorbs whatever share is left so the sum stays 1.

        Either mode raises via the non-negativity assertion if a target is infeasible,
        i.e. it exceeds what the other items hold in the baseline so a share would go
        negative.
        """
        split_letter = self.definition.split_dimension_letter
        is_receiver = self._receiver_mask(prepared, is_targeted, split_letter)
        # 1 where the receiver absorbs in this slice, 0 elsewhere (at most one receiver per slice)
        is_receiver_mode = is_receiver.sum_over(split_letter)

        # Receiver mode: non-targeted entries already hold their baseline in `values`,
        # so the receiver simply absorbs the slice's deviation from 1
        deficit = 1.0 - values.sum_over(split_letter)
        receiver_result = values + deficit * is_receiver

        # Proportional mode: non-targeted entries scale to fill what the targets leave over
        remaining_share = 1.0 - (values * is_targeted).sum_over(split_letter)
        untargeted_baseline_sum = (prepared * (1 - is_targeted)).sum_over(split_letter)
        proportional_result = values * is_targeted + prepared * (1 - is_targeted) * (
            remaining_share / untargeted_baseline_sum.maximum(1e-9)
        )

        new_values = receiver_result * is_receiver_mode + proportional_result * (
            1 - is_receiver_mode
        )

        self._assert_sums_to_one(new_values, prepared, split_letter, name)
        self._assert_non_negative(new_values, name)

        return new_values

    def _receiver_mask(
        self,
        prepared: fd.FlodymArray,
        is_targeted: fd.FlodymArray,
        split_letter: str,
    ) -> fd.FlodymArray:
        """Mark the receiver item where it should absorb the freed share.

        Zero everywhere unless the definition declares a ``split_receiver_item``. Where
        it does, the mask is 1 on that item, but only in slices that (a) have a target
        freeing up share, and (b) do not target the receiver item itself — if the
        receiver is targeted, its target wins and the remaining items scale
        proportionally instead.
        """
        receiver_item = self.definition.split_receiver_item
        if receiver_item is None:
            return fd.Parameter(dims=prepared.dims.drop("t"))

        # mark the item that is meant to receive
        split_dimension = prepared.dims[split_letter]
        is_receiver_item = fd.Parameter(dims=prepared.dims[(split_letter,)])
        is_receiver_item[{split_dimension.name: receiver_item}] = 1.0

        # mark slices that have a targeted entry
        slice_has_target = is_targeted.sum_over(split_letter).apply(lambda x: (x > 0).astype(float))
        # marked receiver x this slice is targeted x the receiver is not targeted
        return is_receiver_item * slice_has_target * (1 - is_targeted)

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

    def _assert_non_negative(self, values: fd.FlodymArray, name: str):
        """Check that no split share is negative after renormalization.

        A negative share arises e.g. when the receiver item must absorb more than the
        targeted entries free up (the baseline of the other items already exceeds the
        remaining share)."""
        min_value = values.values.min()
        if min_value < -1e-6:
            raise ValueError(
                f"'{name}' has negative shares after split renormalization "
                f"(minimum {min_value:.2e}). Check target values, target coordinates, "
                "and the split_receiver_item of the definition."
            )

    def _description(
        self,
        name: str,
        is_specified: fd.FlodymArray,
        endpoint_year: Optional[fd.FlodymArray],
        ext_type: Optional[str],
    ) -> str:
        """Short summary of the applied extrapolation; details are in the scenario config."""
        has_scenario = endpoint_year is not None and is_specified.values.any()
        if not has_scenario:
            return (
                f"Parameter '{name}' is extended into the future; "
                "all entries keep their baseline."
            )

        if ext_type == "target":
            mode = "blending to absolute scenario targets"
        else:
            mode = "scaling the baseline by scenario factors"
        sentence = (
            f"Parameter '{name}' is extended into the future, {mode} "
            f"('{self.definition.blending_function}' blend)"
        )
        references = self.scenario_parameter.referenced_parameters()
        if references:
            sentence += ", (partly) converging to " + ", ".join(f"'{r}'" for r in references)
        sentences = [sentence + "."]

        if not is_specified.values.all():
            sentences.append("Entries without scenario data keep their baseline.")

        if self.definition.split_dimension_letter is not None:
            receiver = self.definition.split_receiver_item
            how = (
                f"'{receiver}' absorbs the freed share"
                if receiver is not None
                else "unspecified entries scale proportionally"
            )
            sentences.append(
                f"The sum=1 constraint over '{self.definition.split_dimension_letter}' "
                f"is preserved ({how})."
            )

        return " ".join(sentences)


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

        Extrapolations are processed in dependency order: a parameter referenced as an
        endpoint of another extrapolated parameter is extrapolated first, independent
        of definition order. Ties keep the definition order. Circular references raise.

        Args:
            parameters: Dictionary of parameters to potentially extrapolate
            scenario_parameters: Scenario values, including structured extrapolation inputs.

        Returns:
            Dictionary of parameters with extrapolations applied where configured
        """
        modified_parameters = parameters.copy()

        extrapolations = {
            name: scenario_parameter
            for name, scenario_parameter in (scenario_parameters or {}).items()
            if isinstance(scenario_parameter, ExtrapolationScenarioParameter)
        }

        for name in self._processing_order(extrapolations):
            scenario_parameter = extrapolations[name]
            param_name = scenario_parameter.definition.name
            if param_name not in modified_parameters:
                if not scenario_parameter.definition.create_new:
                    raise ValueError(
                        f"Parameter '{param_name}' not found in parameters. Use create_new=True to create it."
                    )
                parameter = fd.Parameter(name=param_name, dims=scenario_parameter.value.dims)
                parameter[...] = 1.0 if scenario_parameter.resolve_type() == "factor" else 0.0
            else:
                parameter = modified_parameters[param_name]

            extrapolation = ParameterExtrapolation(
                scenario_parameter=scenario_parameter,
                historic_time=self.historic_time,
                extended_time=self.extended_time,
                parameters=modified_parameters,
            )
            modified_parameters[param_name] = extrapolation.extrapolate(parameter, param_name)

        return modified_parameters

    @staticmethod
    def _processing_order(extrapolations: Dict[str, "ExtrapolationScenarioParameter"]) -> list:
        """Order extrapolations so referenced parameters are processed before referrers.

        Repeatedly picks (in definition order) the parameters whose referenced
        extrapolated parameters are all done. References to plain model parameters
        impose no ordering. Raises if a circular reference prevents progress.
        """
        remaining = dict(extrapolations)
        done = set()
        order = []
        while remaining:
            progress = False
            for name, scenario_parameter in list(remaining.items()):
                open_dependencies = [
                    ref
                    for ref in scenario_parameter.referenced_parameters()
                    if ref in extrapolations and ref not in done
                ]
                if not open_dependencies:
                    order.append(name)
                    done.add(name)
                    del remaining[name]
                    progress = True
            if not progress:
                names = ", ".join(f"'{n}'" for n in remaining)
                raise ValueError(
                    f"Circular reference between extrapolated parameters: {names}. "
                    "Parameters cannot use each other (or themselves) as endpoints."
                )
        return order
