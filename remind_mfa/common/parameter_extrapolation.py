import numpy as np
import flodym as fd
from typing import Dict, Optional, TYPE_CHECKING
from numbers import Number

if TYPE_CHECKING:
    from remind_mfa.common.common_config import CommonCfg, ExtrapolationConfig
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.data_blending import blend


class ParameterExtrapolation:
    """Extrapolate a parameter into the future, blending to pre-defined scenarios.

    Handles three input cases:

    1. Parameters with 'h' dimension: extended to 't', future filled with the last
       historic value (constant continuation) as baseline
    2. Parameters with 't' dimension: existing future values serve as baseline
    3. Parameters with no time dimension: 't' dimension is added, values constant in time

    On top of the baseline, scenario parameters modify individual entries (see
    ``ParameterExtrapolationSpec`` for the naming convention). The two modes differ in
    their anchor:

    - **Absolute** (``{name}_target`` + ``_target_year``): the entry blends from the
      *last historic value* to the absolute target by the target year. The anchor is
      always the last historic value, independent of the baseline shape — so for a
      't' parameter this ignores any pre-existing future trajectory.
    - **Relative** (``{name}_factor`` + ``_factor_year``): the entry keeps its *baseline*
      and is multiplied by a factor blending from 1 to the given value by the factor year.
      The anchor is the baseline itself — so for a 't' parameter it scales the pre-existing
      future trajectory, and for an 'h'/static one it scales the (constant) last historic value.

    All other entries keep the baseline. Historic values are always preserved.
    """

    def __init__(
        self,
        cfg: "ExtrapolationConfig",
        scenario_parameters: Dict[str, fd.Parameter | Number],
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ):
        self.cfg = cfg
        self.scenario_parameters = scenario_parameters or {}
        self.historic_time = historic_time
        self.extended_time = extended_time

    def extrapolate(self, parameter: fd.Parameter, name: str) -> fd.Parameter:
        """Return the extrapolated parameter with full 't' dimension."""
        prepared = self._prepare_parameter(parameter, name)
        last_hist = prepared[{"t": self._last_historic_time}]

        target = self.scenario_parameters.get(f"{name}_target")
        target_year = self.scenario_parameters.get(f"{name}_target_year")
        factor = self.scenario_parameters.get(f"{name}_factor")
        factor_year = self.scenario_parameters.get(f"{name}_factor_year")

        # allow different extrapolation modes within the same parameter
        is_abs = self._specified_mask(target_year, last_hist.dims)
        is_rel = self._specified_mask(factor_year, last_hist.dims)
        self._check_scenario_definition(
            name, target, target_year, factor, factor_year, is_abs, is_rel
        )
        unspec = (1 - is_abs) * (1 - is_rel)

        # keep the baseline where no scenario is specified; targeted entries start at zero
        new_values = prepared * unspec

        # absolute extrapolation: blend from the last historic value to the target
        if target_year is not None:
            new_values = new_values + is_abs * self._absolute_values(
                last_hist, target, target_year, prepared.dims
            )
        # relative extrapolation: scale the baseline by a factor blending from 1
        if factor_year is not None:
            new_values = new_values + is_rel * prepared * self._relative_factors(
                factor, factor_year, prepared.dims
            )

        # renormalize over the split dimension if supplied
        if self.cfg.constrained_split_dim is not None:
            # note: 1 - unspec equals the combined is_abs/is_rel mask, but is safe against
            # flodym's sum-reducing addition when the two masks have different dimensions
            new_values = self._renormalize_split(new_values, prepared, 1 - unspec, name)

        add_assumption_doc(
            type="model switch",
            name=f"Extrapolation of {name}",
            description=self._description(
                name, is_abs, is_rel, unspec, target, target_year, factor, factor_year
            ),
        )

        # preserve historical values
        new_param = new_values.to_Parameter(name=name)
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

    def _check_scenario_definition(
        self, name, target, target_year, factor, factor_year, is_abs, is_rel
    ):
        if (target is None) != (target_year is None):
            missing = f"{name}_target" if target is None else f"{name}_target_year"
            raise ValueError(
                f"'{missing}' is missing — target and target_year must be set together."
            )
        if (factor is None) != (factor_year is None):
            missing = f"{name}_factor" if factor is None else f"{name}_factor_year"
            raise ValueError(
                f"'{missing}' is missing — factor and factor_year must be set together."
            )
        if np.any((is_abs * is_rel).values > 0):
            raise ValueError(
                f"Scenario sets both '{name}_target' and '{name}_factor' for the same entries. "
                "Only one of absolute target and relative factor may be given per entry."
            )

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
            type=self.cfg.blend,
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
            type=self.cfg.blend,
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

        - **Proportional** (no receiver specified): unspecified entries scale
          proportionally to their baseline shares so that the sum stays 1.
        - **Receiver** (at most one receiver entry flagged via ``{name}_receiver``):
          unspecified entries keep their baseline; the single receiver absorbs whatever
          share is left so the sum stays 1.
        """
        split_letter = prepared.dims[self.cfg.constrained_split_dim].letter

        # Classify entries into three groups: targeted, receiver, and unspecified
        receiver = self.scenario_parameters.get(f"{name}_receiver")
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
                f"'{name}' does not sum to 1 over '{self.cfg.constrained_split_dim}' after "
                f"extrapolation. Max deviation on applicable slices: {np.abs(deviation).max():.2e}"
            )

    def _description(
        self,
        name: str,
        is_abs: fd.FlodymArray,
        is_rel: fd.FlodymArray,
        unspec: fd.FlodymArray,
        target: Optional[fd.FlodymArray],
        target_year: Optional[fd.FlodymArray],
        factor: Optional[fd.FlodymArray],
        factor_year: Optional[fd.FlodymArray],
    ) -> str:
        """Describe the extrapolation actually applied to this parameter's entries.

        Reports only the modes that occur, with the scope (named dimension items where
        few, otherwise a count) and the actual target/factor values and years.
        """
        parts = [f"Parameter '{name}' is extended into the future using blend '{self.cfg.blend}'."]

        abs_scope = self._mask_scope(is_abs)
        if abs_scope is not None and target is not None and target_year is not None:
            tv = self._value_range(target, is_abs, self._fmt_value)
            ty = self._value_range(target_year, is_abs, self._fmt_year)
            parts.append(
                f" Absolute targets ('{name}_target') are set for {abs_scope}, blending from "
                f"the last historic value to {tv} by {ty}."
            )

        rel_scope = self._mask_scope(is_rel)
        if rel_scope is not None and factor is not None and factor_year is not None:
            fv = self._value_range(factor, is_rel, self._fmt_value)
            fy = self._value_range(factor_year, is_rel, self._fmt_year)
            parts.append(
                f" Relative factors ('{name}_factor') are applied to {rel_scope}, scaling the "
                f"baseline by {fv} by {fy}."
            )

        const_scope = self._mask_scope(unspec)
        if const_scope == "all entries":
            parts.append(" All entries keep their baseline (constant continuation).")
        elif const_scope is not None:
            parts.append(" The remaining entries keep their baseline.")

        if self.cfg.constrained_split_dim is not None:
            parts.append(
                f" The sum=1 constraint over the '{self.cfg.constrained_split_dim}' dimension "
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
    """Applies the configured extrapolation to all parameters listed in the YAML config
    under ``model_switches.parameter_extrapolation``."""

    def __init__(
        self,
        cfg: "CommonCfg",
        historic_time: fd.Dimension,
        extended_time: fd.Dimension,
    ):
        self.extrapolation_cfg = cfg.model_switches.parameter_extrapolation or {}
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
        """Extrapolate all configured parameters and return the updated dictionary.

        Only parameters listed under ``parameter_extrapolation`` in the config model
        switches are adjusted; all others are returned unchanged.

        Args:
            parameters: Dictionary of parameters to potentially extrapolate
            scenario_parameters: Dictionary of scenario-specific target/factor values.
            Parameters with no scenario entries extend constantly.

        Returns:
            Dictionary of parameters with extrapolations applied where configured
        """
        modified_parameters = parameters.copy()

        for param_name, cfg in self.extrapolation_cfg.items():
            if param_name not in modified_parameters:
                raise ValueError(f"Parameter '{param_name}' not found in parameters.")

            extrapolation = ParameterExtrapolation(
                cfg=cfg,
                scenario_parameters=scenario_parameters,
                historic_time=self.historic_time,
                extended_time=self.extended_time,
            )
            modified_parameters[param_name] = extrapolation.extrapolate(
                modified_parameters[param_name], param_name
            )

        return modified_parameters
