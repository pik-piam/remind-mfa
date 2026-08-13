"""Tests for parameter extrapolation and blending.

Covers the contracts of `remind_mfa.common.data_blending.blend` and
`remind_mfa.common.parameter_extrapolation`, built on the same classes the scenario
CSVs are parsed into (`ExtrapolationDefinition`, `ExtrapolationScenarioParameter`).

Dimensions are kept tiny so expected values are hand-computable: history 2000-2005,
full time 2000-2010, endpoint year 2008 with a linear blend (thirds as midpoints).
"""

import logging

import numpy as np
import flodym as fd
import pytest

from remind_mfa.common.common_definition import ExtrapolationDefinition
from remind_mfa.common.data_blending import (
    BLEND_TYPES,
    CriticallyDampedBlender,
    blend,
    blending_factor,
)
from remind_mfa.common.parameter_extrapolation import (
    ParameterExtrapolation,
    ParameterExtrapolationManager,
)
from remind_mfa.common.scenarios import ExtrapolationScenarioParameter

H = fd.Dimension(name="Historic Time", letter="h", items=list(range(2000, 2006)))
T = fd.Dimension(name="Time", letter="t", items=list(range(2000, 2011)))
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
S = fd.Dimension(name="Structure", letter="s", items=["X", "Y", "Z"])

# blending functions that reach y_lower/y_upper exactly at the bounds
EXACT_BLEND_TYPES = [b for b in BLEND_TYPES if b not in ("sigmoid3", "sigmoid4")]
# blending functions that hold the bound values outside [x_lower, x_upper]
CLAMPED_BLEND_TYPES = [
    b for b in EXACT_BLEND_TYPES if b not in ("extrapol_sigmoid3", "extrapol_sigmoid4")
]


def dimset(*dims) -> fd.DimensionSet:
    return fd.DimensionSet(dim_list=list(dims))


def make_scn(definition: ExtrapolationDefinition, scn_dims, rows) -> ExtrapolationScenarioParameter:
    """Build a scenario parameter and apply (value, index, extras) rows like CSV rows."""
    scn = ExtrapolationScenarioParameter(
        definition=definition,
        value=fd.Parameter(
            name=definition.name, dims=scn_dims, values=np.zeros(scn_dims.shape, dtype=object)
        ),
    )
    for value, index, extras in rows:
        scn.set_value(value, index)
        scn.set_extras(extras, index)
    return scn


def extrapolate(parameter, scn, parameters=None) -> fd.Parameter:
    extra = ParameterExtrapolation(
        scenario_parameter=scn, historic_time=H, extended_time=T, parameters=parameters
    )
    return extra.extrapolate(parameter, scn.definition.name)


def at(arr: fd.FlodymArray, **coords) -> float:
    """Single value at the given dim-letter coordinates."""
    values = arr[coords].values
    assert values.size == 1
    return float(values.flatten()[0])


def h_param(name="p", per_region=(10.0, 20.0)) -> fd.Parameter:
    """Parameter on (h, r), constant in time."""
    values = np.tile(np.array(per_region), (len(H.items), 1))
    return fd.Parameter(name=name, dims=dimset(H, R), values=values)


def t_param(name="p") -> fd.Parameter:
    """Parameter on (t, r) with a non-constant trajectory: 10+i / 20+i in year 2000+i."""
    ramp = np.arange(len(T.items), dtype=float)
    values = np.stack([10.0 + ramp, 20.0 + ramp], axis=1)
    return fd.Parameter(name=name, dims=dimset(T, R), values=values)


# --- A. blend / blending functions -------------------------------------------------


@pytest.mark.parametrize("blend_type", EXACT_BLEND_TYPES)
def test_blend_endpoint_exact(blend_type):
    result = blend(
        target_dims=dimset(T),
        y_lower=2.0,
        y_upper=6.0,
        x="t",
        x_lower=2002,
        x_upper=2008,
        type=blend_type,
    )
    assert at(result, t=2002) == pytest.approx(2.0)
    assert at(result, t=2008) == pytest.approx(6.0)
    within = result.values[T.items.index(2002) : T.items.index(2008) + 1]
    assert np.all(np.diff(within) >= -1e-9), "blend must be monotone between the bounds"


