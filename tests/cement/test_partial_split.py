import flodym as fd
import numpy as np
import pytest

from remind_mfa.cement.cement_parameter_reconciliation import PartialSplit

REGION = fd.Dimension(name="Region", letter="r", items=["A", "B"])
END_USE = fd.Dimension(
    name="End Use",
    letter="u",
    items=["Residential", "Commercial", "Industrial", "Civil Engineering"],
)
COMMON_END_USE = fd.Dimension(
    name="Common End Use", letter="c", items=["Residential", "Commercial"]
)
MATERIAL = fd.Dimension(name="Construction Material", letter="m", items=["Concrete", "Mortar"])


@pytest.fixture
def end_use_split() -> fd.FlodymArray:
    values = np.array([[0.3, 0.2, 0.1, 0.4], [0.4, 0.3, 0.2, 0.1]])
    return fd.FlodymArray(dims=fd.DimensionSet(dim_list=[REGION, END_USE]), values=values)


@pytest.fixture
def material_split() -> fd.FlodymArray:
    values = np.array([[0.8, 0.2], [0.6, 0.4]])
    return fd.FlodymArray(dims=fd.DimensionSet(dim_list=[REGION, MATERIAL]), values=values)


def make_end_use_partial_split(split: fd.FlodymArray) -> tuple[PartialSplit, fd.FlodymArray]:
    partial_split = PartialSplit("end_use_split", ("u", "c"), tuple(COMMON_END_USE.items))
    reduced = split[{"u": COMMON_END_USE}]
    partial_split.set_complement_shares(reduced, partial_split.rest(split))
    return partial_split, reduced


def make_material_partial_split(split: fd.FlodymArray) -> PartialSplit:
    partial_split = PartialSplit("construction_material_split", ("m", "m"), ("Concrete",))
    partial_split.set_complement_shares(split, partial_split.rest(split))
    return partial_split


def test_rest_sums_complement(end_use_split):
    partial_split, _ = make_end_use_partial_split(end_use_split)
    rest = partial_split.rest(end_use_split)
    assert rest.dims.letters == ("r",)
    np.testing.assert_allclose(rest.values, [0.5, 0.3])


def test_view_is_invariant_to_joint_scaling(end_use_split):
    partial_split, reduced = make_end_use_partial_split(end_use_split)
    rest = partial_split.rest(end_use_split)
    view = partial_split.view(reduced, rest)
    scaled_view = partial_split.view(reduced * 1.7, rest * 1.7)
    np.testing.assert_allclose(scaled_view.values, view.values)
    # a normalized split is seen as it is
    np.testing.assert_allclose(view.values, reduced.values)


def test_view_stays_below_one(end_use_split):
    partial_split, reduced = make_end_use_partial_split(end_use_split)
    rest = partial_split.rest(end_use_split)
    view = partial_split.view(reduced * 10.0, rest)
    assert np.all(view.sum_over("c").values < 1.0)


def test_view_of_complement_item_follows_rest(material_split):
    partial_split = make_material_partial_split(material_split)
    rest = partial_split.rest(material_split)
    view = partial_split.view(material_split, rest * 2.0)
    expected_mortar = 2.0 * np.array([0.2, 0.4]) / (np.array([0.8, 0.6]) + 2.0 * np.array([0.2, 0.4]))
    np.testing.assert_allclose(view[{"m": "Mortar"}].values, expected_mortar)
    np.testing.assert_allclose(view.sum_over("m").values, 1.0)


def test_rest_correction_keeps_complement_ratio(end_use_split):
    partial_split, _ = make_end_use_partial_split(end_use_split)
    ratio_before = (
        end_use_split[{"u": "Industrial"}] / end_use_split[{"u": "Civil Engineering"}]
    ).values
    reconciled_before = end_use_split[{"u": COMMON_END_USE}].values.copy()
    factor = fd.FlodymArray(dims=fd.DimensionSet(dim_list=[REGION]), values=np.array([1.5, 0.5]))

    partial_split.apply_rest_correction(end_use_split, factor)

    ratio_after = (
        end_use_split[{"u": "Industrial"}] / end_use_split[{"u": "Civil Engineering"}]
    ).values
    np.testing.assert_allclose(ratio_after, ratio_before)
    np.testing.assert_allclose(end_use_split[{"u": COMMON_END_USE}].values, reconciled_before)
    np.testing.assert_allclose(partial_split.rest(end_use_split).values, [0.75, 0.15])