@pytest.mark.parametrize("blend_type", CLAMPED_BLEND_TYPES)
def test_blend_clamps_outside_range(blend_type):
    # extrapolate() relies on this: historic years must evaluate to y_lower, and
    # years after the endpoint must hold y_upper (trajectory-following).
    result = blend(
        target_dims=dimset(T),
        y_lower=2.0,
        y_upper=6.0,
        x="t",
        x_lower=2002,
        x_upper=2008,
        type=blend_type,
    )
    assert at(result, t=2000) == pytest.approx(2.0)
    assert at(result, t=2010) == pytest.approx(6.0)


def test_blend_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown blending function"):
        blending_factor(np.array([0.5]), "no_such_blend")


# --- B. baseline preparation --------------------------------------------------------


def test_baseline_preparation():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(definition, dimset(R), rows=[])  # no scenario data: constant continuation

    # h-param: history preserved, future filled with last historic value
    result = extrapolate(h_param(), scn)
    assert result.dims.letters == ("t", "r")
    np.testing.assert_allclose(result[{"t": H}].values, h_param().values)
    assert at(result, t=2010, r="A") == pytest.approx(10.0)

    # static param: time dimension added, values constant in time
    static = fd.Parameter(name="p", dims=dimset(R), values=np.array([1.5, 2.5]))
    result = extrapolate(static, scn)
    assert at(result, t=2000, r="B") == pytest.approx(2.5)
    assert at(result, t=2010, r="B") == pytest.approx(2.5)

    # t-param: returned unchanged
    result = extrapolate(t_param(), scn)
    np.testing.assert_allclose(result.values, t_param().values)


# --- C. target / factor semantics ---------------------------------------------------


def test_target_blend():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(
        definition, dimset(R), rows=[(4.0, {"Region": "A"}, {"year": 2008, "type": "target"})]
    )
    result = extrapolate(h_param(), scn)

    np.testing.assert_allclose(result[{"t": H}].values, h_param().values)  # history exact
    assert at(result, t=2006, r="A") == pytest.approx(10.0 + (4.0 - 10.0) / 3)  # linear midpoint
    assert at(result, t=2008, r="A") == pytest.approx(4.0)  # target reached
    assert at(result, t=2010, r="A") == pytest.approx(4.0)  # ... and held
    np.testing.assert_allclose(result[{"r": "B"}].values, 20.0)  # unspecified: baseline


def test_factor_scales_existing_trajectory():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(
        definition, dimset(R), rows=[(2.0, {"Region": "A"}, {"year": 2008, "type": "factor"})]
    )
    result = extrapolate(t_param(), scn)

    assert at(result, t=2005, r="A") == pytest.approx(15.0)  # history exact
    assert at(result, t=2006, r="A") == pytest.approx((1 + 1 / 3) * 16.0)  # factor 4/3
    assert at(result, t=2008, r="A") == pytest.approx(2.0 * 18.0)  # full factor on baseline
    assert at(result, t=2010, r="A") == pytest.approx(2.0 * 20.0)  # still tracks trajectory
    np.testing.assert_allclose(result[{"r": "B"}].values, t_param()[{"r": "B"}].values)


def test_target_anchors_at_last_historic():
    # for a t-param, a target ignores the pre-existing future trajectory: the blend
    # starts at the last historic value, not at the baseline of the blend year
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(
        definition, dimset(R), rows=[(30.0, {"Region": "A"}, {"year": 2008, "type": "target"})]
    )
    result = extrapolate(t_param(), scn)

    assert at(result, t=2006, r="A") == pytest.approx(15.0 + (30.0 - 15.0) / 3)  # anchor 15, not 16
    assert at(result, t=2008, r="A") == pytest.approx(30.0)
    assert at(result, t=2005, r="A") == pytest.approx(15.0)  # history untouched


# --- D. input-error paths -----------------------------------------------------------


def test_value_without_year_warns_and_keeps_baseline(caplog):
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(definition, dimset(R), rows=[(4.0, {"Region": "A"}, {})])  # no extra:year
    with caplog.at_level(logging.WARNING):
        result = extrapolate(h_param(), scn)
    assert "no effect" in caplog.text
    np.testing.assert_allclose(result[{"r": "A"}].values, 10.0)  # baseline kept


def test_year_in_history_raises():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(
        definition, dimset(R), rows=[(4.0, {"Region": "A"}, {"year": 2005, "type": "target"})]
    )
    with pytest.raises(ValueError, match="last historic year"):
        extrapolate(h_param(), scn)


def test_type_resolution_errors():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))

    scn = make_scn(definition, dimset(R), rows=[(4.0, {"Region": "A"}, {"year": 2008})])
    with pytest.raises(ValueError, match="no extrapolation type"):
        extrapolate(h_param(), scn)

    scn = make_scn(
        definition,
        dimset(R),
        rows=[
            (4.0, {"Region": "A"}, {"year": 2008, "type": "target"}),
            (0.5, {"Region": "B"}, {"year": 2008, "type": "factor"}),
        ],
    )
    with pytest.raises(ValueError, match="mixed extrapolation types"):
        extrapolate(h_param(), scn)


# --- E. parameter-valued endpoints and manager orchestration ------------------------


def test_reference_endpoint_tracks_parameter():
    definition = ExtrapolationDefinition(name="p", dim_letters=("r",))
    scn = make_scn(
        definition, dimset(R), rows=[("ref", {"Region": "A"}, {"year": 2008, "type": "target"})]
    )
    ref = t_param(name="ref")
    result = extrapolate(h_param(), scn, parameters={"ref": ref})

    # from the endpoint year on, the entry follows the referenced trajectory
    for year in (2008, 2009, 2010):
        assert at(result, t=year, r="A") == pytest.approx(at(ref, t=year, r="A"))
    assert at(result, t=2005, r="A") == pytest.approx(10.0)  # history untouched

    with pytest.raises(ValueError, match="not found"):
        extrapolate(h_param(), scn, parameters={})


def manager_scn(name, value, ext_type="target"):
    definition = ExtrapolationDefinition(name=name, dim_letters=("r",))
    return make_scn(definition, dimset(R), rows=[(value, {}, {"year": 2008, "type": ext_type})])


def test_manager_dependency_order():
    manager = ParameterExtrapolationManager(historic_time=H, extended_time=T)
    parameters = {"p_a": h_param("p_a"), "p_b": h_param("p_b"), "p_c": h_param("p_c")}
    # p_a references p_b although p_b is defined later; p_b must be extrapolated first
    # (extrapolating p_a against the raw h-dim p_b would raise)
    scenario_parameters = {"p_a": manager_scn("p_a", "p_b"), "p_b": manager_scn("p_b", 4.0)}
    result = manager.apply_prm_extrapolation(parameters, scenario_parameters)

    assert at(result["p_b"], t=2010, r="A") == pytest.approx(4.0)
    assert at(result["p_a"], t=2010, r="A") == pytest.approx(4.0)  # follows extrapolated p_b
    assert result["p_c"] is parameters["p_c"]  # non-extrapolated parameters untouched


def test_manager_circular_reference_raises():
    manager = ParameterExtrapolationManager(historic_time=H, extended_time=T)
    parameters = {"p_a": h_param("p_a"), "p_b": h_param("p_b")}
    scenario_parameters = {"p_a": manager_scn("p_a", "p_b"), "p_b": manager_scn("p_b", "p_a")}
    with pytest.raises(ValueError, match="Circular reference"):
        manager.apply_prm_extrapolation(parameters, scenario_parameters)


def test_manager_create_new():
    manager = ParameterExtrapolationManager(historic_time=H, extended_time=T)

    # the stock_factor pattern: no input data, created with baseline 1 for type factor
    definition = ExtrapolationDefinition(name="new_factor", dim_letters=("r",), create_new=True)
    scn = make_scn(definition, dimset(R), rows=[(0.5, {}, {"year": 2008, "type": "factor"})])
    result = manager.apply_prm_extrapolation({}, {"new_factor": scn})
    assert at(result["new_factor"], t=2005, r="A") == pytest.approx(1.0)
    assert at(result["new_factor"], t=2006, r="A") == pytest.approx(1.0 - 0.5 / 3)
    assert at(result["new_factor"], t=2008, r="A") == pytest.approx(0.5)

    # without create_new, a missing parameter is an error
    definition = ExtrapolationDefinition(name="absent", dim_letters=("r",))
    scn = make_scn(definition, dimset(R), rows=[(0.5, {}, {"year": 2008, "type": "factor"})])
    with pytest.raises(ValueError, match="not found in parameters"):
        manager.apply_prm_extrapolation({}, {"absent": scn})


# --- F. split renormalization -------------------------------------------------------


def split_param() -> fd.Parameter:
    """Shares on (h, s) summing to 1: X=0.5, Y=0.3, Z=0.2."""
    values = np.tile(np.array([0.5, 0.3, 0.2]), (len(H.items), 1))
    return fd.Parameter(name="split", dims=dimset(H, S), values=values)


def split_scn(target, balancing_item=None) -> ExtrapolationScenarioParameter:
    definition = ExtrapolationDefinition(
        name="split",
        dim_letters=("s",),
        split_dimension_letter="s",
        split_balancing_item=balancing_item,
    )
    return make_scn(
        definition, dimset(S), rows=[(target, {"Structure": "X"}, {"year": 2008, "type": "target"})]
    )


def test_split_proportional():
    result = extrapolate(split_param(), split_scn(target=0.8))

    np.testing.assert_allclose(result.sum_over("s").values, 1.0)  # sums to 1 for all years
    np.testing.assert_allclose(result[{"t": H}].values, split_param().values)  # history exact
    assert at(result, t=2008, s="X") == pytest.approx(0.8)
    # untargeted items share the remainder proportionally (baseline ratio Y:Z = 3:2)
    assert at(result, t=2008, s="Y") == pytest.approx(0.12)
    assert at(result, t=2008, s="Z") == pytest.approx(0.08)


def test_split_balancing_item():
    result = extrapolate(split_param(), split_scn(target=0.6, balancing_item="Z"))

    np.testing.assert_allclose(result.sum_over("s").values, 1.0)
    np.testing.assert_allclose(result[{"s": "Y"}].values, 0.3)  # untargeted item keeps baseline
    assert at(result, t=2008, s="X") == pytest.approx(0.6)
    assert at(result, t=2008, s="Z") == pytest.approx(0.1)  # balancing item absorbs the shift


def test_split_infeasible_target_raises():
    # target 0.8 with Y fixed at 0.3 would push the balancing item to -0.1
    with pytest.raises(ValueError, match="negative shares"):
        extrapolate(split_param(), split_scn(target=0.8, balancing_item="Z"))


# --- G. CriticallyDampedBlender -----------------------------------------------------


def test_critically_damped_blender():
    time = np.arange(2000, 2101)
    historical = np.arange(6, dtype=float).reshape(-1, 1)  # ramp 0..5
    prediction = np.full((len(time), 1), 50.0)
    blended = CriticallyDampedBlender(
        time=time, historical=historical, prediction=prediction
    ).blend(approaching_time=10)

    np.testing.assert_allclose(blended[:6], historical)  # history preserved exactly
    assert abs(blended[-1, 0] - 50.0) < 0.5  # converges to the prediction long-term
